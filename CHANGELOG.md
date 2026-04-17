# Changelog

All notable changes to this project should be recorded in this file.

The format follows a simple versioned changelog and starts formal tracking from `0.2.0`.

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