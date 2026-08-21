#!/usr/bin/env python3
"""把俄亥俄州全州 EFF 违规记录流式过滤到 Cuyahoga HUC8 的 231 个设施。

原始 OH_NPDES_EFF_VIOLATIONS.zip 解压后约 288 MB（全州）。按 NPDES_ID（列 1）
匹配 cuyahoga_npdes_ids.txt（与 facilities_huc04110002.json 的 SourceID 同格式）。
"""
import subprocess
import csv
import io

RAW = "data/raw/epa_echo_cuyahoga/OH_NPDES_EFF_VIOLATIONS.zip"
IDS = "data/raw/epa_echo_cuyahoga/cuyahoga_npdes_ids.txt"
OUT = "data/raw/epa_echo_cuyahoga/OH_NPDES_EFF_VIOLATIONS_cuyahoga_huc8.csv"

ids = {l.strip().upper() for l in open(IDS, encoding="utf-8") if l.strip()}
p = subprocess.Popen(
    ["unzip", "-p", RAW, "OH_NPDES_EFF_VIOLATIONS.csv"],
    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
)
r = csv.reader(io.TextIOWrapper(p.stdout, encoding="utf-8", errors="replace"))
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    header = next(r)
    w.writerow(header)
    perm_col = next((i for i, c in enumerate(header) if c.strip() == "NPDES_ID"), 0)
    matched = total = 0
    for row in r:
        total += 1
        if len(row) > perm_col and row[perm_col].strip().upper() in ids:
            w.writerow(row)
            matched += 1
p.stdout.close()
print(f"kept {matched} / {total} rows -> {OUT}")
