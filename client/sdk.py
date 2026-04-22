import argparse
import asyncio
import json
import logging
import os
import random
from dataclasses import dataclass
from typing import Callable

import aiohttp


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


@dataclass
class ClientContext:
    player_name: str | None = None
    field_width: int = 100
    field_height: int = 100
    my_id: str | None = None

    def update_from_welcome(self, payload: dict):
        self.player_name = payload.get("name", self.player_name)
        self.field_width = payload["field"]["width"]
        self.field_height = payload["field"]["height"]
        self.my_id = payload["you"]

    def update_from_state(self, payload: dict):
        self.my_id = payload.get("you", self.my_id)

    def get_my_snake(self, state: dict) -> dict | None:
        if self.my_id is None:
            return None
        for snake in state.get("snakes", []):
            if snake.get("id") == self.my_id:
                return snake
        return None


class BaseSnakeAlgorithm:
    def on_welcome(self, payload: dict, context: ClientContext):
        return None

    def on_death(self, payload: dict, context: ClientContext):
        return None

    def on_respawn(self, payload: dict, context: ClientContext):
        return None

    def decide(self, state: dict, context: ClientContext) -> str:
        raise NotImplementedError


async def register(
    server_url: str,
    name: str,
    max_attempts: int = 8,
    randint: Callable[[int, int], int] | None = None,
) -> str:
    result = await _register_result(server_url, name, max_attempts=max_attempts, randint=randint)
    return result["key"]


async def _register_result(
    server_url: str,
    name: str,
    max_attempts: int = 8,
    randint: Callable[[int, int], int] | None = None,
) -> dict:
    randint = randint or random.randint

    async with aiohttp.ClientSession() as session:
        candidate_name = name
        for attempt in range(max_attempts):
            async with session.post(f"{server_url}/register", json={"name": candidate_name}) as resp:
                data = await resp.json()

            if resp.status == 200:
                logger.info("Registered as: %s (key=%s...)", data["name"], data["key"][:4])
                return data

            if resp.status != 409:
                raise RuntimeError(f"Registration failed: {data}")

            candidate_name = f"{name}_{randint(100, 999)}"
            logger.warning(
                "Name conflict for %s, retrying as %s (attempt %s/%s)",
                name,
                candidate_name,
                attempt + 2,
                max_attempts,
            )

    raise RuntimeError(f"Registration failed after repeated name conflicts for base name {name!r}")


def _default_direction(state: dict, context: ClientContext) -> str:
    my_snake = context.get_my_snake(state)
    if my_snake:
        return my_snake.get("direction", "right")
    return "right"


def _normalize_direction(direction: str, state: dict, context: ClientContext) -> str:
    if direction in DIRECTIONS:
        return direction

    fallback = _default_direction(state, context)
    logger.warning("Algorithm returned invalid direction %r, falling back to %s", direction, fallback)
    return fallback


def _build_ws_url(server_url: str, key: str) -> str:
    return f"{server_url}/ws?key={key}".replace("http://", "ws://").replace("https://", "wss://")


async def play(server_url: str, key: str, algorithm: BaseSnakeAlgorithm, context: ClientContext | None = None):
    context = context or ClientContext()
    ws_url = _build_ws_url(server_url, key)

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(ws_url) as ws:
            logger.info("Connected to game server")

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    msg_type = data.get("type")

                    if msg_type == "welcome":
                        context.update_from_welcome(data)
                        algorithm.on_welcome(data, context)
                        logger.info("Welcome! Field: %sx%s", context.field_width, context.field_height)
                    elif msg_type == "state":
                        context.update_from_state(data)
                        try:
                            direction = algorithm.decide(data, context)
                        except Exception:
                            logger.exception("Algorithm decide() failed, keeping current direction")
                            direction = _default_direction(data, context)
                        await ws.send_json({
                            "type": "move",
                            "direction": _normalize_direction(direction, data, context),
                            "tick": data.get("tick"),
                        })
                    elif msg_type == "death":
                        algorithm.on_death(data, context)
                        logger.info("Died: %s", data["reason"])
                    elif msg_type == "respawn":
                        algorithm.on_respawn(data, context)
                        logger.info("Respawned!")
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    logger.warning("WebSocket closed")
                    break


async def run_forever(server_url: str, name: str, algorithm: BaseSnakeAlgorithm, reconnect_delay_ms: int):
    registration = await _register_result(server_url, name)
    key = registration["key"]
    reconnect_delay_seconds = max(reconnect_delay_ms, 1) / 1000.0
    attempt = 0
    context = ClientContext(player_name=registration.get("name", name))

    while True:
        attempt += 1
        try:
            await play(server_url, key, algorithm=algorithm, context=context)
        except Exception as exc:
            logger.warning(
                "Disconnected: %s, reconnecting in %.2fs... (attempt %s)",
                exc,
                reconnect_delay_seconds,
                attempt,
            )
            await asyncio.sleep(reconnect_delay_seconds)


def build_client_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--server", default="http://localhost:15000", help="Server URL")
    parser.add_argument("--name", required=True, help="Player name")
    parser.add_argument(
        "--reconnect-delay-ms",
        type=int,
        default=read_positive_int_env("SNAKE_CLIENT_RECONNECT_DELAY_MS", 3000),
        help="Reconnect delay in milliseconds (default: env SNAKE_CLIENT_RECONNECT_DELAY_MS or 3000)",
    )
    return parser


async def run_cli_entrypoint(algorithm: BaseSnakeAlgorithm, description: str):
    parser = build_client_parser(description)
    args = parser.parse_args()
    await run_forever(args.server, args.name, algorithm, args.reconnect_delay_ms)