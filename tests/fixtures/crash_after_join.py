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


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    key = await snake_client.register(args.server, args.name)
    ws_url = f"{args.server}/ws?key={key}".replace("http://", "ws://").replace("https://", "wss://")

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(ws_url) as ws:
            for _ in range(2):
                message = await ws.receive()
                if message.type != aiohttp.WSMsgType.TEXT:
                    break
                json.loads(message.data)
            await asyncio.sleep(0.3)


if __name__ == "__main__":
    asyncio.run(main())