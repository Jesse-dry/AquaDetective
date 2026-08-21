#!/usr/bin/env python3
"""Stream-filter the Ohio FY2024 NPDES DMR/LIMITS CSVs down to the Cuyahoga HUC8 facilities.

The raw zips are Ohio state-wide (465 MB DMRS + 71 MB LIMITS uncompressed). This script
streams them with `unzip -p` and keeps only rows whose EXTERNAL_PERMIT_NMBR (col 2) matches
the 231 NPDES SourceIDs extracted from ECHO get_qid for HUC8 04110002.
"""
import subprocess
import csv
import io
import os

RAW = "data/raw/epa_echo_cuyahoga/OH_FY2024_NPDES_DMRS_LIMITS.zip"
IDS_FILE = "data/raw/epa_echo_cuyahoga/cuyahoga_npdes_ids.txt"
OUT_DIR = "data/raw/epa_echo_cuyahoga/"


def load_ids(path):
    ids = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            x = line.strip().upper()
            if x:
                ids.add(x)
    return ids


def filter_csv(zip_path, inner_name, ids, out_path):
    p = subprocess.Popen(
        ["unzip", "-p", zip_path, inner_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    reader = csv.reader(io.TextIOWrapper(p.stdout, encoding="utf-8", errors="replace"))
    with open(out_path, "w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        header = next(reader)
        writer.writerow(header)
        # locate permit-number column (EXTERNAL_PERMIT_NMBR) by header name
        perm_col = next((i for i, h in enumerate(header) if h.strip() == "EXTERNAL_PERMIT_NMBR"), 1)
        matched = 0
        total = 0
        for row in reader:
            total += 1
            if len(row) > perm_col and row[perm_col].strip().upper() in ids:
                writer.writerow(row)
                matched += 1
    p.stdout.close()
    return matched, total, perm_col


def main():
    ids = load_ids(IDS_FILE)
    print(f"loaded {len(ids)} NPDES ids")
    for inner in ["OH_FY2024_NPDES_DMRS.csv", "OH_FY2024_NPDES_LIMITS.csv"]:
        out = os.path.join(OUT_DIR, inner.replace(".csv", "_cuyahoga_huc8.csv"))
        matched, total, perm_col = filter_csv(RAW, inner, ids, out)
        print(f"{inner}: kept {matched} / {total} rows (permit col {perm_col}) -> {out}")


if __name__ == "__main__":
    main()
