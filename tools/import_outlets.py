#!/usr/bin/env python3
"""解析许可证平台原始粘贴(TSV)→ 规范化排口表 + 排口-污染物表。

输入:data/interim/taihu_enterprises_v1/outlet_raw.txt
  从许可证"排放许可信息"页直接复制粘贴的表格,两种行式:
  1. 浓度限值行:排放口编号(DWxxx)\t排放口名称\t污染物种类\t浓度限值\t年排放量5列
  2. 主要排放口合计行:"主要排放口合计"\t污染物\t年排放量5列(续行省略前缀,仅污染物+5年)

输出:data/processed/taihu_enterprises/
  outlets.csv              排口级(1 排口 1 行)
  outlet_pollutants.csv    排口×污染物(1 排口×1 污染物 1 行,含 is_major)
  outlets_report.json      导入报告(主要污染物清单/排放指纹)

主要污染物判定:出现在"主要排放口合计"表、年排放量限值非"/"的污染物。
首要污染物 = 主要污染物中年排放量最大者。
污染物代码归一化到 backend 引擎可识别的指标键(COD/NH3N/TP 等)。

用法:python tools/import_outlets.py
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/interim/taihu_enterprises_v1/outlet_raw.txt"
OUT_DIR = ROOT / "data/processed/taihu_enterprises"

# 污染物名称 → 归一化代码(对接 backend/app/engine 指标键)
POLLUTANT_CODE = {
    "化学需氧量": "COD", "化学需氧量": "COD", "codcr": "COD", "cod": "COD",
    "氨氮": "NH3N", "氨氮（nh3-n）": "NH3N", "氨氮(nh3-n)": "NH3N", "nh3-n": "NH3N",
    "总磷": "TP", "总磷（以p计）": "TP", "总磷(以p计)": "TP",
    "总氮": "TN", "总氮（以n计）": "TN", "总氮(以n计)": "TN",
    "悬浮物": "SS", "五日生化需氧量": "BOD5", "bod5": "BOD5",
    "苯胺类": "ANILINE", "可吸附有机卤化物": "AOX", "硫化物": "SULFIDE",
    "色度": "COLOR", "ph值": "PH", "ph": "PH", "总锑": "SB", "二氧化氯": "CLO2",
    "流量": "FLOW", "六价铬": "CR6", "总铬": "CR", "锌": "ZN", "总锌": "ZN",
    "铜": "CU", "总铜": "CU", "镍": "NI", "总镍": "NI", "氰化物": "CN",
    "甲醛": "HCHO", "挥发酚": "VOLPHEN", "石油类": "OIL", "动植物油": "FATOIL",
    "总磷": "TP",
}


def code_of(pollutant: str) -> str:
    """污染物名称归一化为代码。"""
    key = pollutant.strip().lower().replace(" ", "")
    for name, code in POLLUTANT_CODE.items():
        if name in key or key in name:
            return code
    return pollutant.strip()  # 未匹配则原样保留


def parse_concentration(s: str) -> tuple[float | None, str]:
    """从"500mg/L"/"6-9"/"80"/"/"中提取数值与单位。返回(数值, 原文)。"""
    s = s.strip()
    if not s or s == "/":
        return None, s
    # 区间型(如 pH 6-9)
    m = re.match(r"^(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)", s)
    if m:
        return None, s  # 区间不取单值
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if m:
        return float(m.group(1)), s
    return None, s


def parse_annual(fields: list[str]) -> list:
    """解析年排放量5列,把"/"转为 None,数字转 float。"""
    out = []
    for f in fields:
        f = f.strip()
        if not f or f == "/":
            out.append(None)
        else:
            try:
                out.append(float(f))
            except ValueError:
                out.append(None)
    return out


def parse_remarks(path: Path) -> dict[str, str]:
    """从 企业备注.md 解析 {企业名: 许可状态备注}。"""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("无信息"):
            continue
        # 格式:企业名,状态说明
        if "，" in line:
            name, note = line.split("，", 1)
            out[name.strip()] = note.strip()
    return out


def main() -> None:
    lines = [l.rstrip("\n") for l in open(RAW, encoding="utf-8") if l.strip()]
    if not lines:
        print("[!] raw 为空")
        return

    remarks = parse_remarks(ROOT / "企业备注.md")

    outlets: dict[tuple[str, str], dict] = {}  # (credit_code, outlet_code) → 排口信息
    pollutants: list[dict] = []  # 排口×污染物
    major_set: dict[tuple[str, str], list] = {}  # (credit_code, 污染物代码) → 年量5列

    cur_credit = ""        # 当前企业信用代码(由 ### 锚点行设定)
    cur_ent_name = ""
    cur_section = "concentration"  # concentration | summary

    for raw_line in lines:
        cols = raw_line.split("\t")
        cols = [c.strip() for c in cols]
        head = cols[0] if cols else ""

        # 企业锚点行:### 信用代码 企业名
        if head.startswith("###"):
            parts = raw_line.split(maxsplit=2)
            cur_credit = parts[1] if len(parts) > 1 else ""
            cur_ent_name = parts[2].strip() if len(parts) > 2 else ""
            cur_section = "concentration"
            continue

        # 跳过表头
        if head in ("排放口编号", "第一年") or "许可排放浓度限值" in raw_line:
            continue

        # 进入"主要排放口合计"区
        if "合计" in head:
            cur_section = "summary"
            if len(cols) >= 7:
                pol = cols[1]
                annual = parse_annual(cols[2:7])
                code = code_of(pol)
                major_set[(cur_credit, code)] = annual
            continue

        if cur_section == "summary":
            # 续行:污染物 \t 年量×5(省略"合计"前缀)
            if len(cols) >= 6 and cols[0] and not cols[0].startswith("DW"):
                pol = cols[0]
                annual = parse_annual(cols[1:6])
                code = code_of(pol)
                # 必须有至少一个非 None 年量才算主要污染物
                if any(v is not None for v in annual):
                    major_set[(cur_credit, code)] = annual
                summary_pollutant = code
                continue

        # 浓度限值行:DWxxx
        if head.startswith("DW"):
            cur_section = "concentration"
            outlet_code, outlet_name = head, cols[1] if len(cols) > 1 else ""
            pollutant = cols[2] if len(cols) > 2 else ""
            conc_raw = cols[3] if len(cols) > 3 else "/"
            conc_val, _ = parse_concentration(conc_raw)
            code = code_of(pollutant)
            okey = (cur_credit, outlet_code)
            if okey not in outlets:
                outlets[okey] = {
                    "credit_code": cur_credit, "enterprise_name": cur_ent_name,
                    "outlet_code": outlet_code, "outlet_name": outlet_name,
                    "outlet_type": "", "discharge_to": "", "target_water": "",
                }
            pollutants.append({
                "credit_code": cur_credit, "enterprise_name": cur_ent_name,
                "outlet_code": outlet_code, "outlet_name": outlet_name,
                "pollutant": pollutant, "pollutant_code": code,
                "concentration_limit_raw": conc_raw,
                "concentration_limit_value": conc_val,
                "annual_limit_t": None, "year1": None, "year2": None,
                "year3": None, "year4": None, "year5": None,
                "is_major": False,
            })

    # 回填 is_major + 年排放量限值(按 (credit_code, 污染物代码) 匹配合计表)
    for p in pollutants:
        key = (p["credit_code"], p["pollutant_code"])
        if key in major_set:
            annual = major_set[key]
            p["is_major"] = True
            p["year1"], p["year2"], p["year3"], p["year4"], p["year5"] = annual
            p["annual_limit_t"] = annual[0]  # 取第一年(通常五年相同)

    # 排口信息(从浓度限值行汇集)
    outlet_rows = list(outlets.values())
    # 每排口的主要污染物清单
    outlet_major: dict[str, list[str]] = defaultdict(list)
    outlet_first_pollutant: dict[str, float] = {}  # 首要污染物年量
    for p in pollutants:
        if p["is_major"]:
            outlet_major[p["outlet_code"]].append(p["pollutant_code"])
            if p["annual_limit_t"] and p["annual_limit_t"] > outlet_first_pollutant.get(p["outlet_code"], 0):
                outlet_first_pollutant[p["outlet_code"]] = p["annual_limit_t"]
    for o in outlet_rows:
        majors = outlet_major.get(o["outlet_code"], [])
        o["major_pollutants"] = "/".join(majors) if majors else ""

    # ===== 写 outlets.csv =====
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ofields = ["credit_code", "enterprise_name", "outlet_code", "outlet_name",
               "outlet_type", "discharge_to", "target_water",
               "major_pollutants", "remark"]
    with open(OUT_DIR / "outlets.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ofields)
        w.writeheader()
        for o in outlet_rows:
            w.writerow({k: o.get(k, "") for k in ofields})

    # ===== 写 outlet_pollutants.csv =====
    pfields = ["credit_code", "enterprise_name", "outlet_code", "outlet_name",
               "pollutant", "pollutant_code", "concentration_limit_raw",
               "concentration_limit_value", "annual_limit_t",
               "year1", "year2", "year3", "year4", "year5", "is_major"]
    with open(OUT_DIR / "outlet_pollutants.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=pfields)
        w.writeheader()
        for p in pollutants:
            w.writerow({k: p[k] for k in pfields})

    # ===== 报告(按企业聚合) =====
    enterprises = {}
    for (cc, code), annual in major_set.items():
        ent_name = next((p["enterprise_name"] for p in pollutants if p["credit_code"] == cc), "")
        enterprises.setdefault(cc, {"name": ent_name, "major": []})["major"].append(
            {"pollutant_code": code,
             "pollutant_name": next((p["pollutant"] for p in pollutants
                                     if p["credit_code"] == cc and p["pollutant_code"] == code), code),
             "annual_limit_t": annual[0]})
    for cc, d in enterprises.items():
        d["major"].sort(key=lambda x: x["annual_limit_t"] or 0, reverse=True)
        d["primary_pollutant"] = d["major"][0]["pollutant_code"] if d["major"] else None
        d["fingerprint_vector"] = {m["pollutant_code"]: m["annual_limit_t"] for m in d["major"]}
        d["permit_status"] = remarks.get(d["name"], "在业(有许可数据)")

    # 全部锚点企业(含无许可数据的)→ 企业许可状态表
    anchor_ents: dict[str, str] = {}  # cc → name
    for line in lines:
        if line.startswith("###"):
            parts = line.split(maxsplit=2)
            cc = parts[1] if len(parts) > 1 else ""
            nm = parts[2].strip() if len(parts) > 2 else ""
            anchor_ents[cc] = nm
    ent_status_rows = []
    for cc, nm in anchor_ents.items():
        has_data = cc in enterprises
        status = remarks.get(nm, ("在业(有许可数据)" if has_data else "未查到许可数据"))
        ent_status_rows.append({
            "credit_code": cc, "name": nm,
            "has_permit_data": has_data,
            "permit_status": status,
            "primary_pollutant": enterprises[cc]["primary_pollutant"] if has_data else "",
            "major_pollutants": "/".join(m["pollutant_code"] for m in enterprises[cc]["major"]) if has_data else "",
        })

    # 写企业许可状态表
    with open(OUT_DIR / "enterprises_permitted.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["credit_code", "name", "has_permit_data",
                                          "permit_status", "primary_pollutant",
                                          "major_pollutants"])
        w.writeheader()
        for r in ent_status_rows:
            w.writerow(r)

    report = {
        "outlets_count": len(outlet_rows),
        "pollutant_rows": len(pollutants),
        "enterprises_with_data": len(enterprises),
        "enterprises_anchored": len(anchor_ents),
        "enterprises": enterprises,
        "permit_status_table": [f"{r['name']} | {r['permit_status']}" for r in ent_status_rows],
        "notes": "主要污染物=主要排放口合计表中年排放量限值非/的污染物;首要污染物=年排放量最大者;"
                 "fingerprint_vector 可直接对接 backend/app/engine/fingerprint.py match_pollutants。"
                 "raw 文件用 ### 信用代码 企业名 锚点行分隔多家企业;"
                 "无许可数据的企业见 企业备注.md(许可注销/破产/届满未延续)。",
    }
    (OUT_DIR / "outlets_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
