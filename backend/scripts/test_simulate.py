"""simulate 接口测试：注入事件 + 重置世界。"""
import httpx

BASE = "http://127.0.0.1:8000/api/v1"

with httpx.Client(base_url=BASE, timeout=120) as c:
    r = c.post("/simulate/inject", json={
        "etype": "sudden", "source_id": "ent_10", "severity": "medium",
        "onset_day": 25, "duration_d": 2, "mass_kg": 50,
    })
    print("inject:", r.status_code, r.json() if r.status_code == 200 else r.text)

    r = c.get("/events?limit=5")
    evs = r.json()
    print("最新事件:", evs[0]["id"], evs[0]["etype"], evs[0]["truth_source"], "status:", evs[0]["status"])

    # 验证注入事件确实写进了时序
    r = c.get("/series", params={"station": "st_05", "indicator": "cod", "from": 1737500000, "to": 1737900000})
    data = r.json()["data"]
    vals = [d["value"] for d in data]
    print(f"st_05 cod 注入窗口: {len(vals)} 点, max={max(vals):.1f}")

    # 断面 EEM
    r = c.get("/stations/st_02/eem", params={"event_id": "evt_001"})
    eem = r.json()
    print("st_02 EEM:", eem["dominant"], "矩阵", len(eem["eem"]), "x", len(eem["eem"][0]))

    # 指纹
    r = c.get("/watershed/enterprises/ent_02/fingerprint")
    fp = r.json()
    print("ent_02 指纹:", fp["fingerprint"]["pollutants"])

    # 重置世界
    r = c.post("/simulate/reset", params={"seed": 20250601})
    print("reset:", r.status_code, r.json())
    r = c.get("/events")
    print("重置后事件数:", len(r.json()))
