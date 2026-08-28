"""四类美国公开数据 → 统一 schema 的映射函数。

所有函数返回带 schema.py 定义列的 pandas DataFrame，无 I/O 副作用。
"""
from __future__ import annotations

import hashlib
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


def _integer_id(series: pd.Series) -> pd.Series:
    """Normalize numeric reach identifiers without leaking a trailing `.0`."""
    return pd.to_numeric(series, errors="coerce").astype("Int64").astype("string")


def _taihu_facility_ids(df: pd.DataFrame, registration_id: pd.Series) -> pd.Series:
    """Build stable facility IDs when one legal entity operates multiple sites."""
    names = df["name"].fillna("").astype("string").str.strip()
    addresses = df["address"].fillna("").astype("string").str.strip()
    latitudes = pd.to_numeric(df["lat_wgs84"], errors="coerce").map(
        lambda value: "" if pd.isna(value) else f"{value:.6f}"
    )
    longitudes = pd.to_numeric(df["lon_wgs84"], errors="coerce").map(
        lambda value: "" if pd.isna(value) else f"{value:.6f}"
    )
    fingerprints = (
        names + "|" + addresses + "|" + latitudes.astype("string") + "|" + longitudes.astype("string")
    ).map(lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()[:12])
    legal_entity = registration_id.mask(registration_id.eq(""), "unregistered")
    return TAIHU_SOURCE_DATASET_ID + ":" + legal_entity + ":" + fingerprints


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
    df = pd.read_csv(snapped_csv)
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
            "network_id": "nhdplus_hr_cuyahoga",
            "reach_id": _integer_id(df["COMID"]),
            "snap_flag": df["snap_flag"],
            "snap_dist_m": df["snap_dist_m"],
        }
    )
    return out


# ----------------------------------------------------------------- 河网
def map_flow(edges_csv: Path) -> pd.DataFrame:
    """flow_edges.csv → 河网拓扑表。"""
    df = pd.read_csv(edges_csv)
    return pd.DataFrame(
        {
            "network_id": "nhdplus_hr_cuyahoga",
            "reach_id": _integer_id(df["COMID"]),
            "from_node": _integer_id(df["FromNode"]),
            "to_node": _integer_id(df["ToNode"]),
            "downstream_reach_id": None,
            "length_km": pd.to_numeric(df["LengthKM"], errors="coerce"),
        }
    )[schema.FLOW_COLUMNS]


# ----------------------------------------------------------------- ECHO 污染源
def map_echo_sources(facilities_json: Path, snapped_csv: Path) -> pd.DataFrame:
    """ECHO 设施 JSON + 吸附结果 → 统一污染源表。"""
    fac = pd.DataFrame(json.loads(facilities_json.read_text(encoding="utf-8"))["Results"]["Facilities"])
    echo_snap = pd.read_csv(snapped_csv)
    echo_snap = echo_snap[echo_snap["dataset"] == "echo"][["source_id", "COMID", "snap_flag"]]
    df = fac.merge(echo_snap, left_on="SourceID", right_on="source_id", how="left")
    return pd.DataFrame(
        {
            "source_id": "epa_echo_cuyahoga:" + df["SourceID"],
            "dataset_id": "epa_echo_cuyahoga",
            "source_type": "npdes_facility",
            "registration_id": df["SourceID"],
            "name": df["CWPName"],
            "industry": "",
            "city": df["CWPCity"],
            "region": df["CWPState"],
            "address": "",
            "lat": pd.to_numeric(df["FacLat"], errors="coerce"),
            "lon": pd.to_numeric(df["FacLong"], errors="coerce"),
            "network_id": "nhdplus_hr_cuyahoga",
            "reach_id": _integer_id(df["COMID"]),
            "snap_flag": df["snap_flag"],
            "snap_dist_m": None,
            "permit_status": df["CWPPermitStatusDesc"],
        }
    )[schema.SOURCE_COLUMNS]


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


# ----------------------------------------------------------------- 太湖统一映射
TAIHU_DATASET_ID = "guokong_surface_water_2021_2025"
TAIHU_NETWORK_ID = "hydrorivers_v10_as"
TAIHU_SOURCE_DATASET_ID = "taihu_enterprises_v2"


def map_taihu_reading_frame(df: pd.DataFrame, station_id: str) -> pd.DataFrame:
    """One legacy Taihu station table → unified observation long table."""
    timestamps = pd.to_datetime(df["ts"], errors="coerce", utc=True)
    global_station_id = f"{TAIHU_DATASET_ID}:{station_id}"
    parts: list[pd.DataFrame] = []
    for source_column, (parameter_code, unit) in schema.TAIHU_PARAM_MAP.items():
        if source_column not in df.columns:
            continue
        values = pd.to_numeric(df[source_column], errors="coerce")
        valid = timestamps.notna() & values.notna()
        if not valid.any():
            continue
        parts.append(
            pd.DataFrame(
                {
                    "dataset_id": TAIHU_DATASET_ID,
                    "station_id": global_station_id,
                    "timestamp_utc": timestamps[valid].dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "parameter_code": parameter_code,
                    "value": values[valid],
                    "unit": unit,
                    "qc_flag": "",
                    "detection_limit": None,
                }
            )
        )
    if not parts:
        return pd.DataFrame(columns=schema.OBSERVATION_COLUMNS)
    return pd.concat(parts, ignore_index=True)[schema.OBSERVATION_COLUMNS]


def map_taihu_evaluation_labels(df: pd.DataFrame, station_id: str) -> pd.DataFrame:
    """Keep published water-quality classes outside investigation observations."""
    if "quality_class" not in df.columns:
        return pd.DataFrame(columns=schema.EVALUATION_LABEL_COLUMNS)
    timestamps = pd.to_datetime(df["ts"], errors="coerce", utc=True)
    labels = df["quality_class"].astype("string").str.strip()
    valid = timestamps.notna() & labels.notna() & labels.ne("")
    return pd.DataFrame(
        {
            "dataset_id": TAIHU_DATASET_ID,
            "station_id": f"{TAIHU_DATASET_ID}:{station_id}",
            "timestamp_utc": timestamps[valid].dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "label_code": "quality_class",
            "label_value": labels[valid],
            "label_source": "CNEMC published water-quality class",
        }
    )[schema.EVALUATION_LABEL_COLUMNS]


def map_taihu_sites(snapped_csv: Path) -> pd.DataFrame:
    """Taihu station registry and HydroRIVERS snap results → unified sites."""
    df = pd.read_csv(snapped_csv)
    matched = df["matched"].astype("string").str.lower().isin(["true", "1", "yes"])
    source_id = df["station_id"].astype("string")
    return pd.DataFrame(
        {
            "site_id": TAIHU_DATASET_ID + ":" + source_id,
            "dataset_id": TAIHU_DATASET_ID,
            "source_id": source_id,
            "name": df["name"],
            "site_type": "surface_water_station",
            "provider": "China National Environmental Monitoring Centre",
            "lat": pd.to_numeric(df["lat_wgs"], errors="coerce"),
            "lon": pd.to_numeric(df["lon_wgs"], errors="coerce"),
            "network_id": TAIHU_NETWORK_ID,
            "reach_id": _integer_id(df["hyriv_id"]),
            "snap_flag": matched.map({True: "ok", False: "review"}),
            "snap_dist_m": pd.to_numeric(df["snap_dist_m"], errors="coerce"),
        }
    )[schema.SITE_COLUMNS]


def map_taihu_sources(snapped_csv: Path) -> pd.DataFrame:
    """Taihu enterprise registry and HydroRIVERS snap results → unified sources."""
    df = pd.read_csv(snapped_csv, dtype={"credit_code": "string"})
    matched = df["matched"].astype("string").str.lower().isin(["true", "1", "yes"])
    registration_id = df["credit_code"].fillna("").astype("string")
    source_id = _taihu_facility_ids(df, registration_id)
    return pd.DataFrame(
        {
            "source_id": source_id,
            "dataset_id": TAIHU_SOURCE_DATASET_ID,
            "source_type": "registered_enterprise",
            "registration_id": registration_id,
            "name": df["name"],
            "industry": df["industry"],
            "city": df["city"],
            "region": "",
            "address": df["address"],
            "lat": pd.to_numeric(df["lat_wgs84"], errors="coerce"),
            "lon": pd.to_numeric(df["lon_wgs84"], errors="coerce"),
            "network_id": TAIHU_NETWORK_ID,
            "reach_id": _integer_id(df["hyriv_id"]),
            "snap_flag": matched.map({True: "ok", False: "review"}),
            "snap_dist_m": pd.to_numeric(df["snap_dist_m"], errors="coerce"),
            "permit_status": "",
        }
    )[schema.SOURCE_COLUMNS]


def map_hydrorivers_flow(shapefile: Path) -> pd.DataFrame:
    """HydroRIVERS reach topology → generic flow-network rows."""
    import geopandas as gpd

    df = gpd.read_file(shapefile, columns=["HYRIV_ID", "NEXT_DOWN", "LENGTH_KM"])
    downstream = _integer_id(df["NEXT_DOWN"]).mask(
        pd.to_numeric(df["NEXT_DOWN"], errors="coerce").eq(0)
    )
    return pd.DataFrame(
        {
            "network_id": TAIHU_NETWORK_ID,
            "reach_id": _integer_id(df["HYRIV_ID"]),
            "from_node": None,
            "to_node": None,
            "downstream_reach_id": downstream,
            "length_km": pd.to_numeric(df["LENGTH_KM"], errors="coerce"),
        }
    )[schema.FLOW_COLUMNS]
