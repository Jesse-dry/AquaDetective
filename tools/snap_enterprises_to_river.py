#!/usr/bin/env python3
"""真实企业库对接溯源系统:GCJ-02 → WGS84 转换 + 河网空间吸附。

输入:
  data/interim/taihu_enterprises_v1/taihu_basin_enterprises_v2.csv  (37 家,GCJ-02 坐标)
  data/interim/hydrorivers_v10_as/hydrorivers_taihu_bbox.shp        (太湖河网,WGS84)

输出:data/processed/taihu_enterprises/
  enterprises_snapped.csv   企业 → 最近河段映射(含 NEXT_DOWN 等拓扑字段,可直接溯源)
  snap_report.json          匹配质量报告(命中/未命中、距离分布)

规则:
1. 坐标转换用 GCJ-02 → WGS84 标准近似算法(误差米级);
2. 距离计算在 UTM 51N(米制)下进行;
3. 吸附距离 ≥ SNAP_LIMIT_M 的企业标记为 unmatched(河网未覆盖其所在小微水体),
   溯源时只能按"就近河段"近似处理——如实记录,不强行匹配。

用法:python tools/snap_enterprises_to_river.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parent.parent
SRC_CSV = ROOT / "data/interim/taihu_enterprises_v1/taihu_basin_enterprises_v2.csv"
SRC_SHP = ROOT / "data/interim/hydrorivers_v10_as/hydrorivers_taihu_bbox.shp"
OUT = ROOT / "data/processed/taihu_enterprises"

SNAP_LIMIT_M = 1500.0

# ---------- GCJ-02 → WGS84(标准近似算法) ----------
_A = 6378245.0
_EE = 0.00669342162296594323


def _out_of_china(lon: float, lat: float) -> bool:
    return not (72.004 <= lon <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def gcj02_to_wgs84(lon: float, lat: float) -> tuple[float, float]:
    if _out_of_china(lon, lat):
        return lon, lat
    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - _EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrtmagic) * math.pi)
    dlon = (dlon * 180.0) / (_A / sqrtmagic * math.cos(radlat) * math.pi)
    mglat = lat + dlat
    mglon = lon + dlon
    return lon * 2 - mglon, lat * 2 - mglat


# ---------- 空间吸附 ----------
def main() -> None:
    ents = pd.read_csv(SRC_CSV)
    ents["lon_wgs84"], ents["lat_wgs84"] = zip(
        *ents.apply(lambda r: gcj02_to_wgs84(float(r["longitude"]), float(r["latitude"])), axis=1)
    )

    rivers = gpd.read_file(SRC_SHP)
    rivers_m = rivers.to_crs(32651)

    pts = gpd.GeoDataFrame(
        ents,
        geometry=[Point(x, y) for x, y in zip(ents["lon_wgs84"], ents["lat_wgs84"])],
        crs=4326,
    ).to_crs(32651)

    union = rivers_m.geometry
    records = []
    for i, row in ents.iterrows():
        p = pts.geometry.iloc[i]
        dists = union.distance(p)
        j = int(dists.idxmin())
        reach = rivers_m.loc[j]
        dist = float(dists.min())
        records.append({
            "name": row["name"],
            "city": row["city"],
            "industry": row["industry"],
            "credit_code": row["credit_code"],
            "address": row["address"],
            "lon_wgs84": round(row["lon_wgs84"], 6),
            "lat_wgs84": round(row["lat_wgs84"], 6),
            "hyriv_id": int(reach["HYRIV_ID"]),
            "next_down": int(reach["NEXT_DOWN"]),
            "main_riv": int(reach["MAIN_RIV"]),
            "dis_av_cms": round(float(reach["DIS_AV_CMS"]), 2),
            "ord_stra": int(reach["ORD_STRA"]),
            "snap_dist_m": round(dist, 1),
            "matched": dist < SNAP_LIMIT_M,
        })

    out_df = pd.DataFrame(records)
    OUT.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(OUT / "enterprises_snapped.csv", index=False)

    matched = out_df["matched"].sum()
    report = {
        "total": len(out_df),
        "matched": int(matched),
        "unmatched": int(len(out_df) - matched),
        "snap_limit_m": SNAP_LIMIT_M,
        "dist_stats": {
            "median_m": float(out_df["snap_dist_m"].median()),
            "p90_m": float(out_df["snap_dist_m"].quantile(0.9)),
            "max_m": float(out_df["snap_dist_m"].max()),
        },
        "unmatched_list": out_df.loc[~out_df["matched"], ["name", "snap_dist_m"]].to_dict("records"),
        "notes": "坐标经 GCJ-02→WGS84 近似转换;吸附到 HydroRIVERS 太湖裁剪河网,"
                 "含 NEXT_DOWN 拓扑可直接做上下游溯源;unmatched 企业位于河网未覆盖的小微水体。",
    }
    (OUT / "snap_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
