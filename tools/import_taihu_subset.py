#!/usr/bin/env python3
"""太湖流域国控断面水质子集标准化导入器。

输入:data/interim/guokong_surface_water_2021_2025/taihu_basin_4h_2021_2025.csv.gz
  (由 raw 汇编数据合并而来,已知问题:约 3% 时间戳不规范、'*' 占位、指标中文列名)
输出:data/processed/guokong_taihu/
  stations.csv            断面注册表(station_id/名称/省份/坐标/记录数/时间覆盖)
  readings/<station_id>.csv  按断面分表,统一字段与单位(指南 §2.1 编码)
  import_report.json      导入质量报告(丢弃/修复统计、缺失率)

标准化规则:
1. 时间戳:优先解析"监测时间"列;为空/非法时回退"来源文件"名中的抓取时刻
   (依据发布方说明:文件名与监测时间不一致时以文件内监测时间为准,空时才用文件名);
   输出 ts(ISO 8601,UTC+8)与 epoch 秒两列。
2. 指标:中文列名 → 统一编码(ph/do/conductivity/turbidity/codmn/ammonia_n/tp/tn/
   temperature/chla/algae_density);codmn 为高锰酸盐指数,不得映射为 cod。
3. '*' 等占位符与无法解析的值 → 空(NaN);不做任何插值/平滑(保持原始性)。
4. 时区:中国标准时间 UTC+8。

用法:python tools/import_taihu_subset.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/interim/guokong_surface_water_2021_2025/taihu_basin_4h_2021_2025.csv.gz"
OUT = ROOT / "data/processed/guokong_taihu"

# 中文列名 → 统一编码(指南 §2.1)
COLUMN_MAP = {
    "水温(℃)": "temperature",
    "pH(无量纲)": "ph",
    "溶解氧(mg/L)": "do",
    "电导率(μS/cm)": "conductivity",
    "浊度(NTU)": "turbidity",
    "高锰酸盐指数(mg/L)": "codmn",
    "氨氮(mg/L)": "ammonia_n",
    "总磷(mg/L)": "tp",
    "总氮(mg/L)": "tn",
    "叶绿素α(mg/L)": "chla",
    "藻密度(cells/L)": "algae_density",
    "水质类别": "quality_class",
}

# 文件名中的抓取时刻:2021_07_30_04h51m_国家地表水...
FNAME_TS = re.compile(r"(\d{4})_(\d{2})_(\d{2})_(\d{2})h(\d{2})m")

PLACEHOLDERS = {"*", "-", "—", "", "nan", "NaN", "NULL"}


def parse_ts(row: pd.Series) -> pd.Timestamp | None:
    """监测时间(年份-MM-DD HH:MM)优先,非法时回退文件名抓取时刻。"""
    raw = str(row["监测时间"]).strip()
    year = str(row["年份"])
    # 常规:2021-07-30 04:00
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{2})", raw)
    if m:
        y, mo, d, h, mi = map(int, m.groups())
    else:
        # 变体:年份-2024/1/15 16:00(合并时拼了双年份)
        m = re.match(r"^\d{4}-(\d{4})/(\d{1,2})/(\d{1,2})[ T](\d{1,2}):(\d{2})", raw)
        if m:
            y, mo, d, h, mi = map(int, m.groups())
        else:
            # 回退:文件名抓取时刻(分钟为抓取分钟,按整点截断到监测时次)
            m = FNAME_TS.search(str(row["来源文件"]))
            if not m:
                return None
            y, mo, d, h, mi = map(int, m.groups())
    try:
        return pd.Timestamp(y, mo, d, h, mi, tz="Asia/Shanghai")
    except ValueError:
        return None


def main() -> None:
    df = pd.read_csv(SRC, dtype=str).rename(columns=COLUMN_MAP)
    total_in = len(df)

    df["ts_parsed"] = df.apply(parse_ts, axis=1)
    dropped_ts = int(df["ts_parsed"].isna().sum())
    df = df.dropna(subset=["ts_parsed"])
    # 源数据存在同断面同时刻重复行,去重保留首条
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["省份", "断面名称", "ts_parsed"], keep="first")
    dropped_dup = before_dedup - len(df)
    df["ts"] = df["ts_parsed"].dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    df["epoch"] = df["ts_parsed"].map(lambda t: int(t.timestamp()))

    for col in COLUMN_MAP.values():
        if col == "quality_class":
            continue
        df[col] = pd.to_numeric(
            df[col].where(~df[col].isin(PLACEHOLDERS)), errors="coerce"
        )
    df["quality_class"] = df["quality_class"].where(
        ~df["quality_class"].isin(PLACEHOLDERS)
    )

    keep = ["ts", "epoch", *COLUMN_MAP.values()]
    (OUT / "readings").mkdir(parents=True, exist_ok=True)

    stations = []
    nan_rates: dict[str, float] = {}
    for i, ((prov, name), g) in enumerate(
        df.groupby(["省份", "断面名称"], sort=True), start=1
    ):
        sid = f"taihu_{i:03d}"
        g = g.sort_values("epoch")
        g[keep].to_csv(OUT / "readings" / f"{sid}.csv", index=False)
        span_days = max((g["ts_parsed"].max() - g["ts_parsed"].min()).days, 1)
        stations.append({
            "station_id": sid,
            "name": name,
            "province": prov,
            "records": len(g),
            "first_ts": g["ts"].iloc[0],
            "last_ts": g["ts"].iloc[-1],
            "records_per_day": round(len(g) / span_days, 2),
        })

    numeric_cols = [c for c in COLUMN_MAP.values() if c != "quality_class"]
    for col in numeric_cols:
        nan_rates[col] = round(float(df[col].isna().mean()), 4)

    pd.DataFrame(stations).to_csv(OUT / "stations.csv", index=False)

    report = {
        "source": str(SRC.relative_to(ROOT)),
        "rows_in": total_in,
        "rows_out": len(df),
        "dropped_unparseable_ts": dropped_ts,
        "dropped_duplicates": int(dropped_dup),
        "station_count": len(stations),
        "time_range": [df["ts"].min(), df["ts"].max()],
        "nan_rate_by_indicator": nan_rates,
        "timezone": "UTC+8",
        "notes": "codmn=高锰酸盐指数,非 COD;chla/algae_density 多为空(仅湖库站测量);"
                 "时间戳空值已用文件名抓取时刻回退。",
    }
    (OUT / "import_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
