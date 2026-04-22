import argparse
import asyncio
import contextlib
import importlib
import json
import os
import subprocess
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from aiohttp import web

try:
    from .config import BenchmarkConfig, load_benchmark_config, validate_benchmark_config
    from .report import build_summary
except ImportError:
    from config import BenchmarkConfig, load_benchmark_config, validate_benchmark_config
    from report import build_summary


ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"


class ServerModuleLoader:
    def __init__(self, **env_overrides):
        self.env_overrides = {key: str(value) for key, value in env_overrides.items()}
        self._original_env: dict[str, str | None] = {}
        self._original_modules: dict[str, object | None] = {}
        self._server_path_added = False

    def load(self):
        for key, value in self.env_overrides.items():
            self._original_env[key] = os.environ.get(key)
            os.environ[key] = value

        server_dir_str = str(SERVER_DIR)
        if server_dir_str not in sys.path:
            sys.path.insert(0, server_dir_str)
            self._server_path_added = True

        for module_name in ("server", "game", "config"):
            self._original_modules[module_name] = sys.modules.get(module_name)
            sys.modules.pop(module_name, None)

        importlib.invalidate_caches()
        return importlib.import_module("server")

    def restore(self):
        for key, old_value in self._original_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

        for module_name in ("server", "game", "config"):
            sys.modules.pop(module_name, None)
            original_module = self._original_modules.get(module_name)
            if original_module is not None:
                sys.modules[module_name] = original_module

        if self._server_path_added:
            with contextlib.suppress(ValueError):
                sys.path.remove(str(SERVER_DIR))
        importlib.invalidate_caches()


@dataclass
class BotProcess:
    name: str
    algorithm: str
    entrypoint: str
    process: asyncio.subprocess.Process


async def start_app(server_module):
    app = server_module.create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = getattr(site, "_server").sockets
    port = sockets[0].getsockname()[1]
    return app, runner, f"http://127.0.0.1:{port}"


async def run_benchmark(config: BenchmarkConfig, output_dir: str | Path) -> dict:
    validate_benchmark_config(config)
    output_path = Path(output_dir).resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    replay_path = output_path / "replay.jsonl"
    summary_path = output_path / "summary.json"
    summary_md_path = output_path / "summary.md"
    roster_path = output_path / "roster.json"

    loader = ServerModuleLoader(**config.server_env)
    server_module = None
    app = None
    runner = None
    replay_task = None
    replay_listener = None
    player_event_listener = None
    stop_event = asyncio.Event()
    bot_labels: dict[str, dict] = {}
    processes: list[BotProcess] = []
    replay_queue: asyncio.Queue = asyncio.Queue()
    player_event_queue: asyncio.Queue = asyncio.Queue()
    per_bot: list[dict] = []
    benchmark_run_id = ""
    start_tick = 0
    final_tick = 0

    try:
        server_module = loader.load()
        app, runner, base_url = await start_app(server_module)

        await asyncio.sleep(0.2)
        processes, bot_labels = await _launch_bots(config, base_url)
        roster_path.write_text(json.dumps(bot_labels, indent=2), encoding="utf-8")
        await _wait_for_roster(app, server_module, processes, bot_labels)

        await server_module.pause_game_loop(app)
        try:
            benchmark_run_id = uuid.uuid4().hex
            _reset_benchmark_room(app, server_module, bot_labels)
            start_tick = app[server_module.STATE_KEY].game.tick_count
            replay_listener = replay_queue.put_nowait
            player_event_listener = player_event_queue.put_nowait
            app[server_module.TICK_LISTENERS_KEY].append(replay_listener)
            app[server_module.PLAYER_EVENT_LISTENERS_KEY].append(player_event_listener)

            metadata = {
                "type": "metadata",
                "benchmark_name": config.benchmark_name,
                "benchmark_run_id": benchmark_run_id,
                "duration_seconds": config.duration_seconds,
                "start_tick": start_tick,
                "server_env": config.server_env,
                "started_at": time.time(),
                "tick_rate": server_module.TICK_RATE,
            }
            replay_task = asyncio.create_task(_record_replay(replay_path, metadata, replay_queue, stop_event))
            replay_queue.put_nowait({
                "tick": start_tick,
                "captured_at": time.time(),
                "state": app[server_module.STATE_KEY].game.get_state(),
                "events": [],
            })

            await server_module.push_state_snapshot(app)
            await _wait_for_initial_moves(app, server_module, bot_labels)
        finally:
            server_module.resume_game_loop(app)

        await _wait_for_duration(app, server_module, config.duration_seconds, processes, bot_labels, player_event_queue)
        per_bot = _collect_bot_metrics(app, server_module, bot_labels)
        final_tick = app[server_module.STATE_KEY].game.tick_count
    finally:
        if app is not None and server_module is not None and replay_listener is not None:
            with contextlib.suppress(ValueError):
                app[server_module.TICK_LISTENERS_KEY].remove(replay_listener)
        if app is not None and server_module is not None and player_event_listener is not None:
            with contextlib.suppress(ValueError):
                app[server_module.PLAYER_EVENT_LISTENERS_KEY].remove(player_event_listener)
        stop_event.set()
        await _stop_processes(processes)
        if runner is not None:
            await runner.cleanup()
        if replay_task is not None:
            try:
                await asyncio.wait_for(replay_task, timeout=1.0)
            except asyncio.TimeoutError:
                replay_task.cancel()
                try:
                    await replay_task
                except asyncio.CancelledError:
                    pass
        loader.restore()

    summary, summary_md = build_summary(
        per_bot=per_bot,
        duration_seconds=config.duration_seconds,
        replay_file=replay_path.name,
        benchmark_name=config.benchmark_name,
        benchmark_run_id=benchmark_run_id,
        start_tick=start_tick,
        tick=final_tick,
        tick_rate=server_module.TICK_RATE,
        version=server_module.PROJECT_VERSION,
    )
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary_md_path.write_text(summary_md, encoding="utf-8")
    return summary


async def _record_replay(replay_path: Path, metadata: dict, replay_queue: asyncio.Queue, stop_event: asyncio.Event):
    with replay_path.open("w", encoding="utf-8") as replay_file:
        replay_file.write(json.dumps(metadata) + "\n")
        while True:
            if stop_event.is_set() and replay_queue.empty():
                break
            try:
                payload = await asyncio.wait_for(replay_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            replay_file.write(json.dumps({
                "type": "frame",
                "captured_at": payload.get("captured_at", time.time()),
                "tick": payload.get("tick"),
                "state": payload.get("state"),
                "events": payload.get("events", []),
            }) + "\n")


async def _launch_bots(config: BenchmarkConfig, base_url: str) -> tuple[list[BotProcess], dict[str, dict]]:
    processes: list[BotProcess] = []
    bot_labels: dict[str, dict] = {}
    name_counters: dict[str, int] = defaultdict(int)

    for bot in config.bots:
        entrypoint = bot.resolve_entrypoint(ROOT)
        entrypoint_label = _format_entrypoint_label(entrypoint)
        prefix = bot.name_prefix or bot.algorithm
        for index in range(1, bot.count + 1):
            name_counters[prefix] += 1
            name = f"{prefix}_{name_counters[prefix]:02d}"
            env = os.environ.copy()
            env.update(bot.env)
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(entrypoint),
                "--server",
                base_url,
                "--name",
                name,
                *bot.extra_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
                cwd=str(ROOT),
            )
            processes.append(BotProcess(
                name=name,
                algorithm=bot.algorithm,
                entrypoint=entrypoint_label,
                process=process,
            ))
            bot_labels[name] = {
                "algorithm": bot.algorithm,
                "entrypoint": entrypoint_label,
            }
            await asyncio.sleep(0.05)

    return processes, bot_labels


def _format_entrypoint_label(entrypoint: Path) -> str:
    try:
        return str(entrypoint.relative_to(ROOT))
    except ValueError:
        return str(entrypoint)


async def _wait_for_roster(app, server_module, processes: list[BotProcess], bot_labels: dict[str, dict], timeout: float = 8.0):
    expected_names = set(bot_labels)
    deadline = asyncio.get_running_loop().time() + timeout

    while True:
        for bot in processes:
            if bot.process.returncode is not None:
                raise RuntimeError(f"Benchmark bot {bot.name!r} exited before joining the room (code {bot.process.returncode})")

        present_names = _get_present_room_names(app, server_module, expected_names)
        if present_names == expected_names:
            return

        if asyncio.get_running_loop().time() >= deadline:
            missing = sorted(expected_names - present_names)
            raise RuntimeError(f"Benchmark roster did not fully register before timeout; missing bots: {', '.join(missing)}")

        await asyncio.sleep(0.1)


def _get_present_room_names(app, server_module, expected_names: set[str]) -> set[str]:
    runtime = app[server_module.STATE_KEY]
    connected_names = {connection.name for connection in runtime.connected_clients.values()}
    active_snake_names = {snake.name for snake in runtime.game.snakes.values()}
    return {name for name in expected_names if name in connected_names and name in active_snake_names}


def _reset_benchmark_room(app, server_module, bot_labels: dict[str, dict]):
    runtime = app[server_module.STATE_KEY]
    expected_names = set(bot_labels)
    present_names = _get_present_room_names(app, server_module, expected_names)
    if present_names != expected_names:
        missing = sorted(expected_names - present_names)
        raise RuntimeError(f"Benchmark roster is not fully present at benchmark start; missing bots: {', '.join(missing)}")

    fresh_game = server_module.Game()
    fresh_game.strict_observed_tick = True
    for bot_name in bot_labels:
        snake_id = runtime.player_keys_by_name.get(bot_name)
        if snake_id is None:
            raise RuntimeError(f"Benchmark bot {bot_name!r} is missing from player_keys_by_name at benchmark start")
        existing_snake = runtime.game.snakes.get(snake_id)
        public_id = existing_snake.public_id if existing_snake is not None else None
        fresh_game.spawn_snake(snake_id, bot_name, public_id=public_id)

    fresh_game._ensure_food()
    runtime.game = fresh_game


async def _wait_for_initial_moves(app, server_module, bot_labels: dict[str, dict], timeout: float | None = None):
    runtime = app[server_module.STATE_KEY]
    deadline = asyncio.get_running_loop().time() + (timeout or max(0.5, 2.0 / server_module.TICK_RATE))

    while True:
        all_ready = True
        for bot_name in bot_labels:
            snake_id = runtime.player_keys_by_name.get(bot_name)
            snake = runtime.game.snakes.get(snake_id) if snake_id is not None else None
            if snake is None or not snake.alive:
                raise RuntimeError(f"Benchmark bot {bot_name!r} is missing from the room before benchmark start")
            if snake.pending_direction is None or snake.pending_state_tick != runtime.game.tick_count:
                all_ready = False
                break

        if all_ready:
            runtime.game.strict_observed_tick = False
            return

        if asyncio.get_running_loop().time() >= deadline:
            raise RuntimeError("Benchmark bots did not submit initial moves for the reset snapshot before measurement start")

        await asyncio.sleep(0.01)


async def _wait_for_duration(app, server_module, duration_seconds: float, processes: list[BotProcess], bot_labels: dict[str, dict], player_event_queue: asyncio.Queue, interval: float = 0.1):
    deadline = asyncio.get_running_loop().time() + duration_seconds
    expected_names = set(bot_labels)
    while True:
        for bot in processes:
            if bot.process.returncode is not None:
                raise RuntimeError(f"Benchmark bot {bot.name!r} exited before benchmark completion (code {bot.process.returncode})")

        while not player_event_queue.empty():
            event = player_event_queue.get_nowait()
            if event.get("type") == "player_disconnected" and event.get("name") in expected_names:
                raise RuntimeError(f"Benchmark bot left the room before benchmark completion; missing bots: {event['name']}")

        present_names = _get_present_room_names(app, server_module, expected_names)
        if present_names != expected_names:
            missing = sorted(expected_names - present_names)
            raise RuntimeError(f"Benchmark bot left the room before benchmark completion; missing bots: {', '.join(missing)}")

        if asyncio.get_running_loop().time() >= deadline:
            return

        await asyncio.sleep(interval)


def _collect_bot_metrics(app, server_module, bot_labels: dict[str, dict]) -> list[dict]:
    runtime = app[server_module.STATE_KEY]
    game = runtime.game
    per_bot: list[dict] = []

    for bot_name, label in bot_labels.items():
        snake_id = runtime.player_keys_by_name.get(bot_name)
        if snake_id is None:
            raise RuntimeError(f"Benchmark bot {bot_name!r} is missing from player_keys_by_name")

        stats = game.career_stats.get(snake_id)
        if stats is None:
            raise RuntimeError(f"Benchmark bot {bot_name!r} never produced career stats")

        snake = game.snakes.get(snake_id)
        current_ticks = snake.life_ticks if snake and snake.alive else 0
        current_length_accumulator = snake.length_accumulator if snake and snake.alive else 0
        total_life_ticks = stats.total_life_ticks + current_ticks
        total_length_accumulator = stats.total_length_accumulator + current_length_accumulator
        rounds = stats.completed_lives + (1 if current_ticks > 0 else 0)
        avg_survival_ticks = total_life_ticks / rounds if rounds else 0.0
        avg_length = total_length_accumulator / total_life_ticks if total_life_ticks else 0.0

        per_bot.append({
            "name": bot_name,
            "algorithm": label["algorithm"],
            "entrypoint": label["entrypoint"],
            "rounds": rounds,
            "completed_rounds": stats.completed_lives,
            "avg_survival_ticks": avg_survival_ticks,
            "avg_survival_seconds": avg_survival_ticks / server_module.TICK_RATE,
            "avg_length": avg_length,
            "best_length": max(stats.best_length, len(snake.body) if snake and snake.alive else 0),
            "current_length": len(snake.body) if snake and snake.alive else 0,
            "alive": bool(snake and snake.alive),
            "total_life_ticks": total_life_ticks,
            "total_length_accumulator": total_length_accumulator,
        })

    return per_bot


async def _stop_processes(processes: list[BotProcess]):
    for bot in processes:
        if bot.process.returncode is None:
            bot.process.terminate()

    for bot in processes:
        if bot.process.returncode is not None:
            continue
        try:
            await asyncio.wait_for(bot.process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            bot.process.kill()
            await bot.process.wait()


def main():
    parser = argparse.ArgumentParser(description="Run a SnakeRoyale AI benchmark room")
    parser.add_argument("--config", required=True, help="Path to benchmark JSON config")
    parser.add_argument("--output", required=True, help="Output directory for replay and summaries")
    args = parser.parse_args()

    config = load_benchmark_config(args.config)
    summary = asyncio.run(run_benchmark(config, args.output))
    print(json.dumps(summary["winners"], indent=2))


if __name__ == "__main__":
    main()