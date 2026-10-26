from usb_baidu_sync.menu_bar import USBBaiduSyncApp

def test_menu_bar_initial_state(tmp_path):
    config_file = tmp_path / "config.json"
    db_file = tmp_path / "sync.db"
    app = USBBaiduSyncApp(config_path=config_file, db_path=db_file, dry_run=True)
    assert app.title == "💾"
    assert "监听就绪" in app.status_item.title

def test_menu_bar_status_update(tmp_path):
    config_file = tmp_path / "config.json"
    db_file = tmp_path / "sync.db"
    app = USBBaiduSyncApp(config_path=config_file, db_path=db_file, dry_run=True)
    app.update_status("🔄 正在上传 [1/5]: test.png")
    assert "正在上传" in app.status_item.title
