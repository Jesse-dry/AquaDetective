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


def test_observed_pollutants_match_the_library_used_by_investigation():
    """现场观测必须与调查侧比对用的库同源。

    调查走 rank_pollutants,它用的是"注入真实许可证后"的库(_injected_pollutant_lib);
    若观测仍由合成指纹生成,真凶在污染物通道会排到末位 —— 实测彩云印染厂
    (合成 cod .77/ammonia .13/cr6 .045,注入后 {ammonia: 1.0})排 18 家里的第 17,
    溯源被判给别家。EEM 通道两侧都用合成谱,一直自洽,可作对照。
    """
    from app.data.watershed_builder import build_watershed
    from app.data.fingerprint_lib import observed_pollutants, rank_pollutants

    ws = build_watershed()
    for src in ("ent_04", "ent_09", "ent_02"):
        obs = observed_pollutants(ws, "st_09", seed=43, event_source=src)
        ranked = rank_pollutants(obs, ws)
        rank = next(i for i, r in enumerate(ranked, 1) if r["enterprise_id"] == src)
        assert rank <= 2, f"{src} 在污染物通道排第 {rank} 名,现场观测与库不同源"
        assert ranked[0]["score"] > 0.9, "同源样本相似度应接近 1"
