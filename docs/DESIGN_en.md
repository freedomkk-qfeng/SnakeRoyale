# SnakeRoyale Design

Current version: `0.3.0`

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

`SNAKE_SEND_TIMEOUT_MS` is applied per individual WebSocket send operation. If one connection cannot flush a message inside that budget, that connection is dropped and, for players, transitions into the reconnect-grace flow instead of blocking other sockets.

### Reconnect Grace Window

When a player disconnects unexpectedly, the snake is not removed immediately.

Instead the server keeps the snake alive for a configurable grace window. If the same player reconnects with the same key during that window, the connection resumes the same snake.

This reduces disruption from temporary Wi-Fi instability during class.

### Configurable Runtime Knobs

The server reads its default runtime settings from `config/server.json`.

For temporary overrides, the existing environment variables still take precedence. `SNAKE_SERVER_CONFIG` can point the server at an alternate JSON file.

The following values are intentionally configurable:

1. `SNAKE_TICK_RATE`
2. `SNAKE_SEND_TIMEOUT_MS`
3. `SNAKE_DISCONNECT_GRACE_MS`
4. `SNAKE_SPECTATOR_RECONNECT_MS`
5. `SNAKE_MAX_REGISTERED_PLAYERS`
6. `SNAKE_MAX_SPECTATORS`

This allows operators to tune the game for different classroom environments without code changes.

The two capacity knobs exist as classroom safety rails:

1. Registered players are capped by default so a bad script cannot grow the registration tables without bound during a class.
2. Spectator connections are capped by default so unauthenticated observers cannot fan out unlimited full-state streams.
3. Setting either cap to `0` disables that limit for controlled deployments.

### Weak-Network Validation Lab

The repository now includes a built-in Toxiproxy lab in `docker-compose.full.yml`.

This exists for two reasons:

1. It gives instructors a repeatable way to demonstrate weak-network behavior with real TCP/WebSocket traffic.
2. It gives maintainers an end-to-end validation harness for changes related to sender isolation, reconnect grace, and observability.

The lab keeps the normal dashboard and direct bots on the normal server path while degraded bots or spectators can be routed through `toxiproxy:15001`.

That separation is important because it lets us verify the intended property directly: one impaired path should not stall healthy paths.

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

The project uses three layers of automated validation:

1. Logic tests for game rules and statistics behavior.
2. End-to-end tests for registration, WebSocket gameplay, spectator state, reconnect grace, and resume behavior.
3. Docker-backed weak-network end-to-end tests that route real HTTP and WebSocket traffic through Toxiproxy.

This split is intentional: rule bugs, normal networking bugs, and impaired-network bugs fail differently and should remain easy to isolate.

The weak-network suite specifically covers:

1. Downstream latency on HTTP and WebSocket delivery.
2. Upstream latency delaying player control without stalling direct observers.
3. Direct-player and direct-spectator isolation from proxied slow paths.
4. Reconnect-grace recovery after forced proxy resets.
5. Status-endpoint observability during and after proxy-induced disconnects.
6. Timeout and limit-data toxics that emulate blackholes and truncated streams.

Known limits of this lab:

1. It focuses on transport behaviors that Toxiproxy models directly.
2. It does not currently model kernel-level packet reordering, corruption, or probabilistic loss.
3. If those scenarios become important later, `tc netem` should be added as a second validation layer rather than replacing Toxiproxy.

## Known Tradeoffs

1. Full-state snapshots are simpler than deltas but heavier on bandwidth.
2. Dashboard rendering is driven by received snapshots, so visual smoothness is limited by broadcast cadence unless interpolation is added later.
3. The current implementation is optimized for classroom scale, not very large public deployments.
4. The sample client now retries transient registration name collisions a few times, but it is still only a reference bot and not a full client SDK.