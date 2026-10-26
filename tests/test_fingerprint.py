from pathlib import Path
from usb_baidu_sync.fingerprint import calculate_fast_hash

def test_fast_hash_small_file(tmp_path):
    p = tmp_path / "small.txt"
    p.write_text("hello world")
    h1 = calculate_fast_hash(p, p.stat().st_size)
    h2 = calculate_fast_hash(p, p.stat().st_size)
    assert h1 == h2
    assert len(h1) == 32

def test_fast_hash_large_file(tmp_path):
    p = tmp_path / "large.bin"
    # 模拟 > 10MB 文件
    with open(p, "wb") as f:
        f.seek(11 * 1024 * 1024)
        f.write(b"end")
    h = calculate_fast_hash(p, p.stat().st_size)
    assert len(h) == 32
