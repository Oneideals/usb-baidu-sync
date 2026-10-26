"""Central coordinator orchestrating scanning, incremental diffing, and upload dispatch."""
from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from usb_baidu_sync.baidu_engine import BaiduEngine, UploadResult
from usb_baidu_sync.config import AppConfig
from usb_baidu_sync.database import SyncDatabase
from usb_baidu_sync.fingerprint import calculate_fast_hash
from usb_baidu_sync.path_resolver import resolve_remote_path
from usb_baidu_sync.usb_listener import USBListener, get_volume_metadata
from usb_baidu_sync.usb_scanner import FileInfo, scan_volume

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0


@dataclass
class SyncSummary:
    total_scanned: int = 0
    uploaded_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    duration_seconds: float = 0.0


def send_system_notification(title: str, message: str) -> None:
    """Send a native macOS system notification safely using osascript argv."""
    try:
        script = """
        on run argv
            display notification (item 1 of argv) with title (item 2 of argv)
        end run
        """
        subprocess.run(
            ["osascript", "-e", script, str(message), str(title)],
            capture_output=True,
            timeout=3,
        )
    except Exception as e:
        logger.debug("Failed to send system notification: %s", e)


class SyncCoordinator:
    """Coordinates USB events, file diffing, BaiduPCS-Go execution, and state persistence."""

    def __init__(
        self,
        config: AppConfig,
        db_path: Path | str | None = None,
        engine: BaiduEngine | None = None,
        on_status: Callable[[str], None] | None = None,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> None:
        self.config = config
        self.db = SyncDatabase(db_path=db_path)
        self.engine = engine or BaiduEngine(dry_run=config.dry_run)
        self.on_status = on_status
        self.on_progress = on_progress
        self._listener: USBListener | None = None
        self._is_active = False
        self._current_syncing_mount: str | None = None
        self._abort_event = threading.Event()

    def start(self) -> None:
        """Start listening for USB mount/unmount events."""
        self._is_active = True
        self._listener = USBListener(
            on_mount=self._handle_mount,
            on_unmount=self._handle_unmount,
        )
        self._listener.start()
        if self.on_status:
            self.on_status("🟢 监听就绪 (等待插入U盘)")

    def stop(self) -> None:
        """Stop listening and abort active transfers."""
        self._is_active = False
        if self._listener:
            self._listener.stop()
        if self._current_syncing_mount:
            self._handle_unmount(self._current_syncing_mount)

    def _handle_mount(self, mount_path: str, volume_name: str, volume_uuid: str) -> None:
        """Handle mount notification by dispatching to a background thread to prevent blocking Cocoa run loop."""
        if not self._is_active:
            return
        send_system_notification("USBBaiduSync", f"检测到 U 盘挂载: {volume_name}，开始比对...")
        threading.Thread(
            target=self.sync_volume,
            args=(mount_path, volume_name, volume_uuid),
            daemon=True,
            name=f"SyncWorker-{volume_name}",
        ).start()

    def _handle_unmount(self, mount_path: str) -> None:
        """Handle unmount notification, terminate active upload process, and mark abort."""
        if self._current_syncing_mount and str(mount_path) == str(self._current_syncing_mount):
            logger.warning("Active volume unmounted abruptly: %s", mount_path)
            self._abort_event.set()
            self.engine.abort_current_upload()
            self._current_syncing_mount = None
            if self.on_status:
                self.on_status("⚠️ U盘已拔出，已终止传输")
            send_system_notification("USBBaiduSync", "U 盘已拔出，未完成的上传已安全终止。")

    def sync_volume(
        self,
        mount_path: Path | str,
        volume_name: str,
        volume_uuid: str | None = None,
    ) -> SyncSummary:
        """Execute full incremental sync for a given volume."""
        start_time = time.time()
        mount_p = Path(mount_path)
        self._current_syncing_mount = str(mount_p)
        self._abort_event.clear()

        if not volume_uuid:
            _, volume_uuid, _ = get_volume_metadata(mount_p)

        # 1. Update volume registry
        self.db.upsert_volume(volume_uuid=volume_uuid, volume_name=volume_name, mount_path=str(mount_p))

        if self.on_status:
            self.on_status(f"🔍 正在扫描 U 盘: {volume_name}...")

        # 2. Check credentials if not dry run and bduss configured
        if not self.config.dry_run and self.config.bduss:
            if not self.engine.check_login():
                warning_msg = "⚠️ 百度网盘登录已过期，请在设置中更新 BDUSS"
                logger.warning(warning_msg)
                if self.on_status:
                    self.on_status(warning_msg)
                send_system_notification("USBBaiduSync", "百度网盘登录已过期，请在设置中更新 BDUSS")
                self._current_syncing_mount = None
                return SyncSummary()

        # 3. Scan files
        candidates = scan_volume(mount_p, ignore_patterns=self.config.ignore_patterns)
        summary = SyncSummary(total_scanned=len(candidates))

        if not candidates:
            summary.duration_seconds = time.time() - start_time
            if self.on_status:
                self.on_status(f"🟢 U盘 {volume_name} 无需同步文件")
            self._current_syncing_mount = None
            return summary

        # 4. Two-tier incremental evaluation
        upload_queue: list[FileInfo] = []
        for file_info in candidates:
            if self._abort_event.is_set():
                break

            need_upload, reason = self.db.evaluate_file(
                volume_uuid=volume_uuid,
                rel_path=file_info.rel_path,
                file_path=file_info.abs_path,
                size=file_info.size,
                mtime=file_info.mtime,
            )
            if need_upload:
                upload_queue.append(file_info)
            else:
                summary.skipped_count += 1

        logger.info(
            "Evaluation complete: %d total, %d to upload, %d skipped",
            summary.total_scanned,
            len(upload_queue),
            summary.skipped_count,
        )

        if not upload_queue:
            summary.duration_seconds = time.time() - start_time
            if self.on_status:
                self.on_status(f"✅ 同步完成: 全部 {summary.skipped_count} 个文件均已为最新")
            self._current_syncing_mount = None
            send_system_notification("USBBaiduSync", f"U盘 [{volume_name}] 所有文件均已同步，无需上传。")
            return summary

        # 5. Upload loop with retry and unmount protection
        total_to_upload = len(upload_queue)
        for idx, file_info in enumerate(upload_queue, start=1):
            if self._abort_event.is_set() or not mount_p.exists():
                logger.warning("Upload loop interrupted for volume: %s", volume_name)
                break

            remote_path = resolve_remote_path(
                base_dir=self.config.remote_base_dir,
                volume_name=volume_name,
                rel_path=file_info.rel_path,
            )

            status_msg = f"🔄 正在上传 [{idx}/{total_to_upload}]: {file_info.rel_path}"
            if self.on_status:
                self.on_status(status_msg)
            if self.on_progress:
                self.on_progress(idx, total_to_upload, file_info.rel_path)

            try:
                fast_hash = calculate_fast_hash(file_info.abs_path, file_info.size)
            except (FileNotFoundError, OSError) as e:
                if self._abort_event.is_set() or not mount_p.exists():
                    self.db.record_upload_status(
                        volume_uuid=volume_uuid,
                        rel_path=file_info.rel_path,
                        status="INTERRUPTED",
                        error_msg="Volume unmounted during hash calculation",
                        remote_path=remote_path,
                        file_size=file_info.size,
                        mtime=file_info.mtime,
                    )
                    break
                logger.error("Error hashing file %s: %s", file_info.rel_path, e)
                summary.failed_count += 1
                continue

            # Attempt upload with exponential backoff retry
            result: UploadResult | None = None
            for attempt in range(1, MAX_RETRIES + 1):
                if self._abort_event.is_set():
                    result = UploadResult(success=False, is_interrupted=True)
                    break

                res = self.engine.upload_file(file_info.abs_path, remote_path)
                result = res if isinstance(res, UploadResult) else UploadResult(success=bool(res))

                if result.success:
                    break

                if result.is_auth_error:
                    warning_msg = "⚠️ 百度网盘登录已过期，请在设置中更新 BDUSS"
                    logger.warning(warning_msg)
                    if self.on_status:
                        self.on_status(warning_msg)
                    send_system_notification("USBBaiduSync", "百度网盘登录已过期，请在设置中更新 BDUSS")
                    self._abort_event.set()
                    break

                if result.is_interrupted or self._abort_event.is_set():
                    break

                # Retryable network failure
                if attempt < MAX_RETRIES:
                    backoff = INITIAL_BACKOFF * (2 ** (attempt - 1))
                    logger.info("Upload failed, retrying (%d/%d) in %.1fs...", attempt, MAX_RETRIES, backoff)
                    time.sleep(backoff)

            if not result:
                result = UploadResult(success=False, error_message="Unknown error")

            if result.success:
                self.db.record_upload_success(
                    volume_uuid=volume_uuid,
                    volume_name=volume_name,
                    rel_path=file_info.rel_path,
                    file_size=file_info.size,
                    mtime=file_info.mtime,
                    fast_hash=fast_hash,
                    remote_path=remote_path,
                )
                summary.uploaded_count += 1
            elif result.is_interrupted or self._abort_event.is_set():
                self.db.record_upload_status(
                    volume_uuid=volume_uuid,
                    rel_path=file_info.rel_path,
                    status="INTERRUPTED",
                    error_msg="Upload interrupted by unmount",
                    remote_path=remote_path,
                    file_size=file_info.size,
                    mtime=file_info.mtime,
                    fast_hash=fast_hash,
                )
                break
            else:
                self.db.record_upload_status(
                    volume_uuid=volume_uuid,
                    rel_path=file_info.rel_path,
                    status="FAILED",
                    error_msg=result.error_message or "Upload process failed after retries",
                    remote_path=remote_path,
                    file_size=file_info.size,
                    mtime=file_info.mtime,
                    fast_hash=fast_hash,
                )
                summary.failed_count += 1

        summary.duration_seconds = time.time() - start_time
        self._current_syncing_mount = None

        if self._abort_event.is_set():
            logger.info("Sync aborted. Uploaded %d files before abort.", summary.uploaded_count)
            return summary

        done_msg = f"✅ 同步完成: 新增上传 {summary.uploaded_count} 个，跳过 {summary.skipped_count} 个"
        if summary.failed_count > 0:
            done_msg += f"，失败 {summary.failed_count} 个"

        if self.on_status:
            self.on_status(done_msg)

        send_system_notification(
            "USBBaiduSync",
            f"U盘 [{volume_name}] 增量同步完成！上传: {summary.uploaded_count}，跳过: {summary.skipped_count}",
        )
        return summary
