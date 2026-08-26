#!/usr/bin/env python3
"""CNEMC 国控断面实时水质前向存档。

每次运行:
1. 拉取国家地表水水质自动监测实时发布系统全部断面当前快照(分页,页间隔 1s,正常使用强度);
2. 原始 JSON 原样存入 data/raw/cnemc_surface_water_realtime/archive/<时间戳>.json(不修改);
3. 解析为长表追加到 data/interim/cnemc_archive/all_stations.csv,
   按(断面名称,监测时间)去重——重复运行不产生重复记录。

监测时间格式为 'MM-DD HH:MM',不含年份;追加时打上抓取年份(跨年边界见 notes)。

定时部署(任选其一):
  crontab:  17 1,5,9,13,17,21 * * *  cd /path/to/AquaDetective && /usr/bin/python3 tools/cnemc_archive.py >> /tmp/cnemc_archive.log 2>&1
  (官方 4h 一轮:约 00/04/08/12/16/20 点出数,错峰 1 小时 17 分抓取)

手动运行:python3 tools/cnemc_archive.py
"""
from __future__ import annotations

import csv
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data/raw/cnemc_surface_water_realtime/archive"
OUT_CSV = ROOT / "data/interim/cnemc_archive/all_stations.csv"

API = "https://szzdjc.cnemc.cn:8070/GJZ/Ajax/Publish.ashx"
PAGE_SIZE = 500
PAGE_DELAY_S = 1.0

HEADERS = ["省份", "流域", "断面名称", "监测时间", "水质类别", "水温(℃)", "pH(无量纲)",
           "溶解氧(mg/L)", "电导率(μS/cm)", "浊度(NTU)", "高锰酸盐指数(mg/L)",
           "氨氮(mg/L)", "总磷(mg/L)", "总氮(mg/L)", "叶绿素α(mg/L)", "藻密度(cells/L)"]

TAG = re.compile(r"<[^>]+>")


def fetch_page(page_index: int) -> dict:
    data = urllib.parse.urlencode({
        "AreaID": "", "RiverID": "", "MNName": "",
        "PageIndex": page_index, "PageSize": PAGE_SIZE, "action": "getRealDatas",
    }).encode()
    req = urllib.request.Request(API, data=data, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fetch_all() -> tuple[list[list[str]], dict]:
    first = fetch_page(1)
    total_pages = int(first.get("total", 1))
    rows = list(first["tbody"])
    for p in range(2, total_pages + 1):
        time.sleep(PAGE_DELAY_S)
        rows.extend(fetch_page(p)["tbody"])
    return rows, first


def clean(cell: str) -> str:
    """单元格去 HTML 标签:'<span title=...>29.2</span>' → '29.2';'--' 保留为占位。"""
    return TAG.sub("", str(cell)).strip()


def main() -> None:
    now = datetime.now()
    rows, first_page = fetch_all()
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 拉取 {len(rows)} 个断面 "
      f"(系统记录数 {first_page.get('records')})")

    # 1) 原始快照(raw 不修改)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"cnemc_snapshot_{now:%Y%m%d_%H%M%S}.json"
    raw_path.write_text(json.dumps(
        {"fetched_at": now.isoformat(timespec="seconds"),
         "records": first_page.get("records"), "thead": first_page.get("thead"),
         "tbody": rows},
        ensure_ascii=False))
    print("原始快照:", raw_path)

    # 2) 长表追加(去重)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    existing: set[tuple[str, str]] = set()
    if OUT_CSV.exists():
        with open(OUT_CSV, newline="") as f:
            for rec in csv.DictReader(f):
                existing.add((rec["断面名称"], rec["监测时间"]))

    year = now.year
    new_rows = 0
    with open(OUT_CSV, "a", newline="") as f:
        w = csv.writer(f)
        if not existing and OUT_CSV.stat().st_size == 0:
            w.writerow(["抓取年份", *HEADERS])
        for row in rows:
            if len(row) < len(HEADERS):
                continue
            key = (row[2], row[3])
            if key in existing:
                continue
            w.writerow([year, row[0], row[1], row[2], row[3], row[4],
                        *[clean(c) for c in row[5:16]]])
            existing.add(key)
            new_rows += 1
    print(f"追加 {new_rows} 条新记录 → {OUT_CSV}")


if __name__ == "__main__":
    main()
