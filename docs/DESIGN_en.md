# SnakeRoyale Design

Current version: `0.2.0`

## Goals

SnakeRoyale is a lightweight multiplayer snake arena for AI programming classes.

The design priorities are:

1. Keep deployment simple enough for classroom use.
2. Keep the protocol easy enough for students to read and implement quickly.
3. Keep the server authoritative so game rules remain deterministic.
4. Keep observability high with a live dashboard and operational status endpoints.
5. Keep the system resilient enough that a single slow client does not degrade everyone else.

## High-Level Architecture

The project has three runtime pieces:

1. `server/`
   Runs the game loop, registration API, WebSocket gameplay connections, spectator connections, and dashboard static assets.
2. `client/`
   Provides a reference AI bot and a batch launcher for classroom demos and smoke testing.
3. `server/static/`
   Hosts the dashboard that visualizes the arena, live ranking, and survival statistics.

The server is the single source of truth for simulation state.

## Core Runtime Model

### Authoritative Tick Loop

The game advances in discrete ticks. On each tick the server:

1. Applies pending directions.
2. Computes next head positions.
3. Resolves wall, body, and head-to-head collisions.
4. Updates bodies, food, scores, and historical records.
5. Emits a state snapshot for players and spectators.

This keeps the gameplay model simple and deterministic, which is more important for teaching than client-side smoothness tricks.

### Full-State Broadcast Protocol

The current protocol sends full state snapshots rather than deltas.

Why:

1. It is easier for students to reason about.
2. It reduces protocol complexity and debugging cost.
3. It makes reconnection and dashboard rendering straightforward.

Tradeoff:

1. It uses more bandwidth than a delta protocol.
2. It benefits from conservative tick-rate tuning in weak classroom networks.

## Networking Design

### Independent Sender Tasks

The current networking design isolates each connection with its own sender task and mailbox.

The main game loop no longer sends directly to every WebSocket in sequence. Instead it only pushes the latest outbound batch into a per-connection mailbox.

This design exists to avoid head-of-line blocking.

Effect:

1. A single slow client should primarily affect itself.
2. The main simulation loop is no longer forced to wait on all client sockets serially.
3. Dashboard spectator traffic is isolated from bot/player traffic.

### Reconnect Grace Window

When a player disconnects unexpectedly, the snake is not removed immediately.

Instead the server keeps the snake alive for a configurable grace window. If the same player reconnects with the same key during that window, the connection resumes the same snake.

This reduces disruption from temporary Wi-Fi instability during class.

### Configurable Runtime Knobs

The following values are intentionally configurable:

1. `SNAKE_TICK_RATE`
2. `SNAKE_SEND_TIMEOUT_MS`
3. `SNAKE_DISCONNECT_GRACE_MS`
4. `SNAKE_SPECTATOR_RECONNECT_MS`

This allows operators to tune the game for different classroom environments without code changes.

## Dashboard Design

The dashboard serves two audiences:

1. Instructors and students who want a quick overview of the match.
2. Operators who want to know whether the system is healthy.

The dashboard shows:

1. Live arena rendering.
2. Current leaderboard by body length.
3. Survival statistics by average length and average survival time.
4. Connection status and event log.

The survival statistics view was added because a single historical max is noisy and luck-sensitive; averaged measures are better for comparing bot quality.

## Documentation Design

The documentation set is organized into four required parts:

1. `README`
   The total entry point for developers, instructors, and contributors.
2. `DESIGN`
   The rationale behind architecture, protocol, and operational tradeoffs.
3. `API`
   The external contract for clients and dashboard consumers.
4. `CHANGELOG`
   A versioned record of behavior, protocol, and product changes.

This structure is intended to make future changes easier to track and explain.

## Testing Strategy

The project uses two layers of automated validation:

1. Logic tests for game rules and statistics behavior.
2. End-to-end tests for registration, WebSocket gameplay, spectator state, reconnect grace, and resume behavior.

This split is intentional: game logic bugs and networking bugs fail differently and should remain easy to isolate.

## Known Tradeoffs

1. Full-state snapshots are simpler than deltas but heavier on bandwidth.
2. Dashboard rendering is driven by received snapshots, so visual smoothness is limited by broadcast cadence unless interpolation is added later.
3. The current implementation is optimized for classroom scale, not very large public deployments.