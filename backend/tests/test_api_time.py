"""公开 API 时间戳单位契约测试。"""
from app.api.time import epoch_ms, epoch_seconds


def test_epoch_conversion_boundary():
    assert epoch_ms(1_755_475_200) == 1_755_475_200_000
    assert epoch_ms(None) is None
    assert epoch_seconds(1_755_475_200_999) == 1_755_475_200
    assert epoch_seconds(None) == 0
