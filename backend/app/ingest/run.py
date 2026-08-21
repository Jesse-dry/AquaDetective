"""美国公开基准数据导入器入口。

把四类原始数据映射到统一 schema，输出标准化 CSV 到 data/processed/cuyahoga/，
并生成数据质量报告。

运行（仓库根目录）：
    backend/.venv/Scripts/python.exe -m app.ingest.run
或直接：
    backend/.venv/Scripts/python.exe backend/app/ingest/run.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import mappers, schema

ROOT = Path(__file__).resolve().parents[3]  # backend/app/ingest/run.py -> 仓库根
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
OUT = PROCESSED / "cuyahoga"


def build_parameters() -> pd.DataFrame:
    rows = []
    for name, code in schema.WQP_PARAM_MAP.items():
        rows.append({"parameter_code": code, "source": "wqp", "original_name": name})
    for orig, code in schema.USGS_PARAM_MAP.items():
        rows.append({"parameter_code": code, "source": "usgs", "original_name": orig})
    for name, code in schema.ECHO_PARAM_MAP.items():
        rows.append({"parameter_code": code, "source": "echo", "original_name": name})
    return pd.DataFrame(rows).sort_values(["source", "parameter_code"])


def build_datasets() -> pd.DataFrame:
    rows = []
    for f in sorted((ROOT / "metadata").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        rows.append(
            {
                "dataset_id": d["dataset_id"],
                "name": d["name"],
                "provider": d["provider"],
                "source_url": d.get("source_url", ""),
                "license": d.get("license", ""),
                "retrieved_at": d.get("retrieved_at", ""),
                "region": d.get("region", ""),
                "time_range_start": d.get("time_range", [None, None])[0],
                "time_range_end": d.get("time_range", [None, None])[1],
                "frequency": d.get("frequency", ""),
            }
        )
    return pd.DataFrame(rows)[schema.DATASET_COLUMNS]


def _table(df: pd.DataFrame | pd.Series) -> str:
    return "```\n" + df.to_string() + "\n```"


def write_report(obs: pd.DataFrame, sites: pd.DataFrame, flow: pd.DataFrame,
                 sources: pd.DataFrame, dmr: pd.DataFrame, viol: pd.DataFrame) -> str:
    lines = ["# Cuyahoga HUC8 公开数据 · 数据质量报告", ""]
    lines += [f"- 生成时间：{pd.Timestamp.now():%Y-%m-%d %H:%M}", ""]

    lines += ["## 1. 表概览", "", "| 表 | 行数 | 说明 |", "|---|---|---|"]
    lines += [f"| observations | {len(obs):,} | 水质+水文观测长表 |"]
    lines += [f"| sites | {len(sites):,} | 统一站点/设施注册表 |"]
    lines += [f"| flow_network | {len(flow):,} | 河网拓扑边 |"]
    lines += [f"| sources | {len(sources):,} | NPDES 污染源设施 |"]
    lines += [f"| source_discharge | {len(dmr):,} | DMR 排放记录 |"]
    lines += [f"| source_violations | {len(viol):,} | 排放违规记录 |", ""]

    lines += ["## 2. 观测分布", ""]
    lines += ["### 按数据集", "", _table(obs.groupby("dataset_id").size())]
    lines += ["### 按统一参数编码（Top 15）", ""]
    top = obs.groupby("parameter_code").size().sort_values(ascending=False).head(15)
    lines += [_table(top)]

    lines += ["### 时间覆盖", ""]
    for ds, g in obs.groupby("dataset_id"):
        tmin, tmax = g["timestamp_utc"].min()[:10], g["timestamp_utc"].max()[:10]
        lines += [f"- {ds}: {tmin} ~ {tmax}"]
    lines += [""]

    lines += ["## 3. 站点吸附", "", _table(sites.groupby(["dataset_id", "snap_flag"]).size())]
    lines += [f"- 吸附距离中位数：{sites['snap_dist_m'].median():.1f} m；>500m 的站点 {int((sites['snap_dist_m']>500).sum())} 个", ""]

    lines += ["## 4. 污染源", ""]
    lines += [f"- NPDES 设施 {len(sources):,} 个（许可状态见 sources.csv）"]
    lines += [f"- DMR 记录覆盖 {dmr['npdes_id'].nunique():,} 个设施；违规记录覆盖 {viol['npdes_id'].nunique():,} 个设施", ""]

    lines += ["## 5. 已知限制与注意事项", ""]
    lines += [
        "- **WQP 时间戳非真 UTC**：`timestamp_utc` 由 ActivityStartDate+Time 拼接并加 `Z`，"
        "实际为站点本地时区（各站 TimeZoneCode 不同），跨站对比传播时间前需统一时区。",
        "- **USGS 为逐日值**：无日内时间，`timestamp_utc` 统一为当日 00:00Z。",
        "- **参数编码**：核心指标走 `parameters.csv` 映射；未映射的 WQP 特征按名称 slug 化保留，未做近似合并。",
        "- **非检出**：WQP 非检出（value 为空）保留 `detection_limit`，value 为 NaN，qc_flag 含 `Not Detected`。",
        "- **吸附超距**：102 个站点距最近河段 >500m，需逐一核验（湖泊站/坐标误差/离线）。",
    ]
    return "\n".join(lines)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("[ingest] 映射四类数据到统一 schema ...")

    obs = pd.concat(
        [
            mappers.map_wqp_observations(RAW / "usgs_wqp_cuyahoga" / "result_2018_2024.csv"),
            mappers.map_usgs_observations(RAW / "usgs_nwis_cuyahoga" / "daily_values_2018_2024.rdb"),
        ],
        ignore_index=True,
    )
    sites = mappers.map_sites(INTERIM / "nhdplus_hr_cuyahoga" / "sites_snapped.csv")
    flow = mappers.map_flow(PROCESSED / "cuyahoga_network" / "flow_edges.csv")
    sources = mappers.map_echo_sources(
        RAW / "epa_echo_cuyahoga" / "facilities_huc04110002.json",
        INTERIM / "nhdplus_hr_cuyahoga" / "sites_snapped.csv",
    )
    dmr = mappers.map_echo_dmr(RAW / "epa_echo_cuyahoga" / "OH_FY2024_NPDES_DMRS_cuyahoga_huc8.csv")
    viol = mappers.map_echo_violations(RAW / "epa_echo_cuyahoga" / "OH_NPDES_EFF_VIOLATIONS_cuyahoga_huc8.csv")

    print("[ingest] 写入标准化 CSV ...")
    obs.to_csv(OUT / "observations.csv", index=False)
    sites.to_csv(OUT / "sites.csv", index=False)
    flow.to_csv(OUT / "flow_network.csv", index=False)
    sources.to_csv(OUT / "sources.csv", index=False)
    dmr.to_csv(OUT / "source_discharge.csv", index=False)
    viol.to_csv(OUT / "source_violations.csv", index=False)
    build_parameters().to_csv(OUT / "parameters.csv", index=False)
    build_datasets().to_csv(OUT / "datasets.csv", index=False)

    report = write_report(obs, sites, flow, sources, dmr, viol)
    (OUT / "data_quality_report.md").write_text(report, encoding="utf-8")

    print(f"[ingest] 完成：{OUT}")
    print(f"  observations={len(obs):,}  sites={len(sites):,}  flow_edges={len(flow):,}  "
          f"sources={len(sources):,}  dmr={len(dmr):,}  violations={len(viol):,}")


if __name__ == "__main__":
    main()
