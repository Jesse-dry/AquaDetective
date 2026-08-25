#!/usr/bin/env python3
"""真实数据异常检测验证:用 processed 太湖数据跑 engine/anomaly 四种方法。

验证逻辑(无标注事件,采用"水质类别一致性"交叉验证):
  引擎检出的中/高严重度异常点,其对应时刻的水质类别(Ⅳ/Ⅴ/劣Ⅴ)占比,
  应显著高于该断面整体的类别占比基线——若一致富集,说明检测在真实数据上有效。

输出:
  data/processed/guokong_taihu/anomaly_validation.json  验证报告
  控制台打印汇总表

用法:python tools/validate_anomaly_real.py [断面数, 默认 8]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data/processed/guokong_taihu"
sys.path.insert(0, str(ROOT / "backend"))

from app.engine.anomaly import detect  # noqa: E402

BAD_CLASSES = {"Ⅳ", "Ⅴ", "劣Ⅴ"}
INDICATORS = ["ammonia_n", "codmn", "do"]
METHODS = ["threesigma", "cusum", "ewma", "seasonal"]


def validate_station(sid: str) -> list[dict]:
    df = pd.read_csv(PROC / "readings" / f"{sid}.csv")
    results = []
    for ind in INDICATORS:
        sub = df.dropna(subset=[ind])
        if len(sub) < 200:
            continue
        x = sub[ind].to_numpy(dtype=float)
        ts = sub["epoch"].to_numpy(dtype=np.int64)
        bad_rate = float(sub["quality_class"].isin(BAD_CLASSES).mean())
        cls = sub["quality_class"].to_numpy()
        for method in METHODS:
            try:
                hits = detect(x, ts, method=method)
            except Exception as exc:  # noqa: BLE001
                results.append({"station": sid, "indicator": ind, "method": method,
                                "error": str(exc)[:80]})
                continue
            sev_idx = [h["idx"] for h in hits if h["severity"] in ("medium", "high")]
            hit_bad = float(np.mean([cls[i] in BAD_CLASSES for i in sev_idx])) if sev_idx else None
            results.append({
                "station": sid, "indicator": ind, "method": method,
                "points": len(x), "detections": len(hits),
                "medium_high": len(sev_idx),
                "detection_rate": round(len(hits) / len(x), 4),
                "bad_class_rate_baseline": round(bad_rate, 4),
                "bad_class_rate_at_detections": round(hit_bad, 4) if hit_bad is not None else None,
            })
    return results


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    stations = pd.read_csv(PROC / "stations.csv")
    top = stations.nlargest(n, "records")["station_id"].tolist()

    rows = []
    for sid in top:
        rows.extend(validate_station(sid))

    valid = [r for r in rows if "error" not in r]
    errors = [r for r in rows if "error" in r]
    per_method: dict[str, dict] = {}
    for m in METHODS:
        sub = [r for r in valid if r["method"] == m]
        enriched = [
            r for r in sub
            if r["bad_class_rate_at_detections"] is not None and r["medium_high"] >= 3
        ]
        agree = sum(
            1 for r in enriched
            if r["bad_class_rate_at_detections"] > r["bad_class_rate_baseline"]
        )
        per_method[m] = {
            "runs": len(sub),
            "total_detections": sum(r["detections"] for r in sub),
            "avg_detection_rate": round(float(np.mean([r["detection_rate"] for r in sub])), 4),
            "consistency_checks": len(enriched),
            "consistency_pass": agree,
            "consistency_pass_rate": round(agree / len(enriched), 3) if enriched else None,
        }

    report = {
        "dataset": "data/processed/guokong_taihu (太湖 105 断面标准化数据, 2021-06~2025-10)",
        "stations_tested": top,
        "indicators": INDICATORS,
        "methods": METHODS,
        "per_method": per_method,
        "errors": errors,
        "detail": valid,
    }
    out = PROC / "anomaly_validation.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print(f"断面: {n} 个(记录最多) × 指标 {INDICATORS} × 方法 {METHODS}")
    print(f"{'方法':<12}{'运行':>4}{'总检出':>8}{'平均检出率':>10}{'一致性通过':>12}")
    for m, s in per_method.items():
        pr = s["consistency_pass_rate"]
        print(f"{m:<12}{s['runs']:>4}{s['total_detections']:>8}"
              f"{s['avg_detection_rate']:>10.2%}"
              f"{str(s['consistency_pass']) + '/' + str(s['consistency_checks']):>8}"
              f"{(' (' + format(pr, '.0%') + ')') if pr is not None else ''}")
    if errors:
        print("错误:", errors)
    print("报告:", out)


if __name__ == "__main__":
    main()
