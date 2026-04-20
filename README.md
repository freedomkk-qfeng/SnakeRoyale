# 🐍 SnakeRoyale

[中文文档](README_zh.md)

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![AI Coded](https://img.shields.io/badge/AI_Coded-100%25-A855F7?logo=github-copilot&logoColor=white)](https://github.com/features/copilot)

A multiplayer snake battle arena for AI programming education. Deploy the server, code your AI client, and learn pathfinding & game strategy through competition.

![Dashboard](docs/screenshot_en.png)

Current version: `0.3.0`

## Documentation

The project documentation is organized into four fixed parts:

1. [README](README.md) - project overview, quick start, deployment, and testing.
2. [DESIGN](docs/DESIGN_en.md) - architecture, networking model, and design tradeoffs.
3. [API](docs/API_en.md) - client/server protocol and endpoint contract.
4. [CHANGELOG](CHANGELOG.md) - versioned release history.

## Project Structure

```
snake-royale/
├── docker-compose.yml      # Default stack: server + bot
├── docker-compose.full.yml # Full stack: server + bot + toxiproxy + bot_toxic
├── CHANGELOG.md            # Versioned release history
├── config/
│   ├── server.json         # Server runtime defaults
│   └── toxiproxy.json      # Toxiproxy startup configuration
├── server/
│   ├── server.py           # aiohttp server (HTTP + WebSocket)
│   ├── game.py             # Game engine
│   ├── static/
│   │   ├── index.html      # Live dashboard (spectate + leaderboard)
│   │   └── docs.html       # API docs page
│   ├── requirements.txt
│   └── Dockerfile
├── client/
│   ├── client.py           # Example AI client (BFS pathfinding)
│   ├── run_clients.py      # Batch launcher
│   ├── requirements.txt
│   └── Dockerfile
├── docs/
│   ├── API.md              # API docs (Markdown, Chinese)
│   ├── API_en.md           # API docs (Markdown, English)
│   ├── DESIGN.md           # Design doc (Chinese)
│   └── DESIGN_en.md        # Design doc (English)
├── tests/
│   ├── test_client_retry.py
│   ├── test_game_logic.py
│   ├── test_server_e2e.py
│   ├── test_toxiproxy_integration.py
│   └── test_support.py
└── README_zh.md            # Chinese entry documentation
```

## Quick Start

### Docker Compose (Recommended)

```bash
docker compose up -d
```

This default stack starts:
- **server** — Game server on port `15000`
- **bot** — 20 example AI clients auto-join the game

To start the full weak-network lab instead:

```bash
docker compose -f docker-compose.full.yml up -d
```

The full stack additionally starts:
- **toxiproxy** — Optional TCP proxy on `8474` / `15001`
- **bot_toxic** — Example degraded bots that connect through the proxy

Adjust server defaults in `config/server.json` when needed:

```json
{
    "tick_rate": 10,
    "send_timeout_ms": 80,
    "disconnect_grace_ms": 3000,
    "spectator_reconnect_ms": 2000,
    "max_registered_players": 200,
    "max_spectators": 50
}
```

Environment variables still override the file when you need per-run tweaks or test injection. The compose files explicitly set `SNAKE_SERVER_CONFIG=/app/config/server.json` and bind-mount the host-side `config/server.json`, so editing that file affects the next container start without rebuilding the image.

If you want to point the server at your own config file, use one of these patterns:

```bash
SNAKE_SERVER_CONFIG=/absolute/path/to/custom-server.json python server/server.py
```

```yaml
services:
    server:
        environment:
            SNAKE_SERVER_CONFIG: /app/config/classroom-a.json
        volumes:
            - ./config/classroom-a.json:/app/config/classroom-a.json:ro
```

If you keep the custom file at `/app/config/server.json` inside the container, you do not need to change `SNAKE_SERVER_CONFIG`; mounting over that path is enough.

Open your browser:
- `http://localhost:15000/` — Live dashboard
- `http://localhost:15000/docs` — API documentation

Bot count can be adjusted via the `-n` parameter in `docker-compose.yml` or `docker-compose.full.yml`.

### Manual Deployment

```bash
# Start server
cd server
pip install -r requirements.txt
python server.py

# Start example clients (in another terminal)
cd client
pip install -r requirements.txt
python run_clients.py -n 10                # Launch 10 AIs
python run_clients.py -n 5 --server http://192.168.1.100:15000  # Custom server
```

## Game Rules

| Item | Value |
|------|-------|
| Field size | 100 × 100 |
| Tick rate | Configurable via `config/server.json` or `SNAKE_TICK_RATE` override (default: 10/sec) |
| Initial length | 3 |
| Death | Hit wall / self / other snake / head-on collision |
| On death | Body turns into food that slowly decays over time |
| Respawn | Automatic at a random position |

## Server Tuning

The server reads runtime defaults from `config/server.json`. For ad-hoc overrides, the existing environment variables still work and take precedence over the file.

- `tick_rate` / `SNAKE_TICK_RATE`: server game loop frequency. Lower it when classroom Wi-Fi or browser rendering becomes unstable.
- `send_timeout_ms` / `SNAKE_SEND_TIMEOUT_MS`: per-send WebSocket timeout. Each connection has its own sender task, so a slow client only stalls itself.
- `disconnect_grace_ms` / `SNAKE_DISCONNECT_GRACE_MS`: reconnect grace window. After disconnect, the snake keeps moving in its last direction and can be resumed with the same key during this window.
- `spectator_reconnect_ms` / `SNAKE_SPECTATOR_RECONNECT_MS`: dashboard spectator auto-reconnect interval.
- `max_registered_players` / `SNAKE_MAX_REGISTERED_PLAYERS`: total registration cap. `0` disables the cap.
- `max_spectators` / `SNAKE_MAX_SPECTATORS`: concurrent spectator connection cap. `0` disables the cap.
- Dashboard now includes a survival tab with average survival length and average survival time per bot, which is usually more informative than the single lucky max-length record.

The server now fans out snapshots through independent per-connection sender tasks, so the main game loop no longer waits on one client's socket before serving the others.

## Weak-Network Lab

The weak-network lab lives in `docker-compose.full.yml`, so weak-network bots can connect to `http://toxiproxy:15001` while the dashboard and normal bots still use `http://server:15000`.

Useful admin API examples:

```bash
# Add 250ms downstream latency with 50ms jitter
curl -X POST http://localhost:8474/proxies/snake_server/toxics \
    -H 'Content-Type: application/json' \
    -d '{"name":"latency_downstream","type":"latency","stream":"downstream","attributes":{"latency":250,"jitter":50}}'

# Simulate a connection reset after 100ms
curl -X POST http://localhost:8474/proxies/snake_server/toxics \
    -H 'Content-Type: application/json' \
    -d '{"name":"reset_downstream","type":"reset_peer","stream":"downstream","attributes":{"timeout":100}}'

# Blackhole downstream data and close after 60ms
curl -X POST http://localhost:8474/proxies/snake_server/toxics \
    -H 'Content-Type: application/json' \
    -d '{"name":"timeout_downstream","type":"timeout","stream":"downstream","attributes":{"timeout":60}}'

# Allow only 512 bytes through before closing the stream
curl -X POST http://localhost:8474/proxies/snake_server/toxics \
    -H 'Content-Type: application/json' \
    -d '{"name":"limit_downstream","type":"limit_data","stream":"downstream","attributes":{"bytes":512}}'

# Clear all toxics
curl -X POST http://localhost:8474/reset
```

To launch a small batch of degraded bots through the proxy:

```bash
docker compose -f docker-compose.full.yml up -d

# Or start only the proxied bot group from the full stack
docker compose -f docker-compose.full.yml up -d bot_toxic

# Or point a custom client at the proxied endpoint directly
python client.py --server http://localhost:15001 --name LaggyBot
```

The automated weak-network coverage is Docker-backed too. It exercises real HTTP + WebSocket traffic through Toxiproxy for latency, upstream command delay, spectator isolation, reset recovery, timeout blackholes, and limit-data disconnects.

When you are validating reconnect behavior, monitor the direct server status endpoint rather than the proxied one:

```bash
curl http://localhost:15000/status
```

`players_grace_disconnected` is the most useful field for checking whether a proxy-induced disconnect is still inside the grace window.

## Write Your AI

### 1. Get the Example Client & Docs

- API docs: `http://<server>:15000/docs`
- Download example client: `http://<server>:15000/download/client.py`

### 2. Install & Run

```bash
pip install aiohttp
python client.py --server http://<server>:15000 --name "my_snake"
python client.py --server http://<server>:15000 --name "my_snake" --reconnect-delay-ms 1500
```

The sample client reconnect delay is configurable via `--reconnect-delay-ms` or `SNAKE_CLIENT_RECONNECT_DELAY_MS`.
If registration hits a temporary name collision, the sample client now retries with suffixed names before failing.

### 3. Build Your Strategy

Study the example client and API docs, then implement your own decision logic. Each tick the server pushes full game state; your client returns a direction (`up` / `down` / `left` / `right`).

**Strategy ideas:**
- Beginner: Avoid walls and snake bodies, pick a random safe direction
- Intermediate: BFS / A* to find the nearest food
- Advanced: Flood fill for space evaluation, opponent prediction, encirclement

## API Overview

| Endpoint | Description |
|----------|-------------|
| `POST /register` | Register a player, get a key |
| `WS /ws?key=xxx` | WebSocket game connection |
| `GET /status` | Leaderboard and game state |
| `WS /spectate` | Dashboard spectator connection |
| `GET /api/runtime-config` | Dashboard runtime config |
| `GET /docs` | Full API documentation |

See `http://<server>:15000/docs` for the full protocol.

## Tech Stack

- Python 3.12 + aiohttp
- Pure WebSocket communication, no extra dependencies
- Single-file HTML dashboard (Canvas rendering)

## Testing

```bash
python -m pytest tests -v
```

If your environment does not already have pytest installed, run `pip install pytest` first.

If Docker is not available, the Toxiproxy-based suite is skipped automatically and the core local tests still run.

The suite is split into three layers:
- `tests/test_game_logic.py`: core game and stats logic
- `tests/test_server_e2e.py`: end-to-end register / WebSocket / spectator / reconnect scenarios
- `tests/test_toxiproxy_integration.py`: Docker-backed weak-network end-to-end coverage through a real Toxiproxy instance

## License

[Apache License 2.0](LICENSE)
