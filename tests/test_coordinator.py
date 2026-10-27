from pathlib import Path
from unittest.mock import MagicMock
from usb_baidu_sync.baidu_engine import UploadResult
from usb_baidu_sync.coordinator import SyncCoordinator, SyncSummary
from usb_baidu_sync.config import AppConfig


def test_coordinator_sync_pipeline(tmp_path):
    usb_dir = tmp_path / "mock_usb"
    usb_dir.mkdir()
    (usb_dir / "file1.txt").write_text("content 1")

    cfg = AppConfig(dry_run=True)
    db_file = tmp_path / "test.db"
    coord = SyncCoordinator(config=cfg, db_path=db_file)

    summary = coord.sync_volume(mount_path=usb_dir, volume_name="TEST_USB", volume_uuid="UUID-999")
    assert summary.total_scanned == 1
    assert summary.uploaded_count == 1
    assert summary.skipped_count == 0
    assert summary.failed_count == 0

    # 第二次触发：全部跳过 (增量生效)
    summary2 = coord.sync_volume(mount_path=usb_dir, volume_name="TEST_USB", volume_uuid="UUID-999")
    assert summary2.total_scanned == 1
    assert summary2.uploaded_count == 0
    assert summary2.skipped_count == 1
    assert summary2.failed_count == 0


def test_coordinator_no_bduss_precheck(tmp_path):
    usb_dir = tmp_path / "mock_usb"
    usb_dir.mkdir()
    (usb_dir / "file1.txt").write_text("content 1")

    # dry_run=False, but bduss is empty and not logged in
    cfg = AppConfig(dry_run=False, bduss="")
    statuses = []
    mock_engine = MagicMock()
    mock_engine.check_login.return_value = False
    coord = SyncCoordinator(
        config=cfg,
        db_path=tmp_path / "test.db",
        engine=mock_engine,
        on_status=lambda s: statuses.append(s),
    )

    summary = coord.sync_volume(mount_path=usb_dir, volume_name="TEST_USB", volume_uuid="UUID-123")
    assert summary.uploaded_count == 0
    assert any("BDUSS" in s for s in statuses)


def test_coordinator_quota_precheck_abort(tmp_path):
    usb_dir = tmp_path / "mock_usb"
    usb_dir.mkdir()
    (usb_dir / "file1.txt").write_text("content 1" * 100)

    cfg = AppConfig(dry_run=True)
    mock_engine = MagicMock()
    # 0 available bytes: used = total
    mock_engine.get_quota.return_value = (1000, 1000)

    statuses = []
    coord = SyncCoordinator(
        config=cfg,
        db_path=tmp_path / "test.db",
        engine=mock_engine,
        on_status=lambda s: statuses.append(s),
    )

    summary = coord.sync_volume(mount_path=usb_dir, volume_name="TEST_USB", volume_uuid="UUID-456")
    assert summary.uploaded_count == 0
    assert mock_engine.upload_file.call_count == 0
    assert any("空间不足" in s for s in statuses)


def test_coordinator_quota_error_immediate_break(tmp_path):
    usb_dir = tmp_path / "mock_usb"
    usb_dir.mkdir()
    (usb_dir / "file1.txt").write_text("content 1")
    (usb_dir / "file2.txt").write_text("content 2")

    cfg = AppConfig(dry_run=True)
    mock_engine = MagicMock()
    # Enough space in precheck
    mock_engine.get_quota.return_value = (0, 10**9)
    # But during upload, first file triggers quota error
    mock_engine.upload_file.return_value = UploadResult(
        success=False,
        is_quota_error=True,
        error_message="errno: 31061 空间不足",
    )

    statuses = []
    coord = SyncCoordinator(
        config=cfg,
        db_path=tmp_path / "test.db",
        engine=mock_engine,
        on_status=lambda s: statuses.append(s),
    )

    summary = coord.sync_volume(mount_path=usb_dir, volume_name="TEST_USB", volume_uuid="UUID-789")
    # Only 1 attempt, then aborted immediately without retrying 3 times or attempting file2
    assert mock_engine.upload_file.call_count == 1
    assert summary.uploaded_count == 0
    assert summary.failed_count == 1
    assert any("空间已满" in s for s in statuses)
