from pathlib import Path
from usb_baidu_sync.baidu_engine import BaiduEngine

def test_baidu_engine_dry_run_mode(tmp_path):
    engine = BaiduEngine(binary_path="mock", dry_run=True)
    assert engine.check_login() is True
    res = engine.upload_file(tmp_path / "test.txt", "/remote/test.txt")
    assert res is True
