#!/usr/bin/env python3
"""CNEMC 国控断面实时水质前向存档。

每次运行:
1. 拉取国家地表水水质自动监测实时发布系统全部断面当前快照(分页,页间隔 2s,降低限速触发);
2. 原始 JSON 原样存入 data/raw/cnemc_surface_water_realtime/archive/<时间戳>.json(不修改);
3. 解析为长表追加到 data/interim/cnemc_archive/all_stations.csv,
   按(抓取年份,断面名称,监测时间)去重——重复运行不产生重复记录,跨年不误并。

监测时间格式为 'MM-DD HH:MM',不含年份;追加时打上抓取年份并参与去重键。

健康检查:main() 断言拉取行数 > 0 且与系统 records 偏差 < 10%,不达标 sys.exit(1),
杜绝"页1成功后续全失败"或"空响应"伪装成全量成功(历史 8 轮 6 失败的最严重静默路径)。

定时部署(任选其一):
  crontab(本地中国 IP,主力轨,已证 100% 成功):
    13 1,5,9,13,17,21 * * *  cd /path/to/AquaDetective && /usr/bin/python3 tools/cnemc_archive.py >> /tmp/cnemc_archive.log 2>&1
  GitHub Actions(异地冗余备份):见 .github/workflows/cnemc-archive.yml

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
PAGE_DELAY_S = 2.0  # 页间延时,降低对政务 API 的限速触发

HEADERS = ["省份", "流域", "断面名称", "监测时间", "水质类别", "水温(℃)", "pH(无量纲)",
           "溶解氧(mg/L)", "电导率(μS/cm)", "浊度(NTU)", "高锰酸盐指数(mg/L)",
           "氨氮(mg/L)", "总磷(mg/L)", "总氮(mg/L)", "叶绿素α(mg/L)", "藻密度(cells/L)"]

TAG = re.compile(r"<[^>]+>")


def fetch_page(page_index: int, retries: int = 3) -> dict:
    """拉取单页,带重试。GitHub Actions runner 访问 CNEMC API 不稳定,
    单页失败重试 3 次(间隔递增),仍失败则抛异常让上层处理。"""
    data = urllib.parse.urlencode({
        "AreaID": "", "RiverID": "", "MNName": "",
        "PageIndex": page_index, "PageSize": PAGE_SIZE, "action": "getRealDatas",
    }).encode()
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(API, data=data, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            last_err = e
            wait = (attempt + 1) * 5
            print(f"  第 {page_index} 页拉取失败(第 {attempt+1}/{retries} 次): {e}, {wait}s 后重试")
            time.sleep(wait)
    raise RuntimeError(f"第 {page_index} 页重试 {retries} 次仍失败: {last_err}")


def fetch_all() -> tuple[list[list[str]], dict]:
    first = fetch_page(1)
    total_pages = int(first.get("total", 1))
    # 防御:total 若是记录数(常见 API 命名歧义)会跑几千空页,设上限 50 页
    if total_pages > 50 or total_pages < 1:
        print(f"  [警告] total={total_pages} 异常,按 1 页处理")
        total_pages = 1
    rows = list(first.get("tbody", []))
    for p in range(2, total_pages + 1):
        time.sleep(PAGE_DELAY_S)
        try:
            page = fetch_page(p)
            rows.extend(page.get("tbody", []))
        except RuntimeError as e:
            print(f"  [警告] {e},跳过该页,继续后续页")
            continue
    return rows, first


def clean(cell: str) -> str:
    """单元格去 HTML 标签:'<span title=...>29.2</span>' → '29.2';'--' 保留为占位。"""
    return TAG.sub("", str(cell)).strip()


def main() -> None:
    now = datetime.now()
    rows, first_page = fetch_all()
    records = first_page.get("records")
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 拉取 {len(rows)} 个断面 "
      f"(系统记录数 {records})")

    # ===== 健康检查断言(防静默假成功)=====
    # 1) 空响应:rows 为 0 说明 API 返回空壳,不提交
    if not rows:
        print("[FAILED] 拉取 0 行(空响应),退出不提交", flush=True)
        raise SystemExit(1)
    # 2) 覆盖率:拉取行数 vs 系统 records 偏差 < 10%(防页1成功后续全失败的假全量)
    if records:
        try:
            rec_n = int(records)
            if rec_n > 0:
                coverage = len(rows) / rec_n
                if coverage < 0.90:
                    print(f"[FAILED] 覆盖率 {coverage:.1%} < 90%(拉 {len(rows)}/系统 {rec_n}),"
                          f"疑后续页全失败,退出不提交", flush=True)
                    raise SystemExit(1)
                print(f"[OK] 覆盖率 {coverage:.1%}(拉 {len(rows)}/系统 {rec_n})")
        except (ValueError, TypeError):
            pass
    # 3) 数据新鲜度:与已存 CSV 末行比对,本次最新时次不应早于已存最新
    #    用 (抓取年份 + 监测时间) 拼成可比较的完整时间戳,防跨年字符串误杀
    #    (年初 '01-01' 字典序 < '12-31' 会误判,必须带年份比)
    year = now.year
    if OUT_CSV.exists():
        with open(OUT_CSV, newline="") as f:
            recs = list(csv.DictReader(f))
        if recs:
            last_year = recs[-1].get("抓取年份", str(year))
            last_ts = recs[-1]["监测时间"]
            cur_max = max((r[3] for r in rows if len(r) > 3), default="")
            # 拼成 "YYYY MM-DD HH:MM" 字符串比较(年份前置,字典序=时间序)
            last_full = f"{last_year} {last_ts}"
            cur_full = f"{year} {cur_max}"
            if cur_full < last_full:
                print(f"[FAILED] 本次最新时次 {cur_full} 早于已存 {last_full},"
                      f"疑 API 返回缓存旧数据,退出不提交", flush=True)
                raise SystemExit(1)
            # 时次停滞断言:本次最新时次应严格晚于已存,或本次含已存未有的新时次
            # (防"末次相等仅补全断面"被放行——与前向存档目标相悖)
            if cur_full == last_full:
                print(f"[FAILED] 本次最新时次 {cur_full} 与已存末次相同,"
                      f"无新时次(仅补全断面,前向存档停滞),退出不提交", flush=True)
                raise SystemExit(1)

    # 1) 原始快照(raw 不修改)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"cnemc_snapshot_{now:%Y%m%d_%H%M%S}.json"
    raw_path.write_text(json.dumps(
        {"fetched_at": now.isoformat(timespec="seconds"),
         "records": records, "thead": first_page.get("thead"),
         "tbody": rows},
        ensure_ascii=False))
    print("原始快照:", raw_path)

    # 2) 长表追加(去重,键含抓取年份防跨年误并)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    existing: set[tuple[str, str, str]] = set()
    if OUT_CSV.exists():
        with open(OUT_CSV, newline="") as f:
            for rec in csv.DictReader(f):
                existing.add((rec["抓取年份"], rec["断面名称"], rec["监测时间"]))

    year = str(now.year)
    new_rows = 0
    with open(OUT_CSV, "a", newline="") as f:
        w = csv.writer(f)
        if not existing and OUT_CSV.stat().st_size == 0:
            w.writerow(["抓取年份", *HEADERS])
        for row in rows:
            if len(row) < len(HEADERS):
                continue
            key = (year, row[2], row[3])
            if key in existing:
                continue
            w.writerow([year, row[0], row[1], row[2], row[3], row[4],
                        *[clean(c) for c in row[5:16]]])
            existing.add(key)
            new_rows += 1
    print(f"追加 {new_rows} 条新记录 → {OUT_CSV}")


if __name__ == "__main__":
    main()
