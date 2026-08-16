"""指纹匹配引擎测试。"""
import numpy as np

from app.engine.fingerprint import match_eem, match_pollutants, synthesize_eem

P1 = [{"lex": 320, "lem": 410, "amp": 1.0, "sigma": 20}]
P2 = [{"lex": 280, "lem": 330, "amp": 1.0, "sigma": 20}]


def test_self_match_high():
    eem = synthesize_eem(P1)
    ranked = match_eem(eem, {"a": synthesize_eem(P1), "b": synthesize_eem(P2)})
    assert ranked[0]["enterprise_id"] == "a"
    assert ranked[0]["score"] > 0.99


def test_rank_separation():
    q = synthesize_eem(P1)
    ranked = match_eem(q, {"b": synthesize_eem(P2), "a": synthesize_eem(P1)})
    assert ranked[0]["enterprise_id"] == "a"
    assert ranked[0]["score"] > ranked[1]["score"] + 0.2


def test_match_pollutants():
    lib = {
        "metal": {"cr6": 0.7, "cod": 0.2, "ammonia": 0.1},
        "food": {"cod": 0.8, "ammonia": 0.15, "tp": 0.05},
    }
    ranked = match_pollutants({"cr6": 0.65, "cod": 0.25, "ammonia": 0.1}, lib)
    assert ranked[0]["enterprise_id"] == "metal"
