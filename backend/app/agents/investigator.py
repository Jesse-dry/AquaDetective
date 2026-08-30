"""溯源 Agent（侦探主编排）：事件解析 → 假设生成 → 工具验证 → 排除/锁定。

节点函数签名为 (state, llm, db_path, ws) -> dict(部分状态更新)，由 graph.py 闭包绑定。
所有数值判定来自 tools（确定性引擎），LLM 仅用于假设排序与推理表述（失败自动降级模板）。
"""
from __future__ import annotations

import json

from ..api.time import epoch_ms
from . import tools

MAX_ROUNDS = 3
W = {"eem": 0.40, "pollutant": 0.25, "pattern": 0.20, "strength": 0.15}

# 通俗化标签:面向普通观众的中文映射(只影响展示文本,不影响数值逻辑)
INDICATOR_CN = {"cod": "化学需氧量", "ammonia": "氨氮", "tp": "总磷", "cr6": "六价铬",
                "ph": "pH值", "do": "溶解氧", "codmn": "高锰酸盐指数"}
ETYPE_CN = {"sudden": "突发泄漏", "periodic": "夜间偷排", "gradual": "逐渐恶化"}
SEVERITY_CN = {"high": "严重(需立即处置)", "medium": "中等(持续关注)", "low": "轻微(等结果)"}


def _indicators_cn(ev: dict) -> str:
    """指标编码列表 → 中文逗号串。"""
    inds = _indicators(ev)
    return "、".join(INDICATOR_CN.get(i, i) for i in inds) or "未知指标"


def _station_cn(ws: dict, station_id: str) -> str:
    """st_02 → 2号断面。"""
    import re
    m = re.match(r"^st_?0*(\d+)$", station_id, re.I)
    return f"{int(m[1])}号断面" if m else station_id


def _indicators(ev: dict) -> list[str]:
    """events.indicators 可能是 JSON 字符串或列表，统一返回列表。"""
    v = ev.get("indicators")
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            v = [v]
    return v or []


def _station_of(ws: dict, station_id: str) -> dict:
    return next(s for s in ws["stations"] if s["id"] == station_id)


def parse_event(state: dict, llm, db_path: str, ws: dict) -> dict:
    ev = state["event"]
    st = _station_of(ws, ev["station_id"])
    # 通俗化文本(我的)+ epoch_ms 转 evidence(队友的),两者合并
    inds_cn = _indicators_cn(ev)
    station_cn = _station_cn(ws, ev["station_id"])
    etype_cn = ETYPE_CN.get(ev["etype"], ev["etype"])
    sev_cn = SEVERITY_CN.get(ev["severity"], ev["severity"])
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(hours=8))
    onset_cn = datetime.fromtimestamp(int(ev["onset_ts"]), tz=tz).strftime("%m月%d日 %H:%M")
    event_evidence = {
        k: ev.get(k) for k in ("id", "station_id", "indicators", "severity", "etype")
    }
    event_evidence["onset_ts"] = epoch_ms(ev.get("onset_ts"))
    stream = list(state["stream"])
    stream.append({"type": "step", "data": {
        "step_id": "parse", "phase": "事件解析",
        "clue": f"{station_cn} 检出异常：{inds_cn}",
        "reasoning": f"异常类型疑似「{etype_cn}」，严重度「{sev_cn}」，"
                     f"首达时间 {onset_cn}。开始排查上游污染源。",
        "evidence": [{"kind": "event", "value": event_evidence}],
        "status": "verified"}})
    return {"stream": stream}


def _template_ranking(candidates: list[dict], ev: dict) -> list[dict]:
    """无 LLM 时的假设排序模板：衰减 × 事件类型启发。"""
    etype = ev.get("etype", "detected")
    scored = []
    for i, c in enumerate(candidates[:6]):
        s = c["atten"]
        bonus = 0.0
        if etype == "periodic":
            bonus = 0.15  # 偷排偏好：由规律分析进一步确认
        elif etype == "gradual":
            bonus = 0.10
        scored.append({**c, "score": round(min(0.6, s * 50 + bonus + 0.25 - i * 0.02), 3)})
    return sorted(scored, key=lambda r: r["score"], reverse=True)


def generate_hypotheses(state: dict, llm, db_path: str, ws: dict) -> dict:
    ev = state["event"]
    candidates = tools.trace_upstream(db_path, ws, ev["station_id"])
    if not candidates:
        stream = list(state["stream"])
        stream.append({"type": "failed", "data": {
            "reason": "该断面上游未发现注册企业", "suggestions": ["建议增设监测断面"]}})
        return {"hypotheses": [], "stream": stream, "done": True}

    ranked = _template_ranking(candidates, ev)
    # 尝试 LLM 精排（失败/不可用则保持模板结果）
    if llm and llm.available:
        try:
            data = llm.chat_json([
                {"role": "system", "content": "你是水污染溯源专家。根据事件信息给出嫌疑企业排序，"
                                              "返回 JSON: {\"hypotheses\": [{\"enterprise_id\": ..., "
                                              "\"reasons\": \"...\"}]}，最多 4 个。"},
                {"role": "user", "content": f"事件: {ev.get('etype')} 于断面 {ev['station_id']} 检出 "
                                            f"{ev.get('indicators')}，严重度 {ev.get('severity')}。"
                                            f"候选: {[c['enterprise_id'] for c in candidates[:8]]}"},
            ])
            if data and data.get("hypotheses"):
                order = {h["enterprise_id"]: h.get("reasons", "") for h in data["hypotheses"]}
                ranked = sorted(ranked, key=lambda r: (r["enterprise_id"] in order, -r["score"]),
                                reverse=True)
                ranked = [dict(r, llm_reasons=order.get(r["enterprise_id"], "")) for r in ranked]
        except Exception:
            pass

    hypotheses = []
    stream = list(state["stream"])
    for i, c in enumerate(ranked[:4]):
        h = {
            "id": f"h{i+1}", "target_id": c["enterprise_id"], "target_name": c["name"],
            "industry": c["industry"], "reasons": f"位于上游，衰减系数 {c['atten']:.5f}"
                                                  + c.get("llm_reasons", ""),
            "score": c["score"], "evidence": [], "status": "candidate",
        }
        hypotheses.append(h)
        stream.append({"type": "hypothesis", "data": {
            "id": h["id"], "target": h["target_name"], "industry": h["industry"],
            "reasons": h["reasons"], "score": h["score"], "status": "candidate"}})
    return {"hypotheses": hypotheses, "stream": stream}


def _check_eem(state, h, ev, db_path, ws) -> tuple[float | None, dict]:
    ranked = tools.match_eem_at(db_path, ws, ev["station_id"], ev.get("id"))
    entry = next((r for r in ranked if r["enterprise_id"] == h["target_id"]), None)
    if entry is None:
        return None, {}
    top = ranked[0]
    return entry["score"], {
        "kind": "eem_score", "target": h["target_name"], "value": entry["score"],
        "rank": next(i for i, r in enumerate(ranked) if r["enterprise_id"] == h["target_id"]) + 1,
        "top": top["enterprise_id"],
        "detail": f"现场荧光指纹与指纹库比对：相似度 {entry['cosine']:.1%}（余弦），"
                  f"相关性 {entry['pearson']:.1%}（皮尔逊）"}


def _check_pollutant(state, h, ev, db_path, ws) -> tuple[float | None, dict]:
    ranked = tools.match_pollutants_at(db_path, ws, ev["station_id"], ev.get("id"))
    entry = next((r for r in ranked if r["enterprise_id"] == h["target_id"]), None)
    if entry is None:
        return None, {}
    return entry["score"], {
        "kind": "pollutant_score", "target": h["target_name"], "value": entry["score"],
        "detail": "特征污染物比例向量比对（相似度越高越同源）"}


def _check_pattern(state, h, ev, db_path, ws) -> tuple[float | None, dict]:
    if ev.get("etype") != "periodic":
        return None, {}
    ent = tools.get_enterprise_profile(ws, h["target_id"])
    if not ent:
        return None, {}
    since = int(ev["onset_ts"]) - 7 * 86400
    # 昼夜规律用事件自身的指标分析(此前硬编码 cr6,非 cr6 事件的规律证据会失效)
    inds = tools.parse_indicators(ev) or ["cod"]
    pat = tools.periodicity_at(db_path, ws, ev["station_id"], inds[0], since)
    pat_hours = set(int(x) for x in pat.get("active_hours", []))
    active = ent["discharge_pattern"].get("active_hours", [0, 24])
    exp = set(range(int(active[0]), 24)) | set(range(0, int(active[1]))) if active[0] > active[1] \
        else set(range(int(active[0]), int(active[1])))
    inter = len(pat_hours & exp) / max(len(exp | pat_hours), 1)
    score = round(min(1.0, inter * pat.get("strength", 0.0)
                      + 0.1 * pat.get("night_share", 0.0)), 3)
    return score, {"kind": "pattern_score", "target": h["target_name"], "value": score,
                   "detail": f"断面活跃时段 {pat.get('active_hours')} vs 企业排班 "
                             f"{active}，夜排占比 {pat.get('night_share')}"}


def _check_strength(state, h, ev, db_path, ws) -> tuple[float | None, dict]:
    if ev.get("etype") != "sudden":
        return None, {}
    st = _station_of(ws, ev["station_id"])
    ent = tools.get_enterprise_profile(ws, h["target_id"])
    if not ent:
        return None, {}
    travel = tools.travel_hours(ws, ent["node_id"], st["node_id"])
    if travel is None:
        return None, {}
    # 距断面传播时间越短越可疑（突发事件的源在时间窗内可达）
    score = round(max(0.0, 1.0 - travel / 12.0), 3)
    return score, {"kind": "strength_score", "target": h["target_name"], "value": score,
                   "detail": f"传播时间约 {travel}h（12h 时间窗内越近越可疑）"}


def verify_hypotheses(state: dict, llm, db_path: str, ws: dict) -> dict:
    ev = state["event"]
    hypotheses = list(state["hypotheses"])
    stream = list(state["stream"])
    rnd = int(state.get("round", 1))
    for h in hypotheses:
        if h["status"] != "candidate":
            continue
        checks = [(_check_eem, "eem"), (_check_pollutant, "pollutant"),
                  (_check_pattern, "pattern"), (_check_strength, "strength")]
        scored_pairs: list[tuple[float, float]] = []
        for fn, wkey in checks:
            s, evd = fn(state, h, ev, db_path, ws)
            if s is None:
                continue
            scored_pairs.append((s, W[wkey]))
            h["evidence"].append(evd)
            stream.append({"type": "step", "data": {
                "step_id": f"{h['id']}_{wkey}", "phase": f"证据校核·{wkey}",
                "clue": evd.get("detail", ""), "reasoning": f"嫌疑企业：{h['target_name']}",
                "evidence": [evd], "status": "verified"}})
        if scored_pairs:
            weight_sum = sum(w for _, w in scored_pairs)
            h["score"] = round(min(1.0, sum(s * w for s, w in scored_pairs) / weight_sum), 3)
        if h["score"] < 0.3:
            h["status"] = "rejected"
            stream.append({"type": "step", "data": {
                "step_id": f"{h['id']}_drop", "phase": "排除假设",
                "clue": f"{h['target_name']} 综合得分 {h['score']} 低于阈值",
                "reasoning": "证据不足，予以排除", "evidence": h["evidence"], "status": "rejected"}})
        stream.append({"type": "hypothesis", "data": {
            "id": h["id"], "target": h["target_name"], "score": h["score"],
            "status": h["status"]}})
    best = max((h for h in hypotheses if h["status"] == "candidate"), key=lambda h: h["score"],
               default=None)
    done = (best is not None and best["score"] >= 0.7) or rnd >= MAX_ROUNDS or best is None
    return {"hypotheses": hypotheses, "stream": stream, "round": rnd + 1, "done": done}


def conclude(state: dict, llm, db_path: str, ws: dict) -> dict:
    hypotheses = state["hypotheses"]
    stream = list(state["stream"])
    best = max((h for h in hypotheses if h["status"] == "candidate"), key=lambda h: h["score"],
               default=None)
    if best and best["score"] >= 0.6:
        conclusion = {
            "source_id": best["target_id"], "source_name": best["target_name"],
            "industry": best["industry"], "confidence": best["score"],
            "status": "resolved",
            "evidence_summary": f"综合 EEM 指纹、污染物谱、排放规律等 {len(best['evidence'])} 项证据，"
                                f"锁定 {best['target_name']}（置信度 {best['score']:.0%}）",
        }
        stream.append({"type": "conclusion", "data": conclusion})
    else:
        conclusion = {
            "source_id": None, "source_name": None, "confidence": 0.0, "status": "failed",
            "reason": "所有候选企业综合得分均低于锁定阈值（指纹匹配度不足）",
            "suggestions": ["建议在可疑支流增设临时监测断面", "建议加密采样做荧光全谱分析",
                            "建议联合生态环境部门开展暗管排查"],
        }
        stream.append({"type": "failed", "data": conclusion})
    return {"conclusion": conclusion, "stream": stream}
