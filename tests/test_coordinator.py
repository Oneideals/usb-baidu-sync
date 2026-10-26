from pathlib import Path
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
