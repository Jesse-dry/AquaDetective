"""公开基准数据统一导入器入口。

把 Cuyahoga 与太湖公开数据映射到统一 schema，并生成数据质量报告。

运行（仓库根目录）：
    cd backend
    .venv/Scripts/python.exe -m app.ingest.run --dataset all
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import pandas as pd

from . import mappers, schema

ROOT = Path(__file__).resolve().parents[3]  # backend/app/ingest/run.py -> 仓库根
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
OUT = PROCESSED / "cuyahoga"
TAIHU_OUT = PROCESSED / "taihu_unified"
QUALITY_REPORTS = ROOT / "docs" / "data-quality"


def build_parameters() -> pd.DataFrame:
    rows = []
    for name, code in schema.WQP_PARAM_MAP.items():
        rows.append({"parameter_code": code, "source": "wqp", "original_name": name})
    for orig, code in schema.USGS_PARAM_MAP.items():
        rows.append({"parameter_code": code, "source": "usgs", "original_name": orig})
    for name, code in schema.ECHO_PARAM_MAP.items():
        rows.append({"parameter_code": code, "source": "echo", "original_name": name})
    for name, (code, _) in schema.TAIHU_PARAM_MAP.items():
        rows.append({"parameter_code": code, "source": "taihu", "original_name": name})
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


def write_cuyahoga_report(obs: pd.DataFrame, sites: pd.DataFrame, flow: pd.DataFrame,
                          sources: pd.DataFrame, dmr: pd.DataFrame,
                          viol: pd.DataFrame) -> str:
    lines = ["# Cuyahoga HUC8 公开数据 · 数据质量报告", ""]

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
        (
            "- **WQP 时间戳非真 UTC**：`timestamp_utc` 由 ActivityStartDate+Time 拼接并加 `Z`，"
            "实际为站点本地时区（各站 TimeZoneCode 不同），跨站对比传播时间前需统一时区。"
        ),
        "- **USGS 为逐日值**：无日内时间，`timestamp_utc` 统一为当日 00:00Z。",
        "- **参数编码**：核心指标走 `parameters.csv` 映射；未映射的 WQP 特征按名称 slug 化保留，未做近似合并。",
        "- **非检出**：WQP 非检出（value 为空）保留 `detection_limit`，value 为 NaN，qc_flag 含 `Not Detected`。",
        "- **吸附超距**：102 个站点距最近河段 >500m，需逐一核验（湖泊站/坐标误差/离线）。",
    ]
    return "\n".join(lines)


def _write_quality_report(out_dir: Path, report_name: str, report: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    QUALITY_REPORTS.mkdir(parents=True, exist_ok=True)
    (out_dir / "data_quality_report.md").write_text(report, encoding="utf-8")
    (QUALITY_REPORTS / f"{report_name}.md").write_text(report, encoding="utf-8")


def run_cuyahoga() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("[ingest:cuyahoga] 映射四类数据到统一 schema ...")

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

    print("[ingest:cuyahoga] 写入标准化 CSV ...")
    obs.to_csv(OUT / "observations.csv", index=False)
    sites.to_csv(OUT / "sites.csv", index=False)
    flow.to_csv(OUT / "flow_network.csv", index=False)
    sources.to_csv(OUT / "sources.csv", index=False)
    dmr.to_csv(OUT / "source_discharge.csv", index=False)
    viol.to_csv(OUT / "source_violations.csv", index=False)
    build_parameters().to_csv(OUT / "parameters.csv", index=False)
    build_datasets().to_csv(OUT / "datasets.csv", index=False)

    report = write_cuyahoga_report(obs, sites, flow, sources, dmr, viol)
    _write_quality_report(OUT, "cuyahoga", report)

    print(f"[ingest:cuyahoga] 完成：{OUT}")
    print(f"  observations={len(obs):,}  sites={len(sites):,}  flow_edges={len(flow):,}  "
          f"sources={len(sources):,}  dmr={len(dmr):,}  violations={len(viol):,}")


def write_taihu_report(stats: dict[str, int], sites: pd.DataFrame,
                        sources: pd.DataFrame, flow: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# 太湖国控断面公开数据 · 统一导入质量报告",
            "",
            "## 1. 表概览",
            "",
            "| 表 | 行数 | 说明 |",
            "|---|---:|---|",
            f"| observations | {stats['observations']:,} | 调查可读的数值观测长表 |",
            f"| evaluation_labels | {stats['evaluation_labels']:,} | 离线评测水质类别 |",
            f"| sites | {len(sites):,} | 太湖断面及 HydroRIVERS 吸附 |",
            f"| sources | {len(sources):,} | 企业候选源及河网吸附 |",
            f"| flow_network | {len(flow):,} | HydroRIVERS 河段拓扑 |",
            "",
            "## 2. 隔离保证",
            "",
            "- `observations.csv.gz` 不包含 `quality_class`、`truth_source` 或企业标签。",
            "- 发布水质类别仅写入 `evaluation_labels.csv.gz`，只供离线验证读取。",
            "- 旧版按站点宽表继续保留，现有异常检测与前端演示不受影响。",
            "",
            "## 3. 已知限制",
            "",
            f"- 河网吸附标记为 `ok` 的断面 {int((sites['snap_flag'] == 'ok').sum())}/{len(sites)}。",
            f"- 河网吸附标记为 `ok` 的企业 {int((sources['snap_flag'] == 'ok').sum())}/{len(sources)}。",
            "- 断面坐标来自汇编方地图查询，正式归因前仍需用官方坐标复核。",
            "- HydroRIVERS 流速与传播时间只能用于候选排序，不能作为污染因果证据。",
        ]
    )


def run_taihu() -> None:
    """Stream legacy Taihu station files into the unified long-table package."""
    readings_dir = PROCESSED / "guokong_taihu" / "readings"
    station_snap = PROCESSED / "guokong_taihu" / "stations_snapped.csv"
    enterprise_snap = PROCESSED / "taihu_enterprises" / "enterprises_snapped.csv"
    river_shape = INTERIM / "hydrorivers_v10_as" / "hydrorivers_taihu_bbox.shp"
    required = [readings_dir, station_snap, enterprise_snap, river_shape]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Taihu unified ingest inputs missing: " + ", ".join(missing))

    TAIHU_OUT.mkdir(parents=True, exist_ok=True)
    observations_path = TAIHU_OUT / "observations.csv.gz"
    labels_path = TAIHU_OUT / "evaluation_labels.csv.gz"
    observation_count = 0
    label_count = 0
    observation_header = True
    label_header = True
    print("[ingest:taihu] 流式写入统一观测与离线评测标签 ...")
    with (
        gzip.open(observations_path, "wt", encoding="utf-8", newline="") as obs_file,
        gzip.open(labels_path, "wt", encoding="utf-8", newline="") as label_file,
    ):
        for reading_path in sorted(readings_dir.glob("taihu_*.csv")):
            frame = pd.read_csv(reading_path)
            station_id = reading_path.stem
            observations = mappers.map_taihu_reading_frame(frame, station_id)
            labels = mappers.map_taihu_evaluation_labels(frame, station_id)
            if not observations.empty:
                observations.to_csv(obs_file, index=False, header=observation_header)
                observation_header = False
                observation_count += len(observations)
            if not labels.empty:
                labels.to_csv(label_file, index=False, header=label_header)
                label_header = False
                label_count += len(labels)
        if observation_header:
            pd.DataFrame(columns=schema.OBSERVATION_COLUMNS).to_csv(obs_file, index=False)
        if label_header:
            pd.DataFrame(columns=schema.EVALUATION_LABEL_COLUMNS).to_csv(label_file, index=False)

    sites = mappers.map_taihu_sites(station_snap)
    sources = mappers.map_taihu_sources(enterprise_snap)
    flow = mappers.map_hydrorivers_flow(river_shape)
    sites.to_csv(TAIHU_OUT / "sites.csv", index=False)
    sources.to_csv(TAIHU_OUT / "sources.csv", index=False)
    flow.to_csv(TAIHU_OUT / "flow_network.csv", index=False)
    build_parameters().to_csv(TAIHU_OUT / "parameters.csv", index=False)
    build_datasets().to_csv(TAIHU_OUT / "datasets.csv", index=False)

    stats = {"observations": observation_count, "evaluation_labels": label_count}
    report = write_taihu_report(stats, sites, sources, flow)
    _write_quality_report(TAIHU_OUT, "taihu", report)
    print(f"[ingest:taihu] 完成：{TAIHU_OUT}")
    print(
        f"  observations={observation_count:,}  evaluation_labels={label_count:,}  "
        f"sites={len(sites):,}  sources={len(sources):,}  flow_reaches={len(flow):,}"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        choices=("cuyahoga", "taihu", "all"),
        default="cuyahoga",
        help="dataset package to generate (default: cuyahoga)",
    )
    args = parser.parse_args(argv)
    if args.dataset in ("cuyahoga", "all"):
        run_cuyahoga()
    if args.dataset in ("taihu", "all"):
        run_taihu()


if __name__ == "__main__":
    main()
