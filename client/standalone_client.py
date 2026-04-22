"""
SnakeRoyale — legacy standalone BFS client.

This file is kept so /download/client.py continues to provide a single runnable
Python sample for existing classroom workflows.
"""

import argparse
import asyncio
import json
import logging
import os
import random
from collections import deque

import aiohttp


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def read_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


DIRECTIONS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


class SnakeAI:
    def __init__(self):
        self.field_width = 100
        self.field_height = 100
        self.my_id = None

    def decide(self, state: dict) -> str:
        my_snake = None
        for snake in state.get("snakes", []):
            if snake["id"] == self.my_id:
                my_snake = snake
                break

        if not my_snake or not my_snake["body"]:
            return "right"

        head = tuple(my_snake["body"][0])
        foods = {tuple(food) for food in state.get("foods", [])}
        obstacles = set()
        for snake in state.get("snakes", []):
            for pos in snake.get("body", []):
                obstacles.add(tuple(pos))
        obstacles.discard(head)

        safe_moves = {}
        for direction, (dx, dy) in DIRECTIONS.items():
            nx, ny = head[0] + dx, head[1] + dy
            if 0 <= nx < self.field_width and 0 <= ny < self.field_height and (nx, ny) not in obstacles:
                safe_moves[direction] = (nx, ny)

        if not safe_moves:
            return my_snake.get("direction", "right")

        if foods:
            best_direction = self._bfs_to_food(head, foods, obstacles, safe_moves)
            if best_direction:
                return best_direction

        best_direction = None
        best_space = -1
        for direction, position in safe_moves.items():
            reachable = self._count_reachable(position, obstacles)
            if reachable > best_space:
                best_space = reachable
                best_direction = direction

        return best_direction or my_snake.get("direction", "right")

    def _bfs_to_food(
        self,
        head: tuple[int, int],
        foods: set[tuple[int, int]],
        obstacles: set[tuple[int, int]],
        safe_moves: dict[str, tuple[int, int]],
    ) -> str | None:
        visited = {head}
        queue = deque()
        for direction, position in safe_moves.items():
            if position in foods:
                return direction
            queue.append((position, direction))
            visited.add(position)

        steps = 0
        while queue and steps < 500:
            position, first_direction = queue.popleft()
            steps += 1
            for dx, dy in DIRECTIONS.values():
                nx, ny = position[0] + dx, position[1] + dy
                next_position = (nx, ny)
                if next_position in visited:
                    continue
                if not (0 <= nx < self.field_width and 0 <= ny < self.field_height):
                    continue
                if next_position in obstacles:
                    continue
                if next_position in foods:
                    return first_direction
                visited.add(next_position)
                queue.append((next_position, first_direction))

        return None

    def _count_reachable(self, start: tuple[int, int], obstacles: set[tuple[int, int]], limit: int = 50) -> int:
        visited = {start}
        queue = deque([start])
        count = 0
        while queue and count < limit:
            position = queue.popleft()
            count += 1
            for dx, dy in DIRECTIONS.values():
                nx, ny = position[0] + dx, position[1] + dy
                next_position = (nx, ny)
                if next_position in visited:
                    continue
                if not (0 <= nx < self.field_width and 0 <= ny < self.field_height):
                    continue
                if next_position in obstacles:
                    continue
                visited.add(next_position)
                queue.append(next_position)
        return count


async def register(server_url: str, name: str) -> str:
    async with aiohttp.ClientSession() as session:
        candidate_name = name
        for attempt in range(8):
            async with session.post(f"{server_url}/register", json={"name": candidate_name}) as response:
                payload = await response.json()

            if response.status == 200:
                logger.info("Registered as: %s (key=%s...)", payload["name"], payload["key"][:4])
                return payload["key"]

            if response.status != 409:
                raise RuntimeError(f"Registration failed: {payload}")

            candidate_name = f"{name}_{random.randint(100, 999)}"
            logger.warning("Name conflict for %s, retrying as %s (attempt %s/8)", name, candidate_name, attempt + 2)

    raise RuntimeError(f"Registration failed after repeated name conflicts for base name {name!r}")


async def play(server_url: str, key: str):
    ai = SnakeAI()
    ws_url = f"{server_url}/ws?key={key}".replace("http://", "ws://").replace("https://", "wss://")

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(ws_url) as ws:
            logger.info("Connected to game server")
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data["type"] == "welcome":
                        ai.field_width = data["field"]["width"]
                        ai.field_height = data["field"]["height"]
                        ai.my_id = data["you"]
                    elif data["type"] == "state":
                        ai.my_id = data.get("you", ai.my_id)
                        direction = ai.decide(data)
                        await ws.send_json({"type": "move", "direction": direction, "tick": data.get("tick")})
                    elif data["type"] == "death":
                        logger.info("Died: %s", data["reason"])
                    elif data["type"] == "respawn":
                        logger.info("Respawned!")
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    logger.warning("WebSocket closed")
                    break


async def main():
    parser = argparse.ArgumentParser(description="Snake Online AI Client")
    parser.add_argument("--server", default="http://localhost:15000", help="Server URL")
    parser.add_argument("--name", required=True, help="Player name")
    parser.add_argument(
        "--reconnect-delay-ms",
        type=int,
        default=read_positive_int_env("SNAKE_CLIENT_RECONNECT_DELAY_MS", 3000),
        help="Reconnect delay in milliseconds (default: env SNAKE_CLIENT_RECONNECT_DELAY_MS or 3000)",
    )
    args = parser.parse_args()

    key = await register(args.server, args.name)
    reconnect_delay_seconds = max(args.reconnect_delay_ms, 1) / 1000.0
    attempt = 0
    while True:
        attempt += 1
        try:
            await play(args.server, key)
        except Exception as exc:
            logger.warning(
                "Disconnected: %s, reconnecting in %.2fs... (attempt %s)",
                exc,
                reconnect_delay_seconds,
                attempt,
            )
            await asyncio.sleep(reconnect_delay_seconds)


if __name__ == "__main__":
    asyncio.run(main())