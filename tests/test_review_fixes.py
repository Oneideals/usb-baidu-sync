"""Tests covering Critical and Important code review findings."""
from pathlib import Path
import unittest.mock as mock
import pytest

from usb_baidu_sync.coordinator import SyncCoordinator, send_system_notification
from usb_baidu_sync.config import AppConfig
from usb_baidu_sync.database import SyncDatabase
from usb_baidu_sync.baidu_engine import BaiduEngine, UploadResult


def test_send_system_notification_escapes_quotes():
    """Verify AppleScript execution handles quotes and special characters safely."""
    with mock.patch("subprocess.run") as mock_run:
        send_system_notification('Title with "quotes" & \\backslashes', 'Message with "quotes"')
        assert mock_run.called
        args, kwargs = mock_run.call_args
        cmd = args[0]
        # Should pass arguments via argv instead of in-string formatting
        assert cmd[0] == "osascript"
        assert 'Message with "quotes"' in cmd
        assert 'Title with "quotes" & \\backslashes' in cmd


def test_unmount_marks_interrupted_and_aborts_promptly(tmp_path):
    """Verify abrupt unmount marks file as INTERRUPTED and halts queue."""
    usb_dir = tmp_path / "mock_usb"
    usb_dir.mkdir()
    (usb_dir / "file1.bin").write_text("content 1")
    (usb_dir / "file2.bin").write_text("content 2")

    cfg = AppConfig(dry_run=False)
    db_file = tmp_path / "sync.db"
    
    mock_engine = mock.MagicMock(spec=BaiduEngine)
    coord = SyncCoordinator(config=cfg, db_path=db_file, engine=mock_engine)

    # When first file uploads, simulate unmount triggered
    def side_effect_upload(local_path, remote_path, progress_cb=None):
        coord._handle_unmount(str(usb_dir))
        return UploadResult(success=False, is_interrupted=True)

    mock_engine.upload_file.side_effect = side_effect_upload

    status_updates = []
    coord.on_status = lambda s: status_updates.append(s)

    summary = coord.sync_volume(mount_path=usb_dir, volume_name="TEST_USB", volume_uuid="UUID-INT")
    
    # Assert second file was NOT attempted
    assert mock_engine.upload_file.call_count == 1
    
    # Assert DB has INTERRUPTED status
    record = coord.db.get_file_record("UUID-INT", "file1.bin")
    assert record is not None
    assert record["upload_status"] == "INTERRUPTED"

    # Assert no "同步完成" in final status
    assert not any("同步完成" in s for s in status_updates[-1:])


def test_auth_expired_halts_upload_queue(tmp_path):
    """Verify expired BDUSS halts upload loop immediately and sets warning."""
    usb_dir = tmp_path / "mock_usb"
    usb_dir.mkdir()
    (usb_dir / "file1.bin").write_text("content 1")
    (usb_dir / "file2.bin").write_text("content 2")

    cfg = AppConfig(dry_run=False, bduss="expired_token")
    db_file = tmp_path / "sync.db"
    
    mock_engine = mock.MagicMock(spec=BaiduEngine)
    mock_engine.check_login.return_value = False
    
    status_updates = []
    coord = SyncCoordinator(
        config=cfg,
        db_path=db_file,
        engine=mock_engine,
        on_status=lambda s: status_updates.append(s),
    )

    summary = coord.sync_volume(mount_path=usb_dir, volume_name="TEST_USB", volume_uuid="UUID-AUTH")
    
    # Should not even attempt upload
    assert mock_engine.upload_file.call_count == 0
    assert any("⚠️" in s and "过期" in s for s in status_updates)
