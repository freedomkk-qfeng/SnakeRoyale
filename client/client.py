"""
贪吃蛇 Online — 示例 AI 客户端

策略：BFS 寻找最近的食物，同时避开墙壁和所有蛇身。
如果没有安全路径到食物，则选择一个安全的方向前进。

用法:
    python client.py --server http://localhost:15000 --name "my_snake"
"""

import argparse
import asyncio
import json
import logging
import sys
from collections import deque

import aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

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
        self.my_id = None  # public_id from server

    def decide(self, state: dict) -> str:
        """Given game state, return the best direction."""
        my_snake = None
        for snake in state.get("snakes", []):
            if snake["id"] == self.my_id:
                my_snake = snake
                break

        if not my_snake or not my_snake["body"]:
            return "right"

        head = tuple(my_snake["body"][0])
        foods = [tuple(f) for f in state.get("foods", [])]

        # Build obstacle set (all snake bodies except our tail, which might move)
        obstacles = set()
        for snake in state["snakes"]:
            body = [tuple(b) for b in snake["body"]]
            # Include all body parts as obstacles
            for pos in body:
                obstacles.add(pos)

        # Remove our own head from obstacles
        obstacles.discard(head)

        # Find safe moves
        safe_moves = {}
        for direction, (dx, dy) in DIRECTIONS.items():
            nx, ny = head[0] + dx, head[1] + dy
            if 0 <= nx < self.field_width and 0 <= ny < self.field_height:
                if (nx, ny) not in obstacles:
                    safe_moves[direction] = (nx, ny)

        if not safe_moves:
            # No safe move, just go current direction or any direction
            return my_snake.get("direction", "right")

        # BFS to find nearest food
        if foods:
            food_set = set(foods)
            best_dir = self._bfs_to_food(head, food_set, obstacles, safe_moves)
            if best_dir:
                return best_dir

        # No path to food — pick direction with most open space
        best_dir = None
        best_space = -1
        for direction, pos in safe_moves.items():
            space = self._count_reachable(pos, obstacles)
            if space > best_space:
                best_space = space
                best_dir = direction

        return best_dir or my_snake.get("direction", "right")

    def _bfs_to_food(self, head, food_set, obstacles, safe_moves):
        """BFS from head to find the nearest food. Returns the first direction to take."""
        visited = {head}
        # Queue: (position, first_direction)
        queue = deque()
        for direction, pos in safe_moves.items():
            if pos in food_set:
                return direction
            queue.append((pos, direction))
            visited.add(pos)

        max_search = 500  # Limit search to avoid slow ticks
        steps = 0
        while queue and steps < max_search:
            pos, first_dir = queue.popleft()
            steps += 1
            for dx, dy in DIRECTIONS.values():
                nx, ny = pos[0] + dx, pos[1] + dy
                npos = (nx, ny)
                if npos in visited:
                    continue
                if not (0 <= nx < self.field_width and 0 <= ny < self.field_height):
                    continue
                if npos in obstacles:
                    continue
                if npos in food_set:
                    return first_dir
                visited.add(npos)
                queue.append((npos, first_dir))

        return None

    def _count_reachable(self, start, obstacles, limit=50):
        """Count reachable cells from start (flood fill), up to limit."""
        visited = {start}
        queue = deque([start])
        count = 0
        while queue and count < limit:
            pos = queue.popleft()
            count += 1
            for dx, dy in DIRECTIONS.values():
                nx, ny = pos[0] + dx, pos[1] + dy
                npos = (nx, ny)
                if npos in visited:
                    continue
                if not (0 <= nx < self.field_width and 0 <= ny < self.field_height):
                    continue
                if npos in obstacles:
                    continue
                visited.add(npos)
                queue.append(npos)
        return count


async def register(server_url: str, name: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{server_url}/register", json={"name": name}) as resp:
            if resp.status == 409:
                # Name taken, try with random suffix
                import random
                name = f"{name}_{random.randint(100, 999)}"
                async with session.post(f"{server_url}/register", json={"name": name}) as resp2:
                    data = await resp2.json()
                    if resp2.status != 200:
                        raise RuntimeError(f"Registration failed: {data}")
                    logger.info(f"Registered as: {data['name']} (key={data['key'][:4]}...)")
                    return data["key"]
            data = await resp.json()
            if resp.status != 200:
                raise RuntimeError(f"Registration failed: {data}")
            logger.info(f"Registered as: {data['name']} (key={data['key'][:4]}...)")
            return data["key"]


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
                        logger.info(f"Welcome! Field: {ai.field_width}x{ai.field_height}")

                    elif data["type"] == "state":
                        ai.my_id = data.get("you", ai.my_id)
                        direction = ai.decide(data)
                        await ws.send_json({"type": "move", "direction": direction})

                    elif data["type"] == "death":
                        logger.info(f"Died: {data['reason']}")

                    elif data["type"] == "respawn":
                        logger.info("Respawned!")

                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    logger.warning("WebSocket closed")
                    break


async def main():
    parser = argparse.ArgumentParser(description="Snake Online AI Client")
    parser.add_argument("--server", default="http://localhost:15000", help="Server URL")
    parser.add_argument("--name", required=True, help="Player name")
    args = parser.parse_args()

    key = await register(args.server, args.name)

    for attempt in range(100):
        try:
            await play(args.server, key)
        except Exception as e:
            logger.warning(f"Disconnected: {e}, reconnecting in 3s... (attempt {attempt + 1})")
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
