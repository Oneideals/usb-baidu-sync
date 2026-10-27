"""macOS Menu Bar Application for USBBaiduSync."""
from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

try:
    import rumps
except ImportError:
    # Minimal fallback mock for testing environments where rumps / Cocoa display isn't active
    class _MockMenuItem:
        def __init__(self, title: str, callback=None) -> None:
            self.title = title
            self.callback = callback

    class _MockRumpsApp:
        def __init__(self, name: str, title: str | None = None, menu: list | None = None) -> None:
            self.name = name
            self.title = title
            self.menu = menu or []

        def run(self) -> None:
            pass

    class _MockRumpsModule:
        App = _MockRumpsApp
        MenuItem = _MockMenuItem
        separator = "---"

        @staticmethod
        def alert(title, message):
            pass

        @staticmethod
        def Window(message, title, default_text, cancel):
            class _Win:
                def run(self):
                    class _Res:
                        clicked = 0
                        text = default_text
                    return _Res()
            return _Win()

    rumps = _MockRumpsModule()

from usb_baidu_sync.config import AppConfig, ConfigManager
from usb_baidu_sync.coordinator import SyncCoordinator

logger = logging.getLogger(__name__)


class USBBaiduSyncApp(rumps.App):
    """macOS status bar item application managing USB incremental sync to Baidu Netdisk."""

    def __init__(
        self,
        config_path: Path | None = None,
        db_path: Path | None = None,
        dry_run: bool = False,
    ) -> None:
        super().__init__(name="USBBaiduSync", title="💾")
        self.config_manager = ConfigManager(config_path=config_path)
        self.config = self.config_manager.load()
        if dry_run:
            self.config.dry_run = True

        self.status_item = rumps.MenuItem("🟢 监听就绪 (等待插入U盘)")
        self.last_sync_item = rumps.MenuItem("上次同步: 无记录")
        self.manual_sync_btn = rumps.MenuItem("▶️ 立即扫描已连接 U 盘", callback=self.on_manual_sync)
        self.toggle_listen_btn = rumps.MenuItem("⏸️ 暂停自动监听", callback=self.on_toggle_listen)

        self.remote_dir_btn = rumps.MenuItem("📂 百度网盘目标目录...", callback=self.on_set_remote_dir)
        self.bduss_btn = rumps.MenuItem("🔑 设置百度网盘凭证 (BDUSS)...", callback=self.on_set_bduss)
        self.dry_run_btn = rumps.MenuItem(
            f"🧪 模拟运行模式 (Dry-Run: {'开' if self.config.dry_run else '关'})",
            callback=self.on_toggle_dry_run,
        )

        self.menu = [
            self.status_item,
            self.last_sync_item,
            rumps.separator,
            self.manual_sync_btn,
            self.toggle_listen_btn,
            rumps.separator,
            self.remote_dir_btn,
            self.bduss_btn,
            self.dry_run_btn,
            rumps.separator,
            rumps.MenuItem("📜 打开数据与日志目录", callback=self.on_open_logs),
        ]

        self.coordinator = SyncCoordinator(
            config=self.config,
            db_path=db_path,
            on_status=self.update_status,
            on_progress=self.update_progress,
        )
        self._is_paused = False

    def update_status(self, text: str) -> None:
        """Thread-safe UI status update."""
        self.status_item.title = text
        if "正在" in text:
            self.title = "🔄"
        elif "⚠️" in text:
            self.title = "⚠️"
        else:
            self.title = "💾"

    def update_progress(self, current: int, total: int, filename: str) -> None:
        self.status_item.title = f"🔄 传输中 [{current}/{total}]: {Path(filename).name}"

    def on_toggle_listen(self, sender) -> None:
        self._is_paused = not self._is_paused
        if self._is_paused:
            self.coordinator.stop()
            self.toggle_listen_btn.title = "▶️ 恢复自动监听"
            self.update_status("⏸️ 监听已暂停")
        else:
            self.coordinator.start()
            self.toggle_listen_btn.title = "⏸️ 暂停自动监听"
            self.update_status("🟢 监听就绪 (等待插入U盘)")

    def on_manual_sync(self, sender) -> None:
        """Trigger scan and sync across all mounted /Volumes/."""
        threading.Thread(target=self._manual_sync_worker, daemon=True).start()

    def _manual_sync_worker(self) -> None:
        from usb_baidu_sync.usb_listener import get_volume_metadata
        volumes_dir = Path("/Volumes")
        if not volumes_dir.exists():
            return

        found = 0
        for entry in volumes_dir.iterdir():
            if entry.is_dir():
                name, uuid, is_ext = get_volume_metadata(entry)
                if is_ext:
                    found += 1
                    self.coordinator.sync_volume(mount_path=entry, volume_name=name, volume_uuid=uuid)

        if found == 0:
            self.update_status("🟢 未检测到外部 U 盘")

    def on_set_remote_dir(self, sender) -> None:
        window = rumps.Window(
            message="输入百度网盘存放备份的基础目录：",
            title="设置网盘目录",
            default_text=self.config.remote_base_dir,
            cancel="取消",
        )
        response = window.run()
        if response.clicked and response.text.strip():
            new_dir = response.text.strip()
            self.config_manager.update({"remote_base_dir": new_dir})
            self.config.remote_base_dir = new_dir
            rumps.alert("保存成功", f"网盘目标目录已更新为：{new_dir}")

    def on_set_bduss(self, sender) -> None:
        window = rumps.Window(
            message="请输入百度网盘账号的 Cookie (BDUSS)：",
            title="绑定百度网盘账号",
            default_text=self.config.bduss,
            cancel="取消",
        )
        response = window.run()
        if response.clicked and response.text.strip():
            new_bduss = response.text.strip()
            self.config_manager.update({"bduss": new_bduss})
            self.config.bduss = new_bduss
            # Test login
            success = self.coordinator.engine.login_with_bduss(new_bduss)
            if success:
                quota = self.coordinator.engine.get_quota()
                if quota and isinstance(quota, (tuple, list)) and len(quota) == 2:
                    used_gb = quota[0] / (1024**3)
                    total_gb = quota[1] / (1024**3)
                    rumps.alert("绑定成功", f"百度网盘账号已验证并成功登录！\n网盘空间：已用 {used_gb:.1f}GB / 总计 {total_gb:.1f}GB")
                else:
                    rumps.alert("绑定成功", "百度网盘账号已验证并成功登录！")
            else:
                rumps.alert("验证提示", "已保存 BDUSS，如需完整功能请确保 BaiduPCS-Go 可执行文件已安装。")

    def on_toggle_dry_run(self, sender) -> None:
        self.config.dry_run = not self.config.dry_run
        self.config_manager.update({"dry_run": self.config.dry_run})
        self.coordinator.engine.dry_run = self.config.dry_run
        sender.title = f"🧪 模拟运行模式 (Dry-Run: {'开' if self.config.dry_run else '关'})"

    def on_open_logs(self, sender) -> None:
        app_dir = Path.home() / "Library" / "Application Support" / "USBBaiduSync"
        app_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(app_dir)])

    def start_app(self) -> None:
        """Start the background coordinator and launch the menu bar run loop."""
        self.coordinator.start()
        self.run()
