import asyncio
import contextlib
import json
from dataclasses import dataclass, field
import os
import uuid
import logging
import time

from aiohttp import web

from config import (
    DISCONNECT_GRACE_MS,
    DISCONNECT_GRACE_SECONDS,
    MAX_REGISTERED_PLAYERS,
    MAX_SPECTATORS,
    PROJECT_VERSION,
    SEND_TIMEOUT_MS,
    SEND_TIMEOUT_SECONDS,
    SPECTATOR_RECONNECT_MS,
    TICK_RATE,
)
from game import Game
import game as game_module

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

HOST = "0.0.0.0"
PORT = 15000
GAME_TASK_KEY = web.AppKey("game_task", asyncio.Task)
STATE_KEY = web.AppKey("runtime_state", "ServerRuntime")
STATIC_DIR_KEY = web.AppKey("static_dir", str)
CLIENT_PY_KEY = web.AppKey("client_py", str)
DOCS_DIR_KEY = web.AppKey("docs_dir", str)


@dataclass
class OutboundMessage:
    kind: str
    payload: dict | str


@dataclass
class OutboundMailbox:
    latest_batch: list[OutboundMessage] | None = None
    event: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    closed: bool = False


@dataclass(eq=False)
class PlayerConnection:
    key: str
    name: str
    ws: web.WebSocketResponse
    mailbox: OutboundMailbox
    sender_task: asyncio.Task | None = None


@dataclass(eq=False)
class SpectatorConnection:
    ws: web.WebSocketResponse
    mailbox: OutboundMailbox
    sender_task: asyncio.Task | None = None


@dataclass
class ServerRuntime:
    game: Game = field(default_factory=Game)
    registered_players: dict[str, str] = field(default_factory=dict)
    player_keys_by_name: dict[str, str] = field(default_factory=dict)
    connected_clients: dict[str, PlayerConnection] = field(default_factory=dict)
    spectators: set[SpectatorConnection] = field(default_factory=set)
    disconnected_players: dict[str, float] = field(default_factory=dict)
    connection_state_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


async def send_json_with_timeout(ws: web.WebSocketResponse, payload: dict):
    await asyncio.wait_for(ws.send_json(payload), timeout=SEND_TIMEOUT_SECONDS)


async def send_text_with_timeout(ws: web.WebSocketResponse, payload: str):
    await asyncio.wait_for(ws.send_str(payload), timeout=SEND_TIMEOUT_SECONDS)


async def close_mailbox(mailbox: OutboundMailbox):
    async with mailbox.lock:
        mailbox.closed = True
        mailbox.latest_batch = None
        mailbox.event.set()


async def push_state_batch(mailbox: OutboundMailbox, batch: list[OutboundMessage]) -> bool:
    async with mailbox.lock:
        if mailbox.closed:
            return False
        mailbox.latest_batch = batch
        mailbox.event.set()
        return True


async def pop_next_batch(mailbox: OutboundMailbox) -> list[OutboundMessage] | None:
    while True:
        await mailbox.event.wait()
        async with mailbox.lock:
            if mailbox.latest_batch is not None:
                batch = mailbox.latest_batch
                mailbox.latest_batch = None
            elif mailbox.closed:
                mailbox.event.clear()
                return None
            else:
                mailbox.event.clear()
                continue

            # Clear the event only after the current batch is claimed so future pushes re-arm it.
            if mailbox.latest_batch is None and not mailbox.closed:
                mailbox.event.clear()
            return batch


async def send_batch(ws: web.WebSocketResponse, batch: list[OutboundMessage]):
    for message in batch:
        if message.kind == "json":
            await send_json_with_timeout(ws, message.payload)
        else:
            await send_text_with_timeout(ws, message.payload)


async def disconnect_player(state: ServerRuntime, key: str, ws: web.WebSocketResponse, reason: str):
    mailbox = None
    async with state.connection_state_lock:
        connection = state.connected_clients.get(key)
        if connection is not None and connection.ws is ws:
            state.connected_clients.pop(key, None)
            state.disconnected_players.pop(key, None)
            if key in state.game.snakes:
                if DISCONNECT_GRACE_SECONDS > 0:
                    state.disconnected_players[key] = time.monotonic() + DISCONNECT_GRACE_SECONDS
                    logger.info("Player disconnected: %s, grace %.2fs (%s)", connection.name, DISCONNECT_GRACE_SECONDS, reason)
                else:
                    state.game.remove_snake(key)
                    logger.info("Player disconnected: %s, removed immediately (%s)", connection.name, reason)
            mailbox = connection.mailbox

    if mailbox is not None:
        await close_mailbox(mailbox)

    if not ws.closed:
        with contextlib.suppress(Exception):
            await ws.close()


async def disconnect_spectator(state: ServerRuntime, connection: SpectatorConnection, reason: str):
    async with state.connection_state_lock:
        state.spectators.discard(connection)
    await close_mailbox(connection.mailbox)
    if not connection.ws.closed:
        with contextlib.suppress(Exception):
            await connection.ws.close()
    logger.info("Spectator disconnected (total: %s, %s)", len(state.spectators), reason)


async def ensure_player_snake(state: ServerRuntime, key: str, name: str) -> tuple[int | None, bool]:
    async with state.connection_state_lock:
        state.disconnected_players.pop(key, None)
        snake = state.game.snakes.get(key)
        resumed = snake is not None
        if snake is None:
            snake = state.game.spawn_snake(key, name)
        else:
            snake.name = name
            if not snake.alive:
                snake = state.game.respawn_snake(key)
        return state.game.get_public_id(key), resumed


async def expire_disconnected_players(state: ServerRuntime):
    if not state.disconnected_players:
        return
    now = time.monotonic()
    expired: list[tuple[str, str]] = []
    async with state.connection_state_lock:
        for key in list(state.disconnected_players):
            deadline = state.disconnected_players.get(key)
            if deadline is None or deadline > now:
                continue
            state.disconnected_players.pop(key, None)
            if key in state.connected_clients:
                continue
            expired.append((key, state.registered_players.get(key, key[:4])))
            state.game.remove_snake(key)
    for _, name in expired:
        logger.info("Disconnected grace expired for %s", name)


async def player_sender(state: ServerRuntime, connection: PlayerConnection):
    try:
        while True:
            batch = await pop_next_batch(connection.mailbox)
            if batch is None:
                return
            await send_batch(connection.ws, batch)
    except Exception as exc:
        logger.warning("Output stream failed for %s: %s", connection.name, exc)
    finally:
        await disconnect_player(state, connection.key, connection.ws, "sender task ended")


async def spectator_sender(state: ServerRuntime, connection: SpectatorConnection):
    try:
        while True:
            batch = await pop_next_batch(connection.mailbox)
            if batch is None:
                return
            await send_batch(connection.ws, batch)
    except Exception as exc:
        logger.warning("Spectator output stream failed: %s", exc)
    finally:
        await disconnect_spectator(state, connection, "sender task ended")


async def handle_register(request: web.Request):
    state = request.app[STATE_KEY]
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    name = data.get("name", "").strip()
    if not name:
        return web.json_response({"error": "name is required"}, status=400)
    if len(name) > 20:
        return web.json_response({"error": "name too long (max 20 chars)"}, status=400)

    async with state.connection_state_lock:
        if name in state.player_keys_by_name:
            return web.json_response({"error": "name already taken"}, status=409)
        if MAX_REGISTERED_PLAYERS > 0 and len(state.registered_players) >= MAX_REGISTERED_PLAYERS:
            return web.json_response({"error": "player limit reached"}, status=503)

        key = uuid.uuid4().hex[:16]
        state.registered_players[key] = name
        state.player_keys_by_name[name] = key

    logger.info("Player registered: %s (key=%s...)", name, key[:4])
    return web.json_response({"key": key, "name": name})


async def handle_ws(request: web.Request):
    state = request.app[STATE_KEY]
    key = request.query.get("key", "")
    if key not in state.registered_players:
        return web.Response(text="invalid key", status=401)

    if key in state.connected_clients:
        return web.Response(text="already connected", status=409)

    name = state.registered_players[key]
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    mailbox = OutboundMailbox()
    connection = PlayerConnection(key=key, name=name, ws=ws, mailbox=mailbox)
    async with state.connection_state_lock:
        if key in state.connected_clients:
            await ws.close()
            return ws
        state.connected_clients[key] = connection

    public_id, resumed = await ensure_player_snake(state, key, name)
    logger.info("Player connected: %s (%s)", name, "resume" if resumed else "spawn")

    # Send initial welcome
    try:
        await send_json_with_timeout(ws, {
            "type": "welcome",
            "you": public_id,
            "name": name,
            "field": {"width": game_module.FIELD_WIDTH, "height": game_module.FIELD_HEIGHT},
            "tick_rate": TICK_RATE,
            "send_timeout_ms": SEND_TIMEOUT_MS,
            "disconnect_grace_ms": DISCONNECT_GRACE_MS,
            "resumed": resumed,
        })
    except Exception:
        await disconnect_player(state, key, ws, "welcome failed")
        return ws

    connection.sender_task = asyncio.create_task(player_sender(state, connection))

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                if data.get("type") == "move":
                    direction = data.get("direction", "")
                    state.game.set_direction(key, direction)
            elif msg.type == web.WSMsgType.ERROR:
                logger.error("WS error for %s: %s", name, ws.exception())
    finally:
        await disconnect_player(state, key, ws, "ws loop ended")

    return ws


async def handle_spectate(request: web.Request):
    """WebSocket endpoint for dashboard spectators (no auth needed)."""
    state = request.app[STATE_KEY]

    async with state.connection_state_lock:
        if MAX_SPECTATORS > 0 and len(state.spectators) >= MAX_SPECTATORS:
            return web.Response(text="spectator limit reached", status=503)

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    mailbox = OutboundMailbox()
    connection = SpectatorConnection(ws=ws, mailbox=mailbox)
    async with state.connection_state_lock:
        if MAX_SPECTATORS > 0 and len(state.spectators) >= MAX_SPECTATORS:
            await ws.close()
            return ws
        state.spectators.add(connection)
    connection.sender_task = asyncio.create_task(spectator_sender(state, connection))
    logger.info("Spectator connected (total: %s)", len(state.spectators))
    try:
        async for msg in ws:
            pass  # Spectators don't send anything meaningful
    finally:
        await disconnect_spectator(state, connection, "spectate ws loop ended")
    return ws


async def game_loop(app: web.Application):
    state = app[STATE_KEY]
    logger.info("Game loop started (tick rate: %s/s)", TICK_RATE)
    tick_interval = 1.0 / TICK_RATE

    while True:
        t0 = time.monotonic()
        try:
            await expire_disconnected_players(state)

            # Always advance game tick (even with 0 players, spectators need state)
            deaths = state.game.tick()
            game_state = state.game.get_state()

            for key in deaths:
                if key in state.game.snakes:
                    state.game.respawn_snake(key)

            # Fan out state into independent per-client sender tasks.
            for key, connection in list(state.connected_clients.items()):
                if connection.ws.closed:
                    await disconnect_player(state, key, connection.ws, "socket already closed")
                    continue
                batch = [OutboundMessage("json", {**game_state, "you": state.game.get_public_id(key)})]
                if key in deaths:
                    batch.append(OutboundMessage("json", {
                        "type": "death",
                        "reason": deaths[key],
                    }))
                    batch.append(OutboundMessage("json", {"type": "respawn"}))
                await push_state_batch(connection.mailbox, batch)

            # Broadcast to spectators (dashboard)
            if state.spectators:
                state_json = json.dumps(game_state)
                for connection in list(state.spectators):
                    if connection.ws.closed:
                        await disconnect_spectator(state, connection, "socket already closed")
                        continue
                    await push_state_batch(connection.mailbox, [OutboundMessage("text", state_json)])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Game loop iteration failed")

        elapsed = time.monotonic() - t0
        sleep_time = max(0, tick_interval - elapsed)
        await asyncio.sleep(sleep_time)


async def start_game_loop(app: web.Application):
    app[GAME_TASK_KEY] = asyncio.create_task(game_loop(app))


async def stop_game_loop(app: web.Application):
    state = app[STATE_KEY]
    app[GAME_TASK_KEY].cancel()
    try:
        await app[GAME_TASK_KEY]
    except asyncio.CancelledError:
        pass
    for connection in list(state.connected_clients.values()):
        await disconnect_player(state, connection.key, connection.ws, "server shutdown")
    for connection in list(state.spectators):
        await disconnect_spectator(state, connection, "server shutdown")


async def handle_status(request: web.Request):
    state = request.app[STATE_KEY]
    alive = [s for s in state.game.snakes.values() if s.alive]
    return web.json_response({
        "version": PROJECT_VERSION,
        "tick": state.game.tick_count,
        "tick_rate": TICK_RATE,
        "send_timeout_ms": SEND_TIMEOUT_MS,
        "disconnect_grace_ms": DISCONNECT_GRACE_MS,
        "max_registered_players": MAX_REGISTERED_PLAYERS,
        "max_spectators": MAX_SPECTATORS,
        "players_registered": len(state.registered_players),
        "players_connected": len(state.connected_clients),
        "players_grace_disconnected": len(state.disconnected_players),
        "snakes_alive": len(alive),
        "leaderboard": sorted(
            [{"name": s.name, "score": s.score, "length": len(s.body)} for s in alive],
            key=lambda x: x["score"],
            reverse=True,
        )[:20],
        "performance": state.game.get_performance_stats()[:20],
    })


async def handle_runtime_config(request: web.Request):
    return web.json_response({
        "version": PROJECT_VERSION,
        "tick_rate": TICK_RATE,
        "send_timeout_ms": SEND_TIMEOUT_MS,
        "disconnect_grace_ms": DISCONNECT_GRACE_MS,
        "spectator_reconnect_ms": SPECTATOR_RECONNECT_MS,
        "max_registered_players": MAX_REGISTERED_PLAYERS,
        "max_spectators": MAX_SPECTATORS,
    })


async def handle_index(request: web.Request):
    static_dir = request.app[STATIC_DIR_KEY]
    return web.FileResponse(os.path.join(static_dir, "index.html"))


async def handle_docs_page(request: web.Request):
    static_dir = request.app[STATIC_DIR_KEY]
    return web.FileResponse(os.path.join(static_dir, "docs.html"))


async def handle_download_client(request: web.Request):
    client_py = request.app[CLIENT_PY_KEY]
    return web.FileResponse(
        client_py,
        headers={"Content-Disposition": "attachment; filename=client.py"},
    )


async def handle_client_source(request: web.Request):
    client_py = request.app[CLIENT_PY_KEY]
    return web.FileResponse(
        client_py,
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )


async def handle_docs_zh(request: web.Request):
    docs_dir = request.app[DOCS_DIR_KEY]
    return web.FileResponse(
        os.path.join(docs_dir, "API.md"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )


async def handle_docs_en(request: web.Request):
    docs_dir = request.app[DOCS_DIR_KEY]
    return web.FileResponse(
        os.path.join(docs_dir, "API_en.md"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )


def create_app():
    app = web.Application()
    app[STATE_KEY] = ServerRuntime()
    app.router.add_post("/register", handle_register)
    app.router.add_get("/ws", handle_ws)
    app.router.add_get("/spectate", handle_spectate)
    app.router.add_get("/status", handle_status)
    app.router.add_get("/api/runtime-config", handle_runtime_config)
    # Serve dashboard static files
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    app[STATIC_DIR_KEY] = static_dir
    app.router.add_get("/", handle_index)
    app.router.add_get("/docs", handle_docs_page)
    client_py = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "client", "client.py"))
    app[CLIENT_PY_KEY] = client_py
    app.router.add_get("/download/client.py", handle_download_client)
    app.router.add_get("/api/client-source", handle_client_source)
    docs_dir = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs"))
    app[DOCS_DIR_KEY] = docs_dir
    app.router.add_get("/api/docs/zh", handle_docs_zh)
    app.router.add_get("/api/docs/en", handle_docs_en)
    app.router.add_static("/static/", static_dir)
    app.on_startup.append(start_game_loop)
    app.on_cleanup.append(stop_game_loop)
    return app


if __name__ == "__main__":
    app = create_app()
    logger.info("Starting Snake Online server on %s:%s", HOST, PORT)
    web.run_app(app, host=HOST, port=PORT, print=None)
