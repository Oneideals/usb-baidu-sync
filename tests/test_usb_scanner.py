from pathlib import Path
from usb_baidu_sync.usb_scanner import scan_volume, FileInfo

def test_scan_volume_filters_ignored(tmp_path):
    (tmp_path / "keep.txt").write_text("hello")
    (tmp_path / ".DS_Store").write_text("trash")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "report.docx").write_text("doc")
    
    files = scan_volume(tmp_path, ignore_patterns=[".DS_Store"])
    rel_paths = [f.rel_path for f in files]
    assert "keep.txt" in rel_paths
    assert "sub/report.docx" in rel_paths
    assert ".DS_Store" not in rel_paths
    
    # Check FileInfo attributes
    keep_file = next(f for f in files if f.rel_path == "keep.txt")
    assert keep_file.size == 5
    assert keep_file.mtime > 0
    assert keep_file.abs_path == tmp_path / "keep.txt"
