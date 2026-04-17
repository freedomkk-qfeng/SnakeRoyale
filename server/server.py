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


@dataclass
class PlayerConnection:
    key: str
    name: str
    ws: web.WebSocketResponse
    mailbox: OutboundMailbox
    sender_task: asyncio.Task | None = None


@dataclass
class SpectatorConnection:
    ws: web.WebSocketResponse
    mailbox: OutboundMailbox
    sender_task: asyncio.Task | None = None

# In-memory storage
registered_players: dict[str, str] = {}  # key -> name
connected_clients: dict[str, PlayerConnection] = {}
spectators: list[SpectatorConnection] = []
disconnected_players: dict[str, float] = {}
connection_state_lock = asyncio.Lock()

game = Game()


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

            if mailbox.latest_batch is None and not mailbox.closed:
                mailbox.event.clear()
            return batch


async def send_batch(ws: web.WebSocketResponse, batch: list[OutboundMessage]):
    for message in batch:
        if message.kind == "json":
            await send_json_with_timeout(ws, message.payload)
        else:
            await send_text_with_timeout(ws, message.payload)


async def disconnect_player(key: str, ws: web.WebSocketResponse, reason: str):
    mailbox = None
    async with connection_state_lock:
        connection = connected_clients.get(key)
        if connection is not None and connection.ws is ws:
            connected_clients.pop(key, None)
            disconnected_players.pop(key, None)
            if key in game.snakes:
                if DISCONNECT_GRACE_SECONDS > 0:
                    disconnected_players[key] = time.monotonic() + DISCONNECT_GRACE_SECONDS
                    logger.info("Player disconnected: %s, grace %.2fs (%s)", connection.name, DISCONNECT_GRACE_SECONDS, reason)
                else:
                    game.remove_snake(key)
                    logger.info("Player disconnected: %s, removed immediately (%s)", connection.name, reason)
            mailbox = connection.mailbox

    if mailbox is not None:
        await close_mailbox(mailbox)

    if not ws.closed:
        with contextlib.suppress(Exception):
            await ws.close()


async def disconnect_spectator(connection: SpectatorConnection, reason: str):
    for index, existing in enumerate(list(spectators)):
        if existing is connection:
            spectators.pop(index)
            break
    await close_mailbox(connection.mailbox)
    if not connection.ws.closed:
        with contextlib.suppress(Exception):
            await connection.ws.close()
    logger.info("Spectator disconnected (total: %s, %s)", len(spectators), reason)


async def ensure_player_snake(key: str, name: str) -> tuple[int | None, bool]:
    async with connection_state_lock:
        disconnected_players.pop(key, None)
        snake = game.snakes.get(key)
        resumed = snake is not None
        if snake is None:
            snake = game.spawn_snake(key, name)
        else:
            snake.name = name
            if not snake.alive:
                snake = game.respawn_snake(key)
        return game.get_public_id(key), resumed


async def expire_disconnected_players():
    if not disconnected_players:
        return
    now = time.monotonic()
    expired: list[tuple[str, str]] = []
    async with connection_state_lock:
        for key in list(disconnected_players):
            deadline = disconnected_players.get(key)
            if deadline is None or deadline > now:
                continue
            disconnected_players.pop(key, None)
            if key in connected_clients:
                continue
            expired.append((key, registered_players.get(key, key[:4])))
            game.remove_snake(key)
    for _, name in expired:
        logger.info("Disconnected grace expired for %s", name)


async def player_sender(connection: PlayerConnection):
    try:
        while True:
            batch = await pop_next_batch(connection.mailbox)
            if batch is None:
                return
            await send_batch(connection.ws, batch)
    except Exception as exc:
        logger.warning("Output stream failed for %s: %s", connection.name, exc)
    finally:
        await disconnect_player(connection.key, connection.ws, "sender task ended")


async def spectator_sender(connection: SpectatorConnection):
    try:
        while True:
            batch = await pop_next_batch(connection.mailbox)
            if batch is None:
                return
            await send_batch(connection.ws, batch)
    except Exception as exc:
        logger.warning("Spectator output stream failed: %s", exc)
    finally:
        await disconnect_spectator(connection, "sender task ended")


async def handle_register(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)

    name = data.get("name", "").strip()
    if not name:
        return web.json_response({"error": "name is required"}, status=400)
    if len(name) > 20:
        return web.json_response({"error": "name too long (max 20 chars)"}, status=400)

    # Check duplicate name
    for existing_name in registered_players.values():
        if existing_name == name:
            return web.json_response({"error": "name already taken"}, status=409)

    key = uuid.uuid4().hex[:16]
    registered_players[key] = name
    logger.info(f"Player registered: {name} (key={key[:4]}...)")
    return web.json_response({"key": key, "name": name})


async def handle_ws(request: web.Request):
    key = request.query.get("key", "")
    if key not in registered_players:
        return web.Response(text="invalid key", status=401)

    if key in connected_clients:
        return web.Response(text="already connected", status=409)

    name = registered_players[key]
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    mailbox = OutboundMailbox()
    connection = PlayerConnection(key=key, name=name, ws=ws, mailbox=mailbox)
    async with connection_state_lock:
        if key in connected_clients:
            await ws.close()
            return ws
        connected_clients[key] = connection

    public_id, resumed = await ensure_player_snake(key, name)
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
        await disconnect_player(key, ws, "welcome failed")
        return ws

    connection.sender_task = asyncio.create_task(player_sender(connection))

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                if data.get("type") == "move":
                    direction = data.get("direction", "")
                    game.set_direction(key, direction)
            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f"WS error for {name}: {ws.exception()}")
    finally:
        await disconnect_player(key, ws, "ws loop ended")

    return ws


async def handle_spectate(request: web.Request):
    """WebSocket endpoint for dashboard spectators (no auth needed)."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    mailbox = OutboundMailbox()
    connection = SpectatorConnection(ws=ws, mailbox=mailbox)
    spectators.append(connection)
    connection.sender_task = asyncio.create_task(spectator_sender(connection))
    logger.info(f"Spectator connected (total: {len(spectators)})")
    try:
        async for msg in ws:
            pass  # Spectators don't send anything meaningful
    finally:
        await disconnect_spectator(connection, "spectate ws loop ended")
    return ws


async def game_loop(app: web.Application):
    logger.info(f"Game loop started (tick rate: {TICK_RATE}/s)")
    tick_interval = 1.0 / TICK_RATE

    while True:
        t0 = time.monotonic()
        await expire_disconnected_players()

        # Always advance game tick (even with 0 players, spectators need state)
        deaths = game.tick()
        state = game.get_state()

        for key in deaths:
            if key in game.snakes:
                game.respawn_snake(key)

        # Fan out state into independent per-client sender tasks.
        for key, connection in list(connected_clients.items()):
            if connection.ws.closed:
                await disconnect_player(key, connection.ws, "socket already closed")
                continue
            batch = [OutboundMessage("json", {**state, "you": game.get_public_id(key)})]
            if key in deaths:
                batch.append(OutboundMessage("json", {
                    "type": "death",
                    "reason": deaths[key],
                }))
                batch.append(OutboundMessage("json", {"type": "respawn"}))
            await push_state_batch(connection.mailbox, batch)

        # Broadcast to spectators (dashboard)
        if spectators:
            state_json = json.dumps(state)
            for connection in list(spectators):
                if connection.ws.closed:
                    await disconnect_spectator(connection, "socket already closed")
                    continue
                await push_state_batch(connection.mailbox, [OutboundMessage("text", state_json)])

        elapsed = time.monotonic() - t0
        sleep_time = max(0, tick_interval - elapsed)
        await asyncio.sleep(sleep_time)


async def start_game_loop(app: web.Application):
    app[GAME_TASK_KEY] = asyncio.create_task(game_loop(app))


async def stop_game_loop(app: web.Application):
    app[GAME_TASK_KEY].cancel()
    try:
        await app[GAME_TASK_KEY]
    except asyncio.CancelledError:
        pass
    for connection in list(connected_clients.values()):
        await disconnect_player(connection.key, connection.ws, "server shutdown")
    for connection in list(spectators):
        await disconnect_spectator(connection, "server shutdown")


async def handle_status(request: web.Request):
    alive = [s for s in game.snakes.values() if s.alive]
    return web.json_response({
        "version": PROJECT_VERSION,
        "tick": game.tick_count,
        "tick_rate": TICK_RATE,
        "send_timeout_ms": SEND_TIMEOUT_MS,
        "disconnect_grace_ms": DISCONNECT_GRACE_MS,
        "players_registered": len(registered_players),
        "players_connected": len(connected_clients),
        "players_grace_disconnected": len(disconnected_players),
        "snakes_alive": len(alive),
        "leaderboard": sorted(
            [{"name": s.name, "score": s.score, "length": len(s.body)} for s in alive],
            key=lambda x: x["score"],
            reverse=True,
        )[:20],
        "performance": game.get_performance_stats()[:20],
    })


async def handle_runtime_config(request: web.Request):
    return web.json_response({
        "version": PROJECT_VERSION,
        "tick_rate": TICK_RATE,
        "send_timeout_ms": SEND_TIMEOUT_MS,
        "disconnect_grace_ms": DISCONNECT_GRACE_MS,
        "spectator_reconnect_ms": SPECTATOR_RECONNECT_MS,
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
    with open(client_py, "r", encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="text/plain")


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
    logger.info(f"Starting Snake Online server on {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT, print=None)
