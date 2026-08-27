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
                # 等到 report_ready 才 break(报告落盘后才会推送),否则会查到"报告尚未生成"
                if msg["type"] in ("failed", "report_ready", "error"):
                    break
        print(f"WS 共收到 {len(msgs)} 条消息（含 connected）")

        # ===== talks 去重校验(验证"重复内容"bug 修复)=====
        talks = [m for m in msgs if m["type"] == "agent_talk"]
        talk_keys = [(m["data"]["agent"], m["data"]["text"]) for m in talks]
        dup_talks = len(talk_keys) - len(set(talk_keys))
        steps = [m for m in msgs if m["type"] == "step"]
        step_keys = [m["data"].get("step_id") for m in steps]
        dup_steps = len(step_keys) - len(set(step_keys))
        print(f"talks: {len(talks)} 条, 重复 {dup_talks}; steps: {len(steps)} 条, 重复 {dup_steps}")

        # ===== 模拟重连补齐:GET /investigations 返回的 stream 是否含重复 =====
        st = (await client.get(f"/investigations/{inv}")).json()
        replay_talks = [m for m in (st.get("stream") or []) if m["type"] == "agent_talk"]
        replay_keys = [(m["data"]["agent"], m["data"]["text"]) for m in replay_talks]
        replay_dup = len(replay_keys) - len(set(replay_keys))
        print(f"重放 stream: talks {len(replay_talks)} 条, 重复 {replay_dup}")
        if dup_talks or replay_dup:
            print("[FAIL] 检测到重复 talks(前端会跳出重复内容)")
        else:
            print("[OK] 无重复 talks")
        print(f"调查状态: {st['status']} conclusion={json.dumps(st['conclusion'], ensure_ascii=False)[:120]}")
        rep = (await client.get(f"/investigations/{inv}/report")).text
        print(f"报告 {len(rep)} 字符, 标题: {rep.splitlines()[0]}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "evt_001"))
