import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.config import BenchmarkBotConfig, BenchmarkConfig
from benchmark.report import build_summary
from benchmark.runner import run_benchmark


class BenchmarkRunnerTests(unittest.IsolatedAsyncioTestCase):
    def test_build_summary_uses_raw_metrics_for_winner_selection(self):
        summary, _ = build_summary(
            per_bot=[
                {
                    "name": "Alpha",
                    "algorithm": "algo-a",
                    "entrypoint": "client/client.py",
                    "rounds": 1,
                    "completed_rounds": 1,
                    "avg_survival_ticks": 10.004,
                    "avg_survival_seconds": 1.0004,
                    "avg_length": 5.004,
                    "best_length": 8,
                    "current_length": 0,
                    "alive": False,
                    "total_life_ticks": 10.004,
                    "total_length_accumulator": 50.060016,
                },
                {
                    "name": "Beta",
                    "algorithm": "algo-b",
                    "entrypoint": "client/client.py",
                    "rounds": 1,
                    "completed_rounds": 1,
                    "avg_survival_ticks": 10.003,
                    "avg_survival_seconds": 1.0003,
                    "avg_length": 5.003,
                    "best_length": 8,
                    "current_length": 0,
                    "alive": False,
                    "total_life_ticks": 10.003,
                    "total_length_accumulator": 50.040009,
                },
            ],
            duration_seconds=1.0,
            replay_file="replay.jsonl",
            benchmark_name="raw-ranking",
            benchmark_run_id="run-1",
            start_tick=0,
            tick=8,
            tick_rate=8,
            version="0.4.0",
        )

        self.assertEqual(summary["winners"]["bot_by_avg_survival_seconds"]["name"], "Alpha")
        self.assertEqual(summary["winners"]["bot_by_avg_length"]["name"], "Alpha")

    async def test_run_benchmark_writes_summary_and_replay(self):
        config = BenchmarkConfig(
            benchmark_name="smoke-benchmark",
            duration_seconds=1.5,
            server_env={
                "SNAKE_TICK_RATE": "8",
                "SNAKE_SEND_TIMEOUT_MS": "120",
                "SNAKE_DISCONNECT_GRACE_MS": "0",
                "SNAKE_MAX_REGISTERED_PLAYERS": "10",
                "SNAKE_MAX_SPECTATORS": "10",
            },
            bots=[
                BenchmarkBotConfig(
                    algorithm="baseline",
                    entrypoint="client/client.py",
                    count=1,
                    extra_args=["--reconnect-delay-ms", "100"],
                )
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            summary = await run_benchmark(config, temp_dir)
            output_dir = Path(temp_dir)
            summary_path = output_dir / "summary.json"
            summary_md_path = output_dir / "summary.md"
            replay_path = output_dir / "replay.jsonl"
            roster_path = output_dir / "roster.json"

            self.assertTrue(summary_path.exists())
            self.assertTrue(summary_md_path.exists())
            self.assertTrue(replay_path.exists())
            self.assertTrue(roster_path.exists())

            written_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(written_summary["benchmark_name"], "smoke-benchmark")
            self.assertEqual(summary["benchmark_name"], "smoke-benchmark")
            self.assertTrue(written_summary["benchmark_run_id"])
            self.assertEqual(len(written_summary["per_bot"]), 1)
            self.assertEqual(written_summary["per_bot"][0]["algorithm"], "baseline")
            self.assertEqual(written_summary["per_algorithm"][0]["algorithm"], "baseline")
            self.assertEqual(written_summary["replay_file"], "replay.jsonl")

            replay_lines = replay_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertGreaterEqual(len(replay_lines), 2)
            metadata = json.loads(replay_lines[0])
            self.assertEqual(metadata["type"], "metadata")
            self.assertEqual(metadata["benchmark_run_id"], written_summary["benchmark_run_id"])
            first_frame = json.loads(replay_lines[1])
            last_frame = json.loads(replay_lines[-1])
            self.assertEqual(first_frame["type"], "frame")
            self.assertIn("events", first_frame)
            self.assertEqual(first_frame["tick"], written_summary["start_tick"])
            self.assertEqual(len(first_frame["state"]["snakes"]), 1)
            self.assertEqual(first_frame["state"]["snakes"][0]["length"], 3)
            self.assertEqual(first_frame["state"]["record"]["length"], 0)
            self.assertEqual(first_frame["state"]["performance"][0]["avg_survival_ticks"], 0.0)
            self.assertEqual(first_frame["state"]["performance"][0]["rounds"], 0)
            self.assertEqual(last_frame["tick"], written_summary["tick"])

    async def test_run_benchmark_normalizes_whitespace_in_algorithm_and_prefix(self):
        config = BenchmarkConfig(
            benchmark_name=" whitespace-benchmark ",
            duration_seconds=1.2,
            server_env={
                "SNAKE_TICK_RATE": "8",
                "SNAKE_SEND_TIMEOUT_MS": "120",
                "SNAKE_DISCONNECT_GRACE_MS": "0",
                "SNAKE_MAX_REGISTERED_PLAYERS": "10",
                "SNAKE_MAX_SPECTATORS": "10",
            },
            bots=[
                BenchmarkBotConfig(
                    algorithm=" baseline ",
                    entrypoint=" client/client.py ",
                    count=1,
                    name_prefix=" agent ",
                    extra_args=["--reconnect-delay-ms", "100"],
                )
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            summary = await run_benchmark(config, temp_dir)
            roster = json.loads((Path(temp_dir) / "roster.json").read_text(encoding="utf-8"))

        self.assertEqual(summary["benchmark_name"], "whitespace-benchmark")
        self.assertEqual(summary["per_bot"][0]["algorithm"], "baseline")
        self.assertEqual(summary["per_bot"][0]["name"], "agent_01")
        self.assertEqual(set(roster), {"agent_01"})

    async def test_run_benchmark_keeps_unique_names_across_multiple_groups(self):
        config = BenchmarkConfig(
            benchmark_name="multi-group-benchmark",
            duration_seconds=1.5,
            server_env={
                "SNAKE_TICK_RATE": "8",
                "SNAKE_SEND_TIMEOUT_MS": "120",
                "SNAKE_DISCONNECT_GRACE_MS": "0",
                "SNAKE_MAX_REGISTERED_PLAYERS": "10",
                "SNAKE_MAX_SPECTATORS": "10",
            },
            bots=[
                BenchmarkBotConfig(
                    algorithm="baseline",
                    entrypoint="client/client.py",
                    count=1,
                    extra_args=["--reconnect-delay-ms", "100"],
                ),
                BenchmarkBotConfig(
                    algorithm="baseline",
                    entrypoint="client/client.py",
                    count=1,
                    extra_args=["--reconnect-delay-ms", "100"],
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            summary = await run_benchmark(config, temp_dir)
            roster = json.loads((Path(temp_dir) / "roster.json").read_text(encoding="utf-8"))

        self.assertEqual(set(roster), {"baseline_01", "baseline_02"})
        self.assertEqual({item["name"] for item in summary["per_bot"]}, {"baseline_01", "baseline_02"})

    async def test_run_benchmark_supports_builtin_bfs_and_random_clients(self):
        config = BenchmarkConfig(
            benchmark_name="builtin-algorithms-benchmark",
            duration_seconds=1.2,
            server_env={
                "SNAKE_TICK_RATE": "8",
                "SNAKE_SEND_TIMEOUT_MS": "120",
                "SNAKE_DISCONNECT_GRACE_MS": "0",
                "SNAKE_MAX_REGISTERED_PLAYERS": "10",
                "SNAKE_MAX_SPECTATORS": "10",
            },
            bots=[
                BenchmarkBotConfig(
                    algorithm="bfs",
                    entrypoint="client/client.py",
                    count=1,
                    extra_args=["--reconnect-delay-ms", "100"],
                ),
                BenchmarkBotConfig(
                    algorithm="random",
                    entrypoint="client/random_client.py",
                    count=1,
                    extra_args=["--reconnect-delay-ms", "100"],
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            summary = await run_benchmark(config, temp_dir)
            roster = json.loads((Path(temp_dir) / "roster.json").read_text(encoding="utf-8"))

        self.assertEqual({item["algorithm"] for item in summary["per_algorithm"]}, {"bfs", "random"})
        self.assertEqual(
            {details["entrypoint"] for details in roster.values()},
            {"client/client.py", "client/random_client.py"},
        )

    async def test_run_benchmark_fails_when_bot_exits_before_joining(self):
        config = BenchmarkConfig(
            benchmark_name="failing-benchmark",
            duration_seconds=0.5,
            server_env={
                "SNAKE_TICK_RATE": "8",
                "SNAKE_DISCONNECT_GRACE_MS": "0",
            },
            bots=[
                BenchmarkBotConfig(
                    algorithm="broken",
                    entrypoint="tests/fixtures/does_not_exist.py",
                    count=1,
                )
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(RuntimeError):
                await run_benchmark(config, temp_dir)

    async def test_run_benchmark_fails_when_bot_exits_mid_run(self):
        config = BenchmarkConfig(
            benchmark_name="midrun-crash-benchmark",
            duration_seconds=1.2,
            server_env={
                "SNAKE_TICK_RATE": "8",
                "SNAKE_DISCONNECT_GRACE_MS": "0",
                "SNAKE_MAX_REGISTERED_PLAYERS": "10",
            },
            bots=[
                BenchmarkBotConfig(
                    algorithm="crash-bot",
                    entrypoint="tests/fixtures/crash_after_join.py",
                    count=1,
                )
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(RuntimeError):
                await run_benchmark(config, temp_dir)

    async def test_run_benchmark_fails_when_bot_disconnects_but_process_stays_alive(self):
        config = BenchmarkConfig(
            benchmark_name="disconnect-benchmark",
            duration_seconds=1.2,
            server_env={
                "SNAKE_TICK_RATE": "8",
                "SNAKE_DISCONNECT_GRACE_MS": "0",
                "SNAKE_MAX_REGISTERED_PLAYERS": "10",
            },
            bots=[
                BenchmarkBotConfig(
                    algorithm="disconnect-bot",
                    entrypoint="tests/fixtures/disconnect_after_join.py",
                    count=1,
                )
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(RuntimeError):
                await run_benchmark(config, temp_dir)

    async def test_run_benchmark_fails_when_bot_briefly_disconnects_and_reconnects(self):
        config = BenchmarkConfig(
            benchmark_name="brief-disconnect-benchmark",
            duration_seconds=1.2,
            server_env={
                "SNAKE_TICK_RATE": "8",
                "SNAKE_DISCONNECT_GRACE_MS": "0",
                "SNAKE_MAX_REGISTERED_PLAYERS": "10",
            },
            bots=[
                BenchmarkBotConfig(
                    algorithm="blink-bot",
                    entrypoint="tests/fixtures/disconnect_and_reconnect_fast.py",
                    count=1,
                )
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(RuntimeError):
                await run_benchmark(config, temp_dir)

    async def test_run_benchmark_rejects_rosters_over_twenty_bots(self):
        config = BenchmarkConfig(
            benchmark_name="too-many-bots",
            duration_seconds=0.5,
            bots=[
                BenchmarkBotConfig(
                    algorithm="baseline",
                    entrypoint="client/client.py",
                    count=21,
                )
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                await run_benchmark(config, temp_dir)