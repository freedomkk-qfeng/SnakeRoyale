#!/usr/bin/env python3
"""
批量启动示例 AI 客户端

用法:
    python run_clients.py -n 10                          # 启动 10 个客户端
    python run_clients.py -n 5 --server http://host:15000  # 指定服务器地址
"""

import argparse
import asyncio
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Import the real client module
import client as snake_client


def read_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


async def run_one(server: str, name: str, reconnect_delay_ms: int):
    """Run a single client with reconnection."""
    key = await snake_client.register(server, name)
    reconnect_delay_seconds = max(reconnect_delay_ms, 1) / 1000.0
    attempt = 0
    while True:
        attempt += 1
        try:
            await snake_client.play(server, key)
        except Exception as e:
            logger.warning(
                f"[{name}] Disconnected: {e}, reconnecting in {reconnect_delay_seconds:.2f}s... (attempt {attempt})"
            )
            await asyncio.sleep(reconnect_delay_seconds)


async def main():
    parser = argparse.ArgumentParser(description="批量启动贪吃蛇 AI 客户端")
    parser.add_argument("-n", "--count", type=int, default=5, help="客户端数量 (默认: 5)")
    parser.add_argument("--server", default="http://localhost:15000", help="服务器地址")
    parser.add_argument("--prefix", default="Bot", help="名字前缀 (默认: Bot)")
    parser.add_argument(
        "--reconnect-delay-ms",
        type=int,
        default=read_positive_int_env("SNAKE_CLIENT_RECONNECT_DELAY_MS", 3000),
        help="客户端断线重连间隔（毫秒，默认读取 SNAKE_CLIENT_RECONNECT_DELAY_MS 或 3000）",
    )
    args = parser.parse_args()

    logger.info(f"Starting {args.count} AI clients -> {args.server}")

    tasks = []
    for i in range(1, args.count + 1):
        name = f"{args.prefix}_{i:02d}"
        tasks.append(asyncio.create_task(run_one(args.server, name, args.reconnect_delay_ms)))
        # Stagger connections slightly
        await asyncio.sleep(0.1)

    logger.info(f"All {args.count} clients launched")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
