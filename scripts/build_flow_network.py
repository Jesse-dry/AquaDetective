#!/usr/bin/env python3
"""Cuyahoga HUC8 流网导入器（原型）。

将四类美国公开基准数据关联到 NHDPlus HR 河网：
1. 解压 NHDPlus HR GDB，读取 Flowline（COMID / FromNode / ToNode / 几何）；
2. 把 WQP / USGS / ECHO 三类站点坐标吸附到最近河段，得到 COMID；
3. 用 networkx 建立上下游拓扑（FromNode -> ToNode 有向边）；
4. 产出 data/interim（空间匹配）与 data/processed（标准化 + 拓扑 + 上游设施示例）。

运行：backend/.venv/Scripts/python.exe scripts/build_flow_network.py
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"

GDB_ZIP = RAW / "nhdplus_hr_cuyahoga" / "NHDPLUS_H_0411_HU4_GDB.zip"
UTM_CRS = "EPSG:32617"  # Ohio / Cuyahoga 属 UTM 17N
SNAP_MAX_M = 500.0      # 超过此距离的站点标记为 "far"（可能离线或坐标有误）


# ---------------------------------------------------------------- GDB
def extract_gdb() -> Path:
    outdir = INTERIM / "nhdplus_hr_cuyahoga"
    outdir.mkdir(parents=True, exist_ok=True)
    gdb_dir = outdir / "NHDPLUS_H_0411_HU4_GDB.gdb"
    if not gdb_dir.exists():
        print(f"[extract] unzipping {GDB_ZIP.name} ...")
        with zipfile.ZipFile(GDB_ZIP) as z:
            z.extractall(outdir)
    return gdb_dir


def find_flowline_layer(gdb_dir: Path) -> str:
    import pyogrio

    layers = pyogrio.list_layers(str(gdb_dir))
    print("[discover] GDB layers:")
    for name, gtype in layers:
        print(f"   - {name}  ({gtype})")
    # 选含几何的 flowline 要素类（排除 VAA 等纯表，其 gtype 为 None）
    candidates = [n for n, g in layers if "flowline" in n.lower() and g is not None]
    if not candidates:
        raise SystemExit("未找到含几何的 Flowline 图层")
    return candidates[0]


def read_flowlines(gdb_dir: Path, layer: str) -> "gpd.GeoDataFrame":
    import geopandas as gpd

    fl = gpd.read_file(gdb_dir, layer="NHDFlowline")
    vaa = gpd.read_file(gdb_dir, layer="NHDPlusFlowlineVAA")
    print(f"[discover] NHDFlowline: {len(fl)} features, CRS={fl.crs}")
    print(f"[discover] NHDPlusFlowlineVAA: {len(vaa)} rows (FromNode/ToNode 拓扑)")
    if fl.crs is None:
        fl = fl.set_crs("EPSG:4269")  # NHDPlus HR 缺省为地理 NAD83

    geom_cols = [
        "NHDPlusID", "Permanent_Identifier", "GNIS_Name", "ReachCode",
        "LengthKM", "FType", "FlowDir", "Enabled", "geometry",
    ]
    vaa_cols = ["NHDPlusID", "FromNode", "ToNode", "HydroSeq", "LevelPathI",
                "TerminalFl", "Divergence", "TotDASqKm"]
    vaa_cols = [c for c in vaa_cols if c in vaa.columns]

    gdf = fl[geom_cols].merge(vaa[vaa_cols], on="NHDPlusID", how="inner")
    gdf = gdf.rename(columns={"NHDPlusID": "COMID", "Enabled": "ENABLED"})
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=fl.crs)

    gdf = gdf[gdf["COMID"].notna() & gdf["FromNode"].notna() & gdf["ToNode"].notna()]
    gdf = gdf[gdf["FromNode"] != gdf["ToNode"]]
    if "ENABLED" in gdf.columns:
        gdf = gdf[gdf["ENABLED"] == 1]
    print(f"[discover] network flowlines (joined + Enabled=1): {len(gdf)}")
    return gdf


# ---------------------------------------------------------------- points
def load_wqp_points() -> pd.DataFrame:
    f = RAW / "usgs_wqp_cuyahoga" / "station_surface_water.csv"
    df = pd.read_csv(f, dtype=str)
    df = df[
        [
            "MonitoringLocationIdentifier",
            "MonitoringLocationName",
            "MonitoringLocationTypeName",
            "LatitudeMeasure",
            "LongitudeMeasure",
            "ProviderName",
        ]
    ].rename(
        columns={
            "MonitoringLocationIdentifier": "source_id",
            "MonitoringLocationName": "name",
            "MonitoringLocationTypeName": "site_type",
            "LatitudeMeasure": "lat",
            "LongitudeMeasure": "lon",
            "ProviderName": "provider",
        }
    )
    df["dataset"] = "wqp"
    return df


def load_usgs_points() -> pd.DataFrame:
    f = RAW / "usgs_nwis_cuyahoga" / "site_inventory.rdb"
    lines = [l for l in f.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")]
    header = lines[0].split("\t")
    data = [l.split("\t") for l in lines[1:] if l.split("\t")[0].startswith("USGS")]
    df = pd.DataFrame(data, columns=header)
    df = df[["site_no", "station_nm", "site_tp_cd", "dec_lat_va", "dec_long_va"]].rename(
        columns={
            "site_no": "source_id",
            "station_nm": "name",
            "site_tp_cd": "site_type",
            "dec_lat_va": "lat",
            "dec_long_va": "lon",
        }
    )
    df["dataset"] = "usgs"
    df["provider"] = "USGS"
    return df


def load_echo_points() -> pd.DataFrame:
    f = RAW / "epa_echo_cuyahoga" / "facilities_huc04110002.json"
    data = json.loads(f.read_text(encoding="utf-8"))["Results"]["Facilities"]
    df = pd.DataFrame(
        [
            {
                "source_id": x.get("SourceID"),
                "name": x.get("CWPName"),
                "site_type": "NPDES facility",
                "lat": x.get("FacLat"),
                "lon": x.get("FacLong"),
                "provider": "EPA ECHO",
            }
            for x in data
        ]
    )
    df["dataset"] = "echo"
    return df


def load_points() -> pd.DataFrame:
    df = pd.concat([load_wqp_points(), load_usgs_points(), load_echo_points()], ignore_index=True)
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])
    df = df[(df["lat"].between(-90, 90)) & (df["lon"].between(-180, 180))]
    print(f"[points] total {len(df)} sites: " + df.groupby("dataset").size().to_dict().__str__())
    return df


# ---------------------------------------------------------------- snap
def snap_points(points: pd.DataFrame, flow: "gpd.GeoDataFrame") -> pd.DataFrame:
    import geopandas as gpd

    pt = gpd.GeoDataFrame(
        points, geometry=gpd.points_from_xy(points["lon"], points["lat"]), crs="EPSG:4326"
    )
    pt = pt.to_crs(UTM_CRS)
    fl = flow.to_crs(UTM_CRS)

    joined = gpd.sjoin_nearest(pt, fl[["COMID", "geometry"]], how="left", distance_col="snap_dist_m")
    joined = joined.drop(columns=["index_right"], errors="ignore")
    # 等距（如汇流口）可能产生重复匹配，保留每个站点最近的唯一 COMID
    joined = joined.drop_duplicates(subset=["dataset", "source_id"], keep="first")
    joined["snap_flag"] = "ok"
    joined.loc[joined["snap_dist_m"] > SNAP_MAX_M, "snap_flag"] = "far"
    joined.loc[joined["snap_dist_m"].isna(), "snap_flag"] = "unmatched"
    print("[snap] COMID 匹配统计:\n" + joined.groupby("snap_flag").size().to_string())
    return joined


# ---------------------------------------------------------------- topology
def build_topology(flow: "gpd.GeoDataFrame") -> nx.DiGraph:
    g = nx.DiGraph()
    for _, r in flow[["COMID", "FromNode", "ToNode", "LengthKM"]].iterrows():
        g.add_edge(int(r["FromNode"]), int(r["ToNode"]), comid=int(r["COMID"]), length=r["LengthKM"])
    print(f"[topo] nodes={g.number_of_nodes()} edges={g.number_of_edges()}")
    print(f"[topo] 弱连通分量数={nx.number_weakly_connected_components(g)}")
    return g


def upstream_comids(rev: nx.DiGraph, comid_to_from: dict[int, int], comid: int) -> set[int]:
    """返回流入河段 comid 的所有上游河段 COMID（含自身）。

    图 rev 为原图的反向（边方向 ToNode -> FromNode）。从 comid 的 FromNode
    出发做 DFS，途经的反向边即为上游河段。comid_to_from 预建索引避免逐次线性扫描。
    """
    from_node = comid_to_from.get(comid)
    if from_node is None:
        return set()
    out: set[int] = set()
    stack = [from_node]
    seen_nodes = {from_node}
    while stack:
        n = stack.pop()
        for m in rev[n]:
            if m not in seen_nodes:
                seen_nodes.add(m)
                # 反向边 n->m 对应原边 m->n，即上游河段
                out.add(rev[n][m]["comid"])
                stack.append(m)
    return out


# ---------------------------------------------------------------- main
def main() -> None:
    gdb_dir = extract_gdb()
    layer = find_flowline_layer(gdb_dir)
    flow = read_flowlines(gdb_dir, layer)

    points = load_points()
    snapped = snap_points(points, flow)
    g = build_topology(flow)

    # --- interim：空间匹配结果 ---
    interim_ds = INTERIM / "nhdplus_hr_cuyahoga"
    interim_ds.mkdir(parents=True, exist_ok=True)
    flow.to_file(interim_ds / "flowlines.geojson", driver="GeoJSON")
    snapped_cols = [
        c
        for c in ["dataset", "source_id", "name", "site_type", "provider",
                  "lat", "lon", "COMID", "snap_dist_m", "snap_flag"]
        if c in snapped.columns
    ]
    snapped[snapped_cols].to_csv(interim_ds / "sites_snapped.csv", index=False)

    # --- processed：标准化 + 拓扑 ---
    pdir = PROCESSED / "cuyahoga_network"
    pdir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"COMID": d["comid"], "FromNode": u, "ToNode": v, "LengthKM": d.get("length")}
            for u, v, d in g.edges(data=True)
        ]
    ).to_csv(pdir / "flow_edges.csv", index=False)
    import pickle

    with open(pdir / "flow_network.pkl", "wb") as fh:
        pickle.dump(g, fh)

    # 上游设施示例：每个 WQP/USGS 站点 -> 上游 NPDES 设施数
    echo_comids = set(snapped.loc[snapped["dataset"] == "echo", "COMID"].dropna().astype(int))
    rev = g.reverse(copy=True)
    comid_to_from = {d["comid"]: u for u, _v, d in g.edges(data=True)}
    mon = snapped[snapped["dataset"].isin(["wqp", "usgs"])]
    cache: dict[int, set[int]] = {}
    rows = []
    for _, m in mon.iterrows():
        if pd.isna(m["COMID"]):
            continue
        cid = int(m["COMID"])
        ups = cache.get(cid)
        if ups is None:
            ups = upstream_comids(rev, comid_to_from, cid)
            cache[cid] = ups
        rows.append(
            {
                "station_id": m["source_id"],
                "station_name": m["name"],
                "dataset": m["dataset"],
                "COMID": cid,
                "upstream_facilities": len(ups & echo_comids),
            }
        )
    demo = pd.DataFrame(rows).sort_values("upstream_facilities", ascending=False)
    demo.to_csv(pdir / "stations_upstream_facilities.csv", index=False)
    print(f"[demo] 站点上游设施统计（Top 10）:\n{demo.head(10).to_string(index=False)}")
    print(f"[done] 输出已写入 {INTERIM} 与 {PROCESSED}")


if __name__ == "__main__":
    main()
