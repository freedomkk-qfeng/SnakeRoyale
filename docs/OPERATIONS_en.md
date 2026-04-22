# SnakeRoyale — Operations Guide

Current version: `0.4.0`

## Overview

This guide covers deployment, runtime tuning, weak-network lab usage, and test execution.

## 1. Deployment Paths

### Docker Compose

Recommended default stack:

```bash
docker compose up -d
```

This starts:
- `server` — game server on port `15000`
- `bot` — 20 example AI clients

Full weak-network lab stack:

```bash
docker compose -f docker-compose.full.yml up -d
```

This additionally starts:
- `toxiproxy` — proxy admin/API on `8474`, proxied game endpoint on `15001`
- `bot_toxic` — example bots that connect through the proxy

Open in a browser:
- `http://localhost:15000/` — live dashboard
- `http://localhost:15000/docs` — API docs
- `http://localhost:15000/replay` — replay viewer for benchmark artifacts

### Manual Deployment

```bash
# Start server
cd server
pip install -r requirements.txt
python server.py

# Start example clients in another terminal
cd client
pip install -r requirements.txt
python run_clients.py -n 10
python run_clients.py -n 5 --server http://192.168.1.100:15000
```

## 2. Runtime Config

The server reads defaults from `config/server.json`.

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

Environment variables still override file values.

Useful settings:
- `tick_rate` / `SNAKE_TICK_RATE` — game loop frequency
- `send_timeout_ms` / `SNAKE_SEND_TIMEOUT_MS` — per-send WebSocket timeout
- `disconnect_grace_ms` / `SNAKE_DISCONNECT_GRACE_MS` — reconnect grace window
- `spectator_reconnect_ms` / `SNAKE_SPECTATOR_RECONNECT_MS` — dashboard reconnect interval
- `max_registered_players` / `SNAKE_MAX_REGISTERED_PLAYERS` — total registration cap, `0` disables it
- `max_spectators` / `SNAKE_MAX_SPECTATORS` — spectator cap, `0` disables it

The compose files explicitly mount `config/server.json` and set `SNAKE_SERVER_CONFIG=/app/config/server.json`, so editing that file affects the next container start without rebuilding the image.

To point the server at a custom config file:

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

If you mount your custom file directly onto `/app/config/server.json`, you do not need to change `SNAKE_SERVER_CONFIG`.

## 3. Weak-Network Lab

The weak-network lab uses `docker-compose.full.yml`. Proxied bots connect to `http://toxiproxy:15001`, while the dashboard and normal bots still use `http://server:15000`.

Useful Toxiproxy admin API examples:

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

Launch proxied bots:

```bash
docker compose -f docker-compose.full.yml up -d
docker compose -f docker-compose.full.yml up -d bot_toxic
python client.py --server http://localhost:15001 --name LaggyBot
```

When validating reconnect behavior, monitor the direct server status endpoint instead of the proxied one:

```bash
curl http://localhost:15000/status
```

`players_grace_disconnected` is the most useful field for checking whether a proxy-induced disconnect is still inside the reconnect grace window.

## 4. Testing

Run the test suite with:

```bash
python -m pytest tests -v
```

If pytest is not installed yet:

```bash
pip install pytest
```

If Docker is not available, the Toxiproxy-backed suite is skipped automatically while the core local tests still run.

Test layers:
- `tests/test_game_logic.py` — game rules and stats logic
- `tests/test_server_e2e.py` — register / WebSocket / spectator / reconnect scenarios
- `tests/test_toxiproxy_integration.py` — Docker-backed weak-network end-to-end coverage