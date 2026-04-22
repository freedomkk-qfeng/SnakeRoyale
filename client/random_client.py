"""
SnakeRoyale — random-move client built on the reusable client SDK.

Usage:
    python random_client.py --server http://localhost:15000 --name "my_snake"
"""

import asyncio
import logging

import sdk
from algorithms import RandomAlgorithm


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


async def main():
    await sdk.run_cli_entrypoint(RandomAlgorithm(), description="Snake Online Random AI Client")


if __name__ == "__main__":
    asyncio.run(main())