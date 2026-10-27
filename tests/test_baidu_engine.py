from pathlib import Path
from unittest.mock import MagicMock, patch
from usb_baidu_sync.baidu_engine import BaiduEngine, UploadResult, parse_quota_output


def test_baidu_engine_dry_run_mode(tmp_path):
    engine = BaiduEngine(binary_path="mock", dry_run=True)
    assert engine.check_login() is True
    res = engine.upload_file(tmp_path / "test.txt", "/remote/test.txt")
    assert res.success is True
    quota = engine.get_quota()
    assert quota is not None
    used, total = quota
    assert used < total


def test_parse_quota_output():
    # Case 1: Standard BaiduPCS-Go text output
    out1 = "用户名: testuser, 总空间: 2.00TB, 已用空间: 1.00TB, 比率: 50.00%"
    q1 = parse_quota_output(out1)
    assert q1 is not None
    used, total = q1
    assert total == 2 * 1024**4
    assert used == 1 * 1024**4

    # Case 2: Output with byte counts in parentheses
    out2 = "总空间: 2.05TB (2200000000000 B)\n已用空间: 1.10TB (1100000000000 B)"
    q2 = parse_quota_output(out2)
    assert q2 is not None
    assert q2[0] == 1100000000000
    assert q2[1] == 2200000000000

    # Case 3: Empty / unrecognized
    assert parse_quota_output("error: not logged in") is None


def test_upload_storage_full_detection(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")

    engine = BaiduEngine(binary_path="/usr/local/bin/BaiduPCS-Go", dry_run=False)

    mock_proc = MagicMock()
    mock_proc.stdout = ["上传文件失败", "远程错误: errno: 31061, 文件已经超出网盘空间容量"]
    mock_proc.wait.return_value = None
    mock_proc.returncode = 1

    with patch("subprocess.Popen", return_value=mock_proc):
        result = engine.upload_file(test_file, "/remote/test.txt")
        assert result.success is False
        assert result.is_quota_error is True
        assert result.is_auth_error is False
