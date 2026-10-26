from usb_baidu_sync.path_resolver import resolve_remote_path

def test_resolve_remote_path_structure():
    path = resolve_remote_path(
        base_dir="/我的备份/U盘自动备份",
        volume_name="KINGSTON",
        rel_path="photos/2026/trip.jpg",
        date_str="2026-10-26"
    )
    assert path == "/我的备份/U盘自动备份/2026-10-26_KINGSTON/photos/2026/trip.jpg"

def test_resolve_remote_path_clean_slashes():
    path = resolve_remote_path(
        base_dir="我的备份/U盘自动备份/",
        volume_name="My Disk",
        rel_path="/folder/file.pdf",
        date_str="2026-10-26"
    )
    assert path == "/我的备份/U盘自动备份/2026-10-26_My Disk/folder/file.pdf"
