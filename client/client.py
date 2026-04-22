"""
SnakeRoyale — BFS client built on the reusable client SDK.

Usage:
    python client.py --server http://localhost:15000 --name "my_snake"
"""

import asyncio
import logging
import random

import sdk
from algorithms import BFSAlgorithm


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

read_positive_int_env = sdk.read_positive_int_env
DIRECTIONS = sdk.DIRECTIONS


async def register(server_url: str, name: str) -> str:
    return await sdk.register(server_url, name, randint=random.randint)


async def play(server_url: str, key: str):
    await sdk.play(server_url, key, algorithm=BFSAlgorithm())


async def main():
    await sdk.run_cli_entrypoint(BFSAlgorithm(), description="Snake Online BFS AI Client")


if __name__ == "__main__":
    asyncio.run(main())
