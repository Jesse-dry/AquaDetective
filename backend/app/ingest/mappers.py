"""四类美国公开数据 → 统一 schema 的映射函数。

所有函数返回带 schema.py 定义列的 pandas DataFrame，无 I/O 副作用。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from . import schema

# 短名 → 全名（与 metadata/*.json 的 dataset_id 一致）
DATASET_ALIASES = {
    "wqp": "usgs_wqp_cuyahoga",
    "usgs": "usgs_nwis_cuyahoga",
    "echo": "epa_echo_cuyahoga",
}


# ----------------------------------------------------------------- WQP 水质观测
def map_wqp_observations(csv_path: Path) -> pd.DataFrame:
    """WQP Result CSV → observations 长表（水质指标）。"""
    cols = [
        "ActivityStartDate", "ActivityStartTime/Time",
        "MonitoringLocationIdentifier", "ResultDetectionConditionText",
        "CharacteristicName", "ResultMeasureValue", "ResultMeasure/MeasureUnitCode",
        "ResultStatusIdentifier", "DetectionQuantitationLimitMeasure/MeasureValue",
    ]
    df = pd.read_csv(csv_path, usecols=cols, dtype=str)

    import numpy as np

    date = df["ActivityStartDate"].fillna("")
    time = df["ActivityStartTime/Time"].fillna("")
    ts = pd.Series(
        np.where(time.str.len() > 0, date + "T" + time, date + "T00:00:00"),
        index=df.index,
    )

    status = df["ResultStatusIdentifier"].fillna("")
    cond = df["ResultDetectionConditionText"].fillna("")
    qc = status.where(cond == "", status + "|" + cond)

    return pd.DataFrame(
        {
            "dataset_id": "usgs_wqp_cuyahoga",
            "station_id": "usgs_wqp_cuyahoga:" + df["MonitoringLocationIdentifier"],
            "timestamp_utc": ts + "Z",  # WQP 时间为本地时区，UTC 语义见质量报告
            "parameter_code": df["CharacteristicName"].map(schema.map_wqp_param),
            "value": pd.to_numeric(df["ResultMeasureValue"], errors="coerce"),
            "unit": df["ResultMeasure/MeasureUnitCode"],
            "qc_flag": qc,
            "detection_limit": pd.to_numeric(
                df["DetectionQuantitationLimitMeasure/MeasureValue"], errors="coerce"
            ),
        }
    )


# ----------------------------------------------------------------- USGS 水文观测
def _parse_usgs_dv_rdb(rdb_path: Path) -> list[tuple]:
    """解析 USGS dv 多站点多参数的 RDB（按时间序列分块）。"""
    rows: list[tuple] = []
    cur_parm: str | None = None
    with open(rdb_path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if parts[0] == "agency_cd":
                m = re.search(r"_(\d{5})_\d{5}", parts[3]) if len(parts) > 3 else None
                cur_parm = m.group(1) if m else None
                continue
            if re.match(r"^\d+[a-z]", parts[0]):  # 格式行，如 "5s 15s ..."
                continue
            if parts[0] == "USGS" and cur_parm:
                site, date = parts[1], parts[2]
                val = parts[3] if len(parts) > 3 else ""
                qc = parts[4] if len(parts) > 4 else ""
                rows.append((site, date, cur_parm, val, qc))
    return rows


def map_usgs_observations(rdb_path: Path) -> pd.DataFrame:
    """USGS dv RDB → observations 长表（流量/水位/水温）。"""
    rows = _parse_usgs_dv_rdb(rdb_path)
    df = pd.DataFrame(rows, columns=["site", "date", "parm_cd", "value", "qc"])
    unit = {"00060": "ft3/s", "00065": "ft", "00010": "degC"}
    out = pd.DataFrame(
        {
            "dataset_id": "usgs_nwis_cuyahoga",
            "station_id": "usgs_nwis_cuyahoga:" + df["site"],
            "timestamp_utc": df["date"] + "T00:00:00Z",
            "parameter_code": df["parm_cd"].map(schema.map_usgs_param),
            "value": pd.to_numeric(df["value"], errors="coerce"),
            "unit": df["parm_cd"].map(unit),
            "qc_flag": df["qc"],
            "detection_limit": None,
        }
    )
    return out.dropna(subset=["value"])


# ----------------------------------------------------------------- 站点注册表
def map_sites(snapped_csv: Path) -> pd.DataFrame:
    """吸附结果 sites_snapped.csv → 统一站点注册表。"""
    df = pd.read_csv(snapped_csv, dtype={"COMID": "Int64"})
    df["dataset_id"] = df["dataset"].map(DATASET_ALIASES)
    df["site_id"] = df["dataset_id"] + ":" + df["source_id"]
    out = pd.DataFrame(
        {
            "site_id": df["site_id"],
            "dataset_id": df["dataset_id"],
            "source_id": df["source_id"],
            "name": df["name"],
            "site_type": df["site_type"],
            "provider": df["provider"],
            "lat": df["lat"],
            "lon": df["lon"],
            "comid": df["COMID"],
            "snap_flag": df["snap_flag"],
            "snap_dist_m": df["snap_dist_m"],
        }
    )
    return out


# ----------------------------------------------------------------- 河网
def map_flow(edges_csv: Path) -> pd.DataFrame:
    """flow_edges.csv → 河网拓扑表。"""
    df = pd.read_csv(edges_csv)
    return df.rename(columns={"COMID": "comid", "FromNode": "from_node",
                              "ToNode": "to_node", "LengthKM": "length_km"})[schema.FLOW_COLUMNS]


# ----------------------------------------------------------------- ECHO 污染源
def map_echo_sources(facilities_json: Path, snapped_csv: Path) -> pd.DataFrame:
    """ECHO 设施 JSON + 吸附结果 → 统一污染源表。"""
    fac = pd.DataFrame(json.loads(facilities_json.read_text(encoding="utf-8"))["Results"]["Facilities"])
    echo_snap = pd.read_csv(snapped_csv, dtype={"COMID": "Int64"})
    echo_snap = echo_snap[echo_snap["dataset"] == "echo"][["source_id", "COMID", "snap_flag"]]
    df = fac.merge(echo_snap, left_on="SourceID", right_on="source_id", how="left")
    return pd.DataFrame(
        {
            "source_id": "epa_echo_cuyahoga:" + df["SourceID"],
            "npdes_id": df["SourceID"],
            "name": df["CWPName"],
            "city": df["CWPCity"],
            "state": df["CWPState"],
            "zip": df["CWPZip"],
            "lat": pd.to_numeric(df["FacLat"], errors="coerce"),
            "lon": pd.to_numeric(df["FacLong"], errors="coerce"),
            "comid": df["COMID"],
            "permit_status": df["CWPPermitStatusDesc"],
        }
    )


# ----------------------------------------------------------------- ECHO 排放记录（轻量映射）
def map_echo_dmr(dmr_csv: Path) -> pd.DataFrame:
    """过滤后的 DMR CSV → 排放记录表（逐设施逐报告期）。"""
    df = pd.read_csv(dmr_csv, dtype=str, usecols=[
        "EXTERNAL_PERMIT_NMBR", "PARAMETER_DESC", "MONITORING_PERIOD_END_DATE",
        "DMR_VALUE_NMBR", "DMR_UNIT_CODE", "LIMIT_VALUE_NMBR", "EXCEEDENCE_PCT",
    ])
    return pd.DataFrame(
        {
            "source_id": "epa_echo_cuyahoga:" + df["EXTERNAL_PERMIT_NMBR"],
            "npdes_id": df["EXTERNAL_PERMIT_NMBR"],
            "parameter_code": df["PARAMETER_DESC"].map(schema.map_echo_param),
            "monitoring_period_end": df["MONITORING_PERIOD_END_DATE"],
            "value": pd.to_numeric(df["DMR_VALUE_NMBR"], errors="coerce"),
            "unit": df["DMR_UNIT_CODE"],
            "limit_value": pd.to_numeric(df["LIMIT_VALUE_NMBR"], errors="coerce"),
            "exceedence_pct": pd.to_numeric(df["EXCEEDENCE_PCT"], errors="coerce"),
        }
    )


def map_echo_violations(violations_csv: Path) -> pd.DataFrame:
    """过滤后的违规 CSV → 违规记录表。"""
    df = pd.read_csv(violations_csv, dtype=str, usecols=[
        "NPDES_ID", "PARAMETER_DESC", "VIOLATION_TYPE_DESC", "VIOLATION_DESC",
        "MONITORING_PERIOD_END_DATE", "EXCEEDENCE_PCT",
    ])
    return pd.DataFrame(
        {
            "source_id": "epa_echo_cuyahoga:" + df["NPDES_ID"],
            "npdes_id": df["NPDES_ID"],
            "parameter_code": df["PARAMETER_DESC"].map(schema.map_echo_param),
            "violation_type": df["VIOLATION_TYPE_DESC"],
            "violation_desc": df["VIOLATION_DESC"],
            "monitoring_period_end": df["MONITORING_PERIOD_END_DATE"],
            "exceedence_pct": pd.to_numeric(df["EXCEEDENCE_PCT"], errors="coerce"),
        }
    )
