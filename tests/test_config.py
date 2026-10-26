from pathlib import Path
from usb_baidu_sync.config import ConfigManager

def test_default_config_generated(tmp_path):
    config_file = tmp_path / "config.json"
    manager = ConfigManager(config_path=config_file)
    cfg = manager.load()
    assert cfg.remote_base_dir == "/我的备份/U盘自动备份"
    assert ".DS_Store" in cfg.ignore_patterns
    assert cfg.dry_run is False
    assert config_file.exists()

def test_config_update(tmp_path):
    config_file = tmp_path / "config.json"
    manager = ConfigManager(config_path=config_file)
    manager.update({"remote_base_dir": "/自定义目录", "bduss": "test_token"})
    cfg = manager.load()
    assert cfg.remote_base_dir == "/自定义目录"
    assert cfg.bduss == "test_token"
