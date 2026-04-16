# SnakeRoyale — API Docs

## Overview

SnakeRoyale is a multiplayer online snake battle arena. The server runs the game engine; clients connect over the network to control their snakes.

- **Server**: `http://<host>:15000`
- **Protocol**: HTTP (registration) + WebSocket (gameplay)
- **Data format**: JSON
- **Dashboard**: `http://<host>:15000/`
- **This page**: `http://<host>:15000/docs`

## Game Rules

| Item | Value |
|------|-------|
| Field size | 100 × 100 cells |
| Coordinates | (0,0) is top-left, x grows right, y grows down |
| Tick rate | 10/sec |
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
  "tick_rate": 10
}
```

> `you` is your snake's public ID (integer), used to find yourself in the `snakes` array of `state` messages.

#### `state` — Game state (every tick)

```json
{
  "type": "state",
  "tick": 1234,
  "you": 1,
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
  "record": {"name": "top_player", "length": 58}
}
```

**Fields:**
- `snakes[].id` — Snake's public ID (integer). Find `id == you` to locate yourself
- `snakes[].body` — Array of coordinates, `body[0]` is the head
- `snakes[].direction` — Current direction: `"up"` / `"down"` / `"left"` / `"right"`
- `you` — Your public ID (integer)
- `foods` — All food coordinates `[x, y]`
- `record` — All-time longest snake record: `name` and `length`

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
  "direction": "up"
}
```

- Directions: `"up"` / `"down"` / `"left"` / `"right"`
- 180° reversal is blocked (e.g., can't go left while moving right)
- Only the last direction per tick is applied
- If no move is sent, the snake continues in its current direction

---

## 4. Leaderboard / Game Status

### `GET /status`

View current game status and leaderboard (no auth required).

```json
{
  "tick": 5678,
  "players_registered": 15,
  "players_connected": 8,
  "snakes_alive": 8,
  "leaderboard": [
    {"name": "Alice", "score": 42, "length": 45},
    {"name": "Bob", "score": 35, "length": 38}
  ]
}
```

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

---

## 7. Example Client

We provide a Python AI client using BFS pathfinding, ready to use:

- **[📄 View source (client.py)](/api/client-source)** — Open in browser, copy directly
- **[⬇ Download client.py](/download/client.py)** — Download to local

Install dependency: `pip install aiohttp`

Run:
```bash
python client.py --server http://<host>:15000 --name "your_name"
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
