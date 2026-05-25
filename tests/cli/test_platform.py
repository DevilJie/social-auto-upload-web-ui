from cli.platform import resolve_platform, PLATFORM_NAMES, PLATFORM_KEYS


def test_resolve_by_key():
    assert resolve_platform("douyin") == 3
    assert resolve_platform("xiaohongshu") == 1
    assert resolve_platform("bilibili") == 5


def test_resolve_by_name():
    assert resolve_platform("抖音") == 3
    assert resolve_platform("小红书") == 1
    assert resolve_platform("B站") == 5


def test_resolve_case_insensitive():
    assert resolve_platform("DouYin") == 3
    assert resolve_platform("BILIBILI") == 5


def test_resolve_invalid():
    assert resolve_platform("nonexistent") is None


def test_platform_names_complete():
    assert len(PLATFORM_NAMES) == 10
    assert all(isinstance(k, int) for k in PLATFORM_NAMES)
    assert all(isinstance(v, str) for v in PLATFORM_NAMES.values())


def test_platform_keys_complete():
    assert len(PLATFORM_KEYS) == 10
    assert all(isinstance(v, str) for v in PLATFORM_KEYS.values())
