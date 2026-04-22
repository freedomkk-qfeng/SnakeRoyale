# SnakeRoyale — API Docs

Current version: `0.4.0`

## Overview

SnakeRoyale is a multiplayer online snake battle arena. The server runs the game engine; clients connect over the network to control their snakes.

- **Server**: `http://<host>:15000`
- **Protocol**: HTTP (registration) + WebSocket (gameplay)
- **Data format**: JSON
- **Dashboard**: `http://<host>:15000/`
- **Replay Viewer**: `http://<host>:15000/replay`
- **This page**: `http://<host>:15000/docs`

## Game Rules

| Item | Value |
|------|-------|
| Field size | 100 × 100 cells |
| Coordinates | (0,0) is top-left, x grows right, y grows down |
| Tick rate | Configurable via `config/server.json` or `SNAKE_TICK_RATE` override (default: 10/sec) |
| Initial length | 3 |
| Death conditions | Hit wall / self / other snake / head-on collision |
| On death | Auto-respawn at random position, length reset to 3, score reset to 0 |
| Death drop | Dead snake's body turns into food at original positions, slowly decays over time |
| Food | Eating food: +1 length, +1 score |

---

## 1. Register

### `POST /register`

Register a player name and get a game key.

**Request Body:**
```json
{
  "name": "your_name"
}
```

**Success (200):**
```json
{
  "key": "a1b2c3d4e5f6g7h8",
  "name": "your_name"
}
```

**Errors:**
- `400` — name is empty, exceeds 20 characters, or invalid JSON
- `409` — name already taken
- `503` — registered-player limit reached

> ⚠️ Save your `key` — you'll need it for all subsequent operations.

---

## 2. Connect

### `WebSocket /ws?key=<your_key>`

Connect via WebSocket using the key from registration. Your snake spawns automatically at a random position.

**Python example:**
```python
import aiohttp, asyncio

async def main():
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect("http://host:15000/ws?key=your_key") as ws:
            async for msg in ws:
                data = msg.json()
                # handle messages...

asyncio.run(main())
```

**JavaScript / Node.js example:**
```javascript
const WebSocket = require('ws');
const ws = new WebSocket('ws://host:15000/ws?key=your_key');

ws.on('message', (data) => {
    const state = JSON.parse(data);
    // handle messages...
});
```

### `WebSocket /spectate`

Connect to the dashboard spectator stream. No auth key is required.

- Success: receives the same full-state snapshots used by the live dashboard.
- Failure: handshake is rejected with `503` when the spectator connection cap is reached.

---

## 3. Message Protocol

### 3.1 Server → Client

#### `welcome` — Connection established

Received immediately after connecting:

```json
{
  "type": "welcome",
  "you": 1,
  "name": "your_name",
  "field": {"width": 100, "height": 100},
  "tick_rate": 10,
  "send_timeout_ms": 80,
  "disconnect_grace_ms": 3000,
  "resumed": false
}
```

> `you` is your snake's public ID (integer), used to find yourself in the `snakes` array of `state` messages.

If the socket drops unexpectedly, the server keeps a short reconnect grace window. Reconnecting with the same key during `disconnect_grace_ms` returns `resumed: true`, meaning you reattach to the same snake instead of spawning a new one.

Extra `welcome` fields:
- `send_timeout_ms` — Active server-side threshold for a single WebSocket send
- `disconnect_grace_ms` — Reconnect grace window for resuming the same snake with the same key
- `resumed` — Whether this connection resumed an existing snake during the grace window

#### `state` — Game state (every tick)

```json
{
  "type": "state",
  "tick": 1234,
  "you": 1,
  "tick_rate": 10,
  "field": {"width": 100, "height": 100},
  "snakes": [
    {
      "id": 1,
      "name": "player_name",
      "body": [[10, 5], [9, 5], [8, 5]],
      "direction": "right",
      "alive": true,
      "score": 7,
      "length": 10
    }
  ],
  "foods": [[20, 30], [55, 12]],
  "record": {"name": "top_player", "length": 58},
  "performance": [
    {
      "id": 1,
      "name": "Bot_01",
      "alive": true,
      "rounds": 4,
      "completed_rounds": 3,
      "avg_length": 8.75,
      "avg_survival_ticks": 42.5,
      "avg_survival_seconds": 7.08,
      "best_length": 18,
      "current_length": 9
    }
  ]
}
```

**Fields:**
- `snakes[].id` — Snake's public ID (integer). Find `id == you` to locate yourself
- `snakes[].body` — Array of coordinates, `body[0]` is the head
- `snakes[].direction` — Current direction: `"up"` / `"down"` / `"left"` / `"right"`
- `you` — Your public ID (integer)
- `tick_rate` — Active server tick configuration, useful for per-step timing budgets on the client side
- `foods` — All food coordinates `[x, y]`
- `record` — All-time longest snake record: `name` and `length`
- `performance` — Aggregated bot metrics for dashboard/ops views, including average survival length, average survival time, and sample count
- `performance[].rounds` — Number of completed lives, plus the current in-progress life if the bot is still alive

#### `death` — Death notification

```json
{
  "type": "death",
  "reason": "hit wall"
}
```

Possible reasons:
- `"hit wall"` — Hit the boundary
- `"hit self"` — Hit own body
- `"hit snake XXX"` — Hit snake named XXX
- `"head-to-head collision"` — Head-on collision with another snake

#### `respawn` — Respawn notification

```json
{
  "type": "respawn"
}
```

Sent immediately after death. Your snake has respawned; the next `state` message will contain your new position.

### 3.2 Client → Server

#### `move` — Change direction

```json
{
  "type": "move",
  "direction": "up",
  "tick": 1234
}
```

- Directions: `"up"` / `"down"` / `"left"` / `"right"`
- `tick` is optional for normal gameplay. SDK clients echo the last observed `state.tick` so benchmark runs can reject stale pre-reset moves; benchmark bots are required to send it.
- 180° reversal is blocked (e.g., can't go left while moving right)
- Only the last direction per tick is applied
- If no move is sent, the snake continues in its current direction

---

## 4. Leaderboard / Game Status

### `GET /status`

View current game status and leaderboard (no auth required).

```json
{
  "version": "0.4.0",
  "tick": 5678,
  "tick_rate": 10,
  "send_timeout_ms": 80,
  "disconnect_grace_ms": 3000,
  "max_registered_players": 200,
  "max_spectators": 50,
  "players_registered": 15,
  "players_connected": 8,
  "players_grace_disconnected": 2,
  "snakes_alive": 8,
  "leaderboard": [
    {"name": "Alice", "score": 42, "length": 45},
    {"name": "Bob", "score": 35, "length": 38}
  ],
  "performance": [
    {"name": "Bot_01", "avg_length": 8.75, "avg_survival_seconds": 7.08, "rounds": 4}
  ]
}
```

`players_grace_disconnected` is the number of players currently disconnected but still retained inside the reconnect grace window.

This field is also the primary observability hook used in the weak-network Toxiproxy lab to verify that proxy-induced disconnects enter and leave the grace window correctly.

- `version` — Current server version
- `max_registered_players` — Active registration cap. `0` means unlimited.
- `max_spectators` — Active spectator cap. `0` means unlimited.

### `GET /api/runtime-config`

Returns runtime config used by the dashboard.

```json
{
  "version": "0.4.0",
  "tick_rate": 10,
  "send_timeout_ms": 80,
  "disconnect_grace_ms": 3000,
  "spectator_reconnect_ms": 2000,
  "max_registered_players": 200,
  "max_spectators": 50
}
```

### `GET /replay`

Serves the browser replay viewer used for local benchmark artifacts.

- Upload `replay.jsonl` to scrub and replay the measured benchmark timeline.
- Upload `summary.json` as an optional overlay to show per-algorithm winners and aggregate metrics.
- Both artifacts are expected to come from the benchmark runner and carry the same `benchmark_run_id`.
- The page rejects overlays whose `benchmark_run_id` or core benchmark metadata do not match the loaded replay.

---

## 5. Quick Start

### Step 1: Register

```bash
curl -X POST http://<host>:15000/register \
  -H "Content-Type: application/json" \
  -d '{"name": "my_snake"}'
```

### Step 2: Write your AI client

Your AI simply needs to:
1. Connect to WebSocket with the key
2. On each `state` message, analyze the game
3. Send a `move` message to choose direction

**Strategy tips:**
- Avoid walls: check distance from head to boundaries
- Avoid snakes: check if any snake body is in adjacent cells
- Chase food: find nearest food and move toward it
- Advanced: pathfinding (BFS/A*), opponent prediction, encirclement

### Step 3: Run & Watch

```bash
# Check leaderboard
curl http://<host>:15000/status

# Open Dashboard in browser
# http://<host>:15000/
```

---

## 6. Error Handling

| Scenario | Behavior |
|----------|----------|
| WebSocket disconnected | Reconnect with the same key |
| Invalid JSON sent | Server ignores the message |
| Invalid direction sent | Server ignores the message |
| Invalid key | WebSocket connection rejected (401) |
| Duplicate connection | Rejected (409), disconnect old session first |
| Registration limit reached | `POST /register` returns 503 |
| Spectator limit reached | `WS /spectate` handshake rejected (503) |

---

## 7. Example Client SDK

We provide a Python client SDK with two built-in algorithms:

- `client.py` — BFS pathfinding client
- `random_client.py` — random safe-move client

SDK runtime responsibilities:

- registration retry on temporary name conflicts
- reconnect loop
- WebSocket connect / receive / send flow

Get the files:

- **[📄 View default BFS source (client.py)](/api/client-source)** — Open in browser, inspect the BFS entrypoint
- **[⬇ Download client SDK bundle](/download/client-sdk.zip)** — Download `client.py`, `random_client.py`, `sdk.py`, and helpers

Install dependency: `pip install aiohttp`

Run:
```bash
python client.py --server http://<host>:15000 --name "your_name"
python random_client.py --server http://<host>:15000 --name "your_random_bot"
```

---

## Appendix: Coordinate Diagram

```
(0,0) ──────────────── (99,0)
  │                       │
  │     Game  Field        │
  │                       │
(0,99) ─────────────── (99,99)
```

Direction and coordinate changes:
- `up`: y - 1
- `down`: y + 1
- `left`: x - 1
- `right`: x + 1
