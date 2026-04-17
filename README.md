# 🐍 SnakeRoyale

[中文文档](README_zh.md)

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![AI Coded](https://img.shields.io/badge/AI_Coded-100%25-A855F7?logo=github-copilot&logoColor=white)](https://github.com/features/copilot)

A multiplayer snake battle arena for AI programming education. Deploy the server, code your AI client, and learn pathfinding & game strategy through competition.

![Dashboard](docs/screenshot_en.png)

Current version: `0.2.0`

## Documentation

The project documentation is organized into four fixed parts:

1. [README](README.md) - project overview, quick start, deployment, and testing.
2. [DESIGN](docs/DESIGN_en.md) - architecture, networking model, and design tradeoffs.
3. [API](docs/API_en.md) - client/server protocol and endpoint contract.
4. [CHANGELOG](CHANGELOG.md) - versioned release history.

## Project Structure

```
snake-royale/
├── docker-compose.yml      # One-command deployment
├── CHANGELOG.md            # Versioned release history
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
└── README_zh.md            # Chinese entry documentation
```

## Quick Start

### Docker Compose (Recommended)

```bash
docker compose up -d
```

Adjust server pacing in `docker-compose.yml` when needed:

```yaml
environment:
    SNAKE_TICK_RATE: "10"
    SNAKE_SEND_TIMEOUT_MS: "80"
    SNAKE_DISCONNECT_GRACE_MS: "3000"
    SNAKE_SPECTATOR_RECONNECT_MS: "2000"
```

This starts:
- **server** — Game server on port `15000`
- **bot** — 20 example AI clients auto-join the game

Open your browser:
- `http://localhost:15000/` — Live dashboard
- `http://localhost:15000/docs` — API documentation

Bot count can be adjusted via the `-n` parameter in `docker-compose.yml`.

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
| Tick rate | Configurable via `SNAKE_TICK_RATE` (default: 10/sec) |
| Initial length | 3 |
| Death | Hit wall / self / other snake / head-on collision |
| On death | Body turns into food that slowly decays over time |
| Respawn | Automatic at a random position |

## Server Tuning

- `SNAKE_TICK_RATE`: server game loop frequency. Lower it when classroom Wi-Fi or browser rendering becomes unstable.
- `SNAKE_SEND_TIMEOUT_MS`: per-send WebSocket timeout. Each connection has its own sender task, so a slow client only stalls itself.
- `SNAKE_DISCONNECT_GRACE_MS`: reconnect grace window. After disconnect, the snake keeps moving in its last direction and can be resumed with the same key during this window.
- `SNAKE_SPECTATOR_RECONNECT_MS`: dashboard spectator auto-reconnect interval.
- Dashboard now includes a survival tab with average survival length and average survival time per bot, which is usually more informative than the single lucky max-length record.

The server now fans out snapshots through independent per-connection sender tasks, so the main game loop no longer waits on one client's socket before serving the others.

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
python -m unittest discover -s tests -v
```

The suite is split into two layers:
- `tests/test_game_logic.py`: core game and stats logic
- `tests/test_server_e2e.py`: end-to-end register / WebSocket / spectator / reconnect scenarios

## License

[Apache License 2.0](LICENSE)
