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
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from algorithms import ALGORITHMS, create_algorithm
import sdk


def read_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


async def run_one(server: str, name: str, reconnect_delay_ms: int, algorithm_name: str):
    """Run a single SDK-backed client with reconnection."""
    await sdk.run_forever(server, name, create_algorithm(algorithm_name), reconnect_delay_ms)


async def main():
    parser = argparse.ArgumentParser(description="批量启动贪吃蛇 AI 客户端")
    parser.add_argument("-n", "--count", type=int, default=5, help="客户端数量 (默认: 5)")
    parser.add_argument("--server", default="http://localhost:15000", help="服务器地址")
    parser.add_argument("--prefix", default="Bot", help="名字前缀 (默认: Bot)")
    parser.add_argument(
        "--algorithm",
        default=os.getenv("SNAKE_CLIENT_ALGORITHM", "bfs").strip() or "bfs",
        choices=sorted(ALGORITHMS),
        help="内置算法选择 (默认: bfs，可通过 SNAKE_CLIENT_ALGORITHM 覆盖)",
    )
    parser.add_argument(
        "--reconnect-delay-ms",
        type=int,
        default=read_positive_int_env("SNAKE_CLIENT_RECONNECT_DELAY_MS", 3000),
        help="客户端断线重连间隔（毫秒，默认读取 SNAKE_CLIENT_RECONNECT_DELAY_MS 或 3000）",
    )
    args = parser.parse_args()

    logger.info("Starting %s %s AI clients -> %s", args.count, args.algorithm, args.server)

    tasks = []
    for i in range(1, args.count + 1):
        name = f"{args.prefix}_{i:02d}"
        tasks.append(
            asyncio.create_task(
                run_one(args.server, name, args.reconnect_delay_ms, args.algorithm)
            )
        )
        # Stagger connections slightly
        await asyncio.sleep(0.1)

    logger.info("All %s clients launched", args.count)
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
