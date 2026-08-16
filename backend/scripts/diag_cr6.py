"""诊断：st_02 cr6 基线偏高的原因排查。"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.topology import impact_matrix
from app.data.watershed_builder import load_watershed

ws = load_watershed("app/data/watershed_config.json")
atten = impact_matrix(ws)
print("== st_02 上游企业衰减与 cr6 理论贡献 ==")
for ent in ws["enterprises"]:
    fac = atten.get((ent["id"], "st_02"))
    if not fac:
        continue
    pat = ent["discharge_pattern"]
    conc_cr6 = 120 if ent["industry"] == "electroplating" else 0
    # cr6 原水浓度从 profiles 读取
    import json as j
    prof = j.load(open("app/data/industry_profiles.json", encoding="utf-8"))
    conc_cr6 = prof[ent["industry"]]["outfall_conc"].get("cr6", 0)
    contrib = conc_cr6 * pat.get("treat_rate", 1.0) * fac
    print(f"{ent['id']:8s} {ent['name']:10s} fac={fac:.6f} treat={pat.get('treat_rate')} "
          f"cr6_conc={conc_cr6} contrib={contrib:.6f}")

print("\n== st_02 cr6 前 10 天峰值时刻 ==")
conn = sqlite3.connect("data/aqua.db")
conn.row_factory = sqlite3.Row
from datetime import datetime, timezone
for row in conn.execute(
    "SELECT ts, value FROM readings WHERE station_id='st_02' AND indicator='cr6' "
    "AND ts < ? ORDER BY value DESC LIMIT 5", (1735689600 + 10 * 86400,)):
    t = datetime.fromtimestamp(row["ts"], tz=timezone.utc)
    print(f"  {t.isoformat()}  value={row['value']:.4f}")
