import asyncio
import json
import os
import uuid
import logging
import time

from aiohttp import web

from game import Game, TICK_RATE
import game as game_module

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

HOST = "0.0.0.0"
PORT = 15000

# In-memory storage
registered_players: dict[str, str] = {}  # key -> name
connected_clients: dict[str, web.WebSocketResponse] = {}  # key -> ws
spectators: list[web.WebSocketResponse] = []  # dashboard spectators

game = Game()


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

    connected_clients[key] = ws
    snake = game.spawn_snake(key, name)
    logger.info(f"Player connected: {name}")

    # Send initial welcome
    await ws.send_json({
        "type": "welcome",
        "you": game.get_public_id(key),
        "name": name,
        "field": {"width": game_module.FIELD_WIDTH, "height": game_module.FIELD_HEIGHT},
        "tick_rate": TICK_RATE,
    })

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
        connected_clients.pop(key, None)
        game.remove_snake(key)
        logger.info(f"Player disconnected: {name}")

    return ws


async def handle_spectate(request: web.Request):
    """WebSocket endpoint for dashboard spectators (no auth needed)."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    spectators.append(ws)
    logger.info(f"Spectator connected (total: {len(spectators)})")
    try:
        async for msg in ws:
            pass  # Spectators don't send anything meaningful
    finally:
        try:
            spectators.remove(ws)
        except ValueError:
            pass
        logger.info(f"Spectator disconnected (total: {len(spectators)})")
    return ws


async def game_loop(app: web.Application):
    logger.info(f"Game loop started (tick rate: {TICK_RATE}/s)")
    tick_interval = 1.0 / TICK_RATE

    while True:
        t0 = time.monotonic()

        # Always advance game tick (even with 0 players, spectators need state)
        deaths = game.tick() if connected_clients else {}
        state = game.get_state()

        # Broadcast state to all connected clients
        disconnected = []
        for key, ws in list(connected_clients.items()):
            if ws.closed:
                disconnected.append(key)
                continue
            try:
                # Send personalized state with public_id as "you" field
                public_id = game.get_public_id(key)
                player_state = {**state, "you": public_id}
                await ws.send_json(player_state)

                # Send death notification
                if key in deaths:
                    await ws.send_json({
                        "type": "death",
                        "reason": deaths[key],
                    })
            except Exception as e:
                logger.warning(f"Error sending to client: {e}")
                disconnected.append(key)

        for key in disconnected:
            connected_clients.pop(key, None)
            game.remove_snake(key)

        # Respawn dead snakes AFTER broadcast is complete
        for key in deaths:
            if key in connected_clients:
                game.respawn_snake(key)
                try:
                    await connected_clients[key].send_json({"type": "respawn"})
                except Exception:
                    pass

        # Broadcast to spectators (dashboard)
        if spectators:
            state_json = json.dumps(state)
            dead_spectators = []
            for ws in spectators:
                if ws.closed:
                    dead_spectators.append(ws)
                    continue
                try:
                    await ws.send_str(state_json)
                except Exception:
                    dead_spectators.append(ws)
            for ws in dead_spectators:
                try:
                    spectators.remove(ws)
                except ValueError:
                    pass

        elapsed = time.monotonic() - t0
        sleep_time = max(0, tick_interval - elapsed)
        await asyncio.sleep(sleep_time)


async def start_game_loop(app: web.Application):
    app["game_task"] = asyncio.create_task(game_loop(app))


async def stop_game_loop(app: web.Application):
    app["game_task"].cancel()
    try:
        await app["game_task"]
    except asyncio.CancelledError:
        pass


async def handle_status(request: web.Request):
    alive = [s for s in game.snakes.values() if s.alive]
    return web.json_response({
        "tick": game.tick_count,
        "players_registered": len(registered_players),
        "players_connected": len(connected_clients),
        "snakes_alive": len(alive),
        "leaderboard": sorted(
            [{"name": s.name, "score": s.score, "length": len(s.body)} for s in alive],
            key=lambda x: x["score"],
            reverse=True,
        )[:20],
    })


def create_app():
    app = web.Application()
    app.router.add_post("/register", handle_register)
    app.router.add_get("/ws", handle_ws)
    app.router.add_get("/spectate", handle_spectate)
    app.router.add_get("/status", handle_status)
    # Serve dashboard static files
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    app.router.add_get("/", lambda r: web.FileResponse(os.path.join(static_dir, "index.html")))
    app.router.add_get("/docs", lambda r: web.FileResponse(os.path.join(static_dir, "docs.html")))
    client_py = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "client", "client.py"))
    app.router.add_get("/download/client.py", lambda r: web.FileResponse(
        client_py,
        headers={"Content-Disposition": "attachment; filename=client.py"},
    ))
    async def handle_client_source(request):
        with open(client_py, "r", encoding="utf-8") as f:
            return web.Response(text=f.read(), content_type="text/plain")
    app.router.add_get("/api/client-source", handle_client_source)
    docs_dir = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs"))
    app.router.add_get("/api/docs/zh", lambda r: web.FileResponse(
        os.path.join(docs_dir, "API.md"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
    ))
    app.router.add_get("/api/docs/en", lambda r: web.FileResponse(
        os.path.join(docs_dir, "API_en.md"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
    ))
    app.router.add_static("/static/", static_dir)
    app.on_startup.append(start_game_loop)
    app.on_cleanup.append(stop_game_loop)
    return app


if __name__ == "__main__":
    app = create_app()
    logger.info(f"Starting Snake Online server on {HOST}:{PORT}")
    web.run_app(app, host=HOST, port=PORT, print=None)
