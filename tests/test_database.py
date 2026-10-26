from pathlib import Path
import time
from usb_baidu_sync.database import SyncDatabase

def test_database_init_and_evaluate(tmp_path):
    db_file = tmp_path / "sync_records.db"
    db = SyncDatabase(db_path=db_file)
    
    # 首次评测：新文件需上传
    test_file = tmp_path / "doc.txt"
    test_file.write_text("content v1")
    stat = test_file.stat()
    
    need_upload, reason = db.evaluate_file(
        volume_uuid="VOL-123",
        rel_path="doc.txt",
        file_path=test_file,
        size=stat.st_size,
        mtime=stat.st_mtime
    )
    assert need_upload is True
    assert reason == "NEW_FILE"
    
    # 模拟上传成功写入
    db.record_upload_success(
        volume_uuid="VOL-123",
        volume_name="KINGSTON",
        rel_path="doc.txt",
        file_size=stat.st_size,
        mtime=stat.st_mtime,
        fast_hash="fakehash1",
        remote_path="/remote/doc.txt"
    )
    
    # 再次评测：元数据未变动则跳过
    need_upload2, reason2 = db.evaluate_file(
        volume_uuid="VOL-123",
        rel_path="doc.txt",
        file_path=test_file,
        size=stat.st_size,
        mtime=stat.st_mtime
    )
    assert need_upload2 is False
    assert reason2 == "METADATA_MATCH"


def test_database_hash_check_on_mtime_change(tmp_path):
    db_file = tmp_path / "sync_records.db"
    db = SyncDatabase(db_path=db_file)

    test_file = tmp_path / "data.bin"
    test_file.write_text("fixed content")
    stat = test_file.stat()

    from usb_baidu_sync.fingerprint import calculate_fast_hash
    real_hash = calculate_fast_hash(test_file, stat.st_size)

    db.record_upload_success(
        volume_uuid="VOL-456",
        volume_name="USB_DISK",
        rel_path="data.bin",
        file_size=stat.st_size,
        mtime=stat.st_mtime - 100,  # 模拟旧 mtime
        fast_hash=real_hash,
        remote_path="/remote/data.bin"
    )

    # mtime 变了，但内容没变 -> Hash 比对一致，跳过上传并更新 mtime
    need_upload, reason = db.evaluate_file(
        volume_uuid="VOL-456",
        rel_path="data.bin",
        file_path=test_file,
        size=stat.st_size,
        mtime=stat.st_mtime
    )
    assert need_upload is False
    assert reason == "HASH_MATCH"
