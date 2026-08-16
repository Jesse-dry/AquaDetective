"""端到端 API 测试：触发调查 → WS 流式收推理 → 状态 → 报告。"""
import asyncio
import json
import sys

import httpx
import websockets

BASE = "http://127.0.0.1:8000/api/v1"
WS = "ws://127.0.0.1:8000/api/v1/ws"


async def main(event_id: str) -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        r = await client.post(f"/events/{event_id}/investigate")
        r.raise_for_status()
        inv = r.json()["investigation_id"]
        print(f"investigation_id: {inv}")

        msgs = []
        async with websockets.connect(f"{WS}?investigation_id={inv}") as ws:
            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
                except asyncio.TimeoutError:
                    print("WS timeout, breaking")
                    break
                msgs.append(msg)
                if msg["type"] in ("conclusion", "failed", "report_ready", "error"):
                    print(f"  <- {msg['type']}: {json.dumps(msg['data'], ensure_ascii=False)[:150]}")
                if msg["type"] in ("conclusion", "failed", "report_ready", "error"):
                    break
        print(f"WS 共收到 {len(msgs)} 条消息（含 connected）")

        st = (await client.get(f"/investigations/{inv}")).json()
        print(f"调查状态: {st['status']} conclusion={json.dumps(st['conclusion'], ensure_ascii=False)[:120]}")
        rep = (await client.get(f"/investigations/{inv}/report")).text
        print(f"报告 {len(rep)} 字符, 标题: {rep.splitlines()[0]}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "evt_001"))
