from usb_baidu_sync.ignore_rules import is_ignored

def test_is_ignored_mac_metadata():
    assert is_ignored(".DS_Store") is True
    assert is_ignored("subfolder/._image.png") is True
    assert is_ignored(".Spotlight-V100/Store.db") is True
    assert is_ignored("photos/family.jpg") is False
