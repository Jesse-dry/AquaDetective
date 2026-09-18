"""侦探推理流的文案：内部编码不得出现在用户可见文本里。"""
from app.agents.investigator import parse_event
from app.data.watershed_builder import build_watershed


def _event(etype: str) -> dict:
    return {"id": "evt_scan_001", "station_id": "st_02",
            "indicators": '["cr6","cod"]', "onset_ts": 1743350400,
            "severity": "high", "etype": etype, "truth_source": None,
            "status": "open", "affected_stations": None}


def _reasoning(etype: str) -> str:
    state = {"event": _event(etype), "stream": []}
    step = parse_event(state, None, "unused.db", build_watershed())["stream"][-1]["data"]
    return step["reasoning"]


def test_detected_event_does_not_leak_raw_code():
    """监测自动检出的事件(etype=detected)类型未知,不得写成"疑似「detected」"。"""
    text = _reasoning("detected")
    assert "detected" not in text
    assert "待定" in text


def test_known_etype_uses_chinese_name():
    text = _reasoning("periodic")
    assert "夜间偷排" in text
    assert "periodic" not in text


def test_unknown_etype_does_not_leak_raw_code():
    """将来新增的类型编码同样不能原样抛给用户。"""
    text = _reasoning("some_new_kind")
    assert "some_new_kind" not in text
    assert "待定" in text
