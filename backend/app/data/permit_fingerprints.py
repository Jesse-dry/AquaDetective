"""真实许可证指纹库:从排口级许可证数据提取企业排放指纹。

数据源:data/processed/taihu_enterprises/outlets_report.json
  - 由 tools/import_outlets.py 从许可证平台原始粘贴解析得到
  - fingerprint_vector = {污染物代码: 年排放量限值 t/a}(仅主要污染物)

铁律:本模块只做数据加载与键名归一化,不产生数值;相似度计算仍走
backend/app/engine/fingerprint.py match_pollutants(纯函数)。

污染物代码归一化(许可证代码 → 引擎指标键,与 watershed_config 对齐):
  COD → cod, NH3N → ammonia, TP → tp, TN → tn, CR6 → cr6
"""
from __future__ import annotations

import json
from pathlib import Path

# 许可证污染物代码 → watershed_config 指标键
CODE_TO_INDICATOR = {
    "COD": "cod", "NH3N": "ammonia", "TP": "tp", "TN": "tn",
    "CR6": "cr6", "SS": "ss", "BOD5": "bod5",
}

# 行业归一化(许可证 industry_cn → watershed industry 键)
INDUSTRY_MAP = {
    "染色": "dyeing", "印染": "dyeing", "漂染": "dyeing", "纺织染整": "dyeing",
    "化工": "chemical", "化工/颜料": "chemical", "化工/锆制品": "chemical",
    "制药": "pharma", "化学制药": "pharma", "生物科技/化工": "pharma",
    "造纸": "paper",
    "污水处理厂": "wwtp",
    "金属表面处理": "electroplating", "热镀锌/金属表面处理": "electroplating",
    "喷涂/表面处理": "electroplating",
}

ROOT = Path(__file__).resolve().parent.parent.parent.parent
REPORT_PATH = ROOT / "data/processed/taihu_enterprises/outlets_report.json"


def _load_report() -> dict:
    if not REPORT_PATH.exists():
        return {}
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def real_fingerprint_by_credit(credit_code: str) -> dict[str, float]:
    """按信用代码取真实指纹向量(引擎指标键,归一化比例)。

    返回 {indicator: proportion},和为 1(与 watershed fingerprint.pollutants 同形)。
    None 年量剔除;若全为 None 退化为等权。
    """
    rep = _load_report()
    ent = rep.get("enterprises", {}).get(credit_code)
    if not ent:
        return {}
    vec = {CODE_TO_INDICATOR.get(k, k.lower()): v
           for k, v in ent.get("fingerprint_vector", {}).items()
           if v is not None}
    total = sum(vec.values())
    if total <= 0:
        # 无年量数据,用主要污染物代码等权
        codes = [CODE_TO_INDICATOR.get(m["pollutant_code"], m["pollutant_code"].lower())
                 for m in ent.get("major", []) if m.get("pollutant_code")]
        if not codes:
            return {}
        vec = {c: 1.0 for c in codes}
        total = sum(vec.values())
    return {k: round(v / total, 4) for k, v in vec.items()}


def real_fingerprints_by_name() -> dict[str, dict[str, float]]:
    """{企业名: 指纹向量} 全表(按企业名索引,供映射层使用)。"""
    rep = _load_report()
    out = {}
    for cc, d in rep.get("enterprises", {}).items():
        vec = real_fingerprint_by_credit(cc)
        if vec:
            out[d["name"]] = vec
    return out


def real_fingerprints_by_industry() -> dict[str, list[dict]]:
    """{industry: [{name, credit_code, fingerprint, primary}]} 按行业分组。

    供映射层把真实指纹注入合成流域(按行业匹配合成企业)。
    """
    rep = _load_report()
    by_ind: dict[str, list[dict]] = {}
    for cc, d in rep.get("enterprises", {}).items():
        ind_cn = ""
        # 从 enterprises_permitted.csv 不便;这里用 outlets_report 无 industry,
        # 从 v2 企业表读行业
        pass
    # 行业信息在 v2 表,这里返回 name 索引,映射层自行匹配
    return {"_all": [{"name": d["name"], "credit_code": cc,
                      "fingerprint": real_fingerprint_by_credit(cc),
                      "primary": d.get("primary_pollutant")}
                     for cc, d in rep.get("enterprises", {}).items()
                     if real_fingerprint_by_credit(cc)]}


if __name__ == "__main__":
    fp = real_fingerprints_by_name()
    print(f"真实指纹企业数: {len(fp)}")
    for name, vec in list(fp.items())[:5]:
        print(f"  {name[:24]:26s} {vec}")
