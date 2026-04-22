# SnakeRoyale — Benchmark Guide

Current version: `0.4.0`

## Overview

0.4.0 adds a local benchmark workflow for scripted mixed-bot evaluation.

Current behavior:
- Starts a fixed-duration room with a mixed roster of bots, then resets into a clean measured benchmark state once the roster is ready.
- Records an authoritative replay timeline into `replay.jsonl`, starting from the measured benchmark window and carrying a unique `benchmark_run_id`, the same per-tick state snapshot broadcast live by the server, and the follow-up replay events emitted for that tick.
- Produces `summary.json` and `summary.md` with exact per-bot and per-algorithm metrics from server runtime stats, keyed by the same `benchmark_run_id`.
- Hard-fails if a configured bot never joins the room.
- Hard-fails if a configured bot exits or drops out of the room before the benchmark duration completes.
- Phase-1 limit: maximum `20` benchmark bots.

## 1. Run a Benchmark

Sample run:

```bash
python benchmark/runner.py \
  --config benchmark/examples/mixed_room.json \
  --output /tmp/snake-benchmark-demo
```

## 2. Config Schema

Example config:

```json
{
  "benchmark_name": "mixed-room-demo",
  "duration_seconds": 120,
  "server_env": {
    "SNAKE_TICK_RATE": "8",
    "SNAKE_SEND_TIMEOUT_MS": "120",
    "SNAKE_DISCONNECT_GRACE_MS": "0",
    "SNAKE_MAX_REGISTERED_PLAYERS": "20",
    "SNAKE_MAX_SPECTATORS": "4"
  },
  "bots": [
    {
      "algorithm": "baseline",
      "entrypoint": "client/client.py",
      "count": 4,
      "extra_args": ["--reconnect-delay-ms", "200"]
    }
  ]
}
```

Top-level fields:
- `benchmark_name` — label used in artifacts and replay UI
- `duration_seconds` — measured benchmark duration
- `server_env` — temporary server overrides applied only for this run
- `bots` — bot groups to launch

Per-bot-group fields:
- `algorithm` — algorithm label used in summaries
- `entrypoint` — script path to launch
- `count` — number of instances in the group
- `name_prefix` — optional name prefix override
- `extra_args` — optional extra CLI args for the bot process
- `env` — optional per-bot environment variables

## 3. Output Artifacts

The output directory contains:
- `replay.jsonl` — metadata plus the authoritative live state snapshot for each benchmark tick, including `benchmark_run_id` and the follow-up replay events attached to that tick
- `summary.json` — machine-readable benchmark result, including `benchmark_run_id`
- `summary.md` — human-readable benchmark summary
- `roster.json` — resolved bot roster, algorithm labels, and entrypoints

## 4. Replay Viewer

Start the server UI if needed:

```bash
python server/server.py
```

Then open `http://localhost:15000/replay` and upload `replay.jsonl`.

If you also upload `summary.json`, the viewer shows per-algorithm winners and aggregate cards. The overlay is rejected when `benchmark_run_id` or core benchmark metadata do not match the loaded replay.

## 5. Notes and Limits

- The benchmark workflow is local and single-run oriented.
- Benchmark artifacts are designed for analysis and replay, not for concurrent benchmark orchestration.
- Phase 1 intentionally caps the room at `20` benchmark bots to keep runs easy to inspect in class.