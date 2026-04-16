# 🐍 SnakeRoyale

[中文文档](README_zh.md)

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![AI Coded](https://img.shields.io/badge/AI_Coded-100%25-A855F7?logo=github-copilot&logoColor=white)](https://github.com/features/copilot)

A multiplayer snake battle arena for AI programming education. Deploy the server, code your AI client, and learn pathfinding & game strategy through competition.

![Dashboard](docs/screenshot_en.png)

## Project Structure

```
snake-royale/
├── docker-compose.yml      # One-command deployment
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
└── docs/
    ├── API.md              # API docs (Markdown, Chinese)
    └── API_en.md           # API docs (Markdown, English)
```

## Quick Start

### Docker Compose (Recommended)

```bash
docker compose up -d
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
| Tick rate | 10/sec |
| Initial length | 3 |
| Death | Hit wall / self / other snake / head-on collision |
| On death | Body turns into food that slowly decays over time |
| Respawn | Automatic at a random position |

## Write Your AI

### 1. Get the Example Client & Docs

- API docs: `http://<server>:15000/docs`
- Download example client: `http://<server>:15000/download/client.py`

### 2. Install & Run

```bash
pip install aiohttp
python client.py --server http://<server>:15000 --name "my_snake"
```

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
| `GET /docs` | Full API documentation |

See `http://<server>:15000/docs` for the full protocol.

## Tech Stack

- Python 3.12 + aiohttp
- Pure WebSocket communication, no extra dependencies
- Single-file HTML dashboard (Canvas rendering)

## License

[Apache License 2.0](LICENSE)
