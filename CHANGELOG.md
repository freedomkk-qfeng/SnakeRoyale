# Changelog

All notable changes to this project should be recorded in this file.

The format follows a simple versioned changelog and starts formal tracking from `0.2.0`.

## [Unreleased]

## [0.3.0] - 2026-04-20

### Added

- Built-in Toxiproxy weak-network lab wiring in `docker-compose.full.yml`, alongside a smaller default compose stack for normal classroom use.
- Docker-backed end-to-end weak-network coverage for latency, upstream control lag, spectator isolation, reset recovery, timeout blackholes, and limit-data disconnects.
- JSON-backed server runtime defaults in `config/server.json`, with support for overriding the file path via `SNAKE_SERVER_CONFIG`.
- Registration and spectator capacity controls, surfaced through `/status` and `/api/runtime-config`.
- Regression coverage for server-side capacity limits and client registration retry behavior.

### Changed

- README and design documentation now describe the weak-network lab, the expanded test strategy, and the operational role of `/status` during proxy fault injection.
- Server runtime tuning is now centered on `config/server.json`, while the existing environment variables remain as higher-priority overrides.
- The example client now retries repeated 409 name conflicts instead of failing after a single suffix attempt.

### Fixed

- Prevented the main game loop from dying silently on unexpected per-iteration exceptions.

## [0.2.0] - 2026-04-17

### Added

- Centralized runtime configuration for tick rate, send timeout, disconnect grace period, and spectator reconnect interval.
- Independent per-connection sender tasks and mailbox-based outbound delivery.
- Reconnect grace-window support so a player can resume the same snake with the same key.
- Survival statistics in the dashboard, including average length and average survival time.
- Automated test suite covering both game logic and end-to-end network scenarios.
- `DESIGN` document as a permanent architecture and rationale reference.
- Formal changelog tracking starting from this release.

### Changed

- Default `SNAKE_TICK_RATE` moved to `10` while remaining fully configurable.
- Dashboard sidebar and survival ranking layout were adjusted to improve readability.
- README files are now the explicit documentation entry point and link to the four required documentation parts.

### Fixed

- Resolved head-of-line blocking caused by sequential WebSocket broadcasting.
- Reduced the impact of slow clients so they primarily affect their own connection.
- Fixed multiple dashboard ranking presentation issues, including survival-tab layout and bot-name visibility.

## [0.1.0]

- Previous baseline release before formal changelog tracking.