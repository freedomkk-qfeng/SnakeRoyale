import argparse
import asyncio
import json
import sys
from pathlib import Path

import aiohttp


ROOT = Path(__file__).resolve().parents[2]
CLIENT_DIR = ROOT / "client"

if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

import client as snake_client


async def _read_messages(ws, count: int):
    for _ in range(count):
        message = await ws.receive()
        if message.type != aiohttp.WSMsgType.TEXT:
            return
        json.loads(message.data)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    key = await snake_client.register(args.server, args.name)
    ws_url = f"{args.server}/ws?key={key}".replace("http://", "ws://").replace("https://", "wss://")

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(ws_url) as first_ws:
            await _read_messages(first_ws, 2)
            await asyncio.sleep(0.35)
        await asyncio.sleep(0.01)
        async with session.ws_connect(ws_url) as second_ws:
            await _read_messages(second_ws, 2)
            await asyncio.sleep(0.9)


if __name__ == "__main__":
    asyncio.run(main())