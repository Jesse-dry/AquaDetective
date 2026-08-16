"""数据层验证：seed 后检查事件信号是否真实可见、基线是否合理。"""
import sqlite3

conn = sqlite3.connect("data/aqua.db")
conn.row_factory = sqlite3.Row

print("== 事件信号检查 ==")
for ev in conn.execute("SELECT * FROM events ORDER BY onset_ts"):
    st, inds = ev["station_id"], ["cr6", "cod", "ammonia"]
    for ind in inds:
        before = conn.execute(
            "SELECT AVG(value) m FROM readings WHERE station_id=? AND indicator=? AND ts < ?",
            (st, ind, ev["onset_ts"])).fetchone()["m"]
        after = conn.execute(
            "SELECT MAX(value) m FROM readings WHERE station_id=? AND indicator=? AND ts >= ?",
            (st, ind, ev["onset_ts"])).fetchone()["m"]
        if after and before and after > before * 1.3:
            print(f"{ev['id']} {ev['etype']:8s} @{st} {ind:7s} "
                  f"baseline={before:.3f} peak={after:.3f} ({after/before:.1f}x)")

print("\n== 基线合理性（非事件时段）==")
for st in ["st_02", "st_09"]:
    for ind in ["cod", "ammonia", "tp", "cr6", "ph"]:
        row = conn.execute(
            "SELECT AVG(value) m, MIN(value) mn, MAX(value) mx FROM readings "
            "WHERE station_id=? AND indicator=? AND ts < 1735689600+10*86400",
            (st, ind)).fetchone()
        print(f"{st} {ind:7s} avg={row['m']:.3f} range=[{row['mn']:.3f},{row['mx']:.3f}]")

print("\n== 企业指纹库 ==")
for fp in conn.execute("SELECT enterprise_id, pollutants FROM fingerprints LIMIT 4"):
    print(fp["enterprise_id"], fp["pollutants"])
