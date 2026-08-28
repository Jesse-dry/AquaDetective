"""统一数据模型（列定义）与参数编码映射。

规范见 docs/后续开发计划.md §3：标准观测记录至少包含
dataset_id / station_id / timestamp_utc / parameter_code / value / unit /
qc_flag / detection_limit / lat / lon / source_url / retrieved_at。

lat/lon 冗余在 sites 注册表（按站点恒定），source_url/retrieved_at 冗余在
datasets 元数据表，避免观测长表逐行重复。
"""
from __future__ import annotations

import re

# ----------------------------------------------------------------- 表结构
OBSERVATION_COLUMNS = [
    "dataset_id", "station_id", "timestamp_utc", "parameter_code",
    "value", "unit", "qc_flag", "detection_limit",
]

SITE_COLUMNS = [
    "site_id", "dataset_id", "source_id", "name", "site_type",
    "provider", "lat", "lon", "comid", "snap_flag", "snap_dist_m",
]

FLOW_COLUMNS = ["comid", "from_node", "to_node", "length_km"]

SOURCE_COLUMNS = [
    "source_id", "npdes_id", "name", "city", "state", "zip",
    "lat", "lon", "comid", "permit_status",
]

DATASET_COLUMNS = [
    "dataset_id", "name", "provider", "source_url", "license",
    "retrieved_at", "region", "time_range_start", "time_range_end", "frequency",
]

# ----------------------------------------------------------------- 参数编码
# 核心水质指标 → 统一编码（其余按名称 slug 化保留，避免按名称近似合并误伤）
WQP_PARAM_MAP: dict[str, str] = {
    # 水温（注意 WQP 用 "Temperature, water"，非 "Temperature"）
    "Temperature, water": "temperature",
    "Temperature, air": "air_temperature",
    "Temperature, sediment": "sediment_temperature",
    # 溶解氧 / 需氧量
    "Dissolved oxygen (DO)": "do",
    "Oxygen": "do",
    "Dissolved oxygen saturation": "do_saturation",
    "Biochemical oxygen demand, standard conditions": "bod",
    "Carbonaceous biochemical oxygen demand, standard conditions": "cbod",
    "Chemical oxygen demand": "cod",
    # 常规理化
    "pH": "ph",
    "Conductivity": "conductivity",
    "Specific conductance": "specific_conductance",
    "Salinity": "salinity",
    "Turbidity": "turbidity",
    "Total dissolved solids": "tds",
    "Chloride": "chloride",
    # 氮（按形态细分，避免近似合并）
    "Ammonia": "ammonia_n",
    "Ammonia and ammonium": "ammonia_n",
    "Nitrate": "nitrate_n",
    "Nitrite": "nitrite_n",
    "Nitrate + Nitrite": "nitrate_nitrite_n",
    "Inorganic nitrogen (nitrate and nitrite)": "nitrate_nitrite_n",
    "Organic Nitrogen": "organic_nitrogen",
    "Total Kjeldahl nitrogen (Organic N & NH3)": "tkn",
    "Nitrogen, mixed forms (NH3), (NH4), organic, (NO2) and (NO3)": "tn",
    "Total Nitrogen, mixed forms": "tn",
    # 磷
    "Orthophosphate": "orthophosphate",
    "Phosphorus": "phosphorus",
    "Total Phosphorus, mixed forms": "tp",
    # 沉积物
    "Suspended Sediment Concentration (SSC)": "ssc",
    "Sediment": "sediment",
}

USGS_PARAM_MAP: dict[str, str] = {
    "00060": "discharge",      # ft³/s
    "00065": "gage_height",    # ft
    "00010": "temperature",    # deg C（与 WQP 水温同码）
}

# ECHO DMR 污染物（排放记录，属于 sources 模型而非 observations）
ECHO_PARAM_MAP: dict[str, str] = {
    "pH": "ph",
    "BOD": "bod",
    "Solids": "solids",
    "Nitrogen": "nitrogen",
    "Phosphorus": "phosphorus",
    "Flow": "flow",
    "Flow rate": "flow",
    "Temperature": "temperature",
    "Turbidity": "turbidity",
    "E. coli": "e_coli",
    "Mercury": "mercury",
    "Oil and grease": "oil_grease",
    "Oxygen": "do",
    "Nitrite + Nitrate total [as N]": "nitrate_nitrite_n",
    "Overflows": "overflows",
}


def slug(name: str) -> str:
    """未映射名称 → 小写蛇形编码（保留原始概念，不丢失）。"""
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def map_wqp_param(name: str) -> str:
    return WQP_PARAM_MAP.get(name, slug(name))


def map_usgs_param(code: str) -> str:
    return USGS_PARAM_MAP.get(code, f"usgs_{code}")


def map_echo_param(name: str) -> str:
    return ECHO_PARAM_MAP.get(name, slug(name))
