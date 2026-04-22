import json
from dataclasses import dataclass, field
from pathlib import Path


MAX_BENCHMARK_BOTS = 20


@dataclass
class BenchmarkBotConfig:
    algorithm: str
    entrypoint: str
    count: int = 1
    name_prefix: str | None = None
    extra_args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    def resolve_entrypoint(self, root_dir: Path) -> Path:
        entrypoint = Path(self.entrypoint)
        if not entrypoint.is_absolute():
            entrypoint = root_dir / entrypoint
        return entrypoint.resolve()


@dataclass
class BenchmarkConfig:
    duration_seconds: float
    bots: list[BenchmarkBotConfig]
    server_env: dict[str, str] = field(default_factory=dict)
    benchmark_name: str = "snake-benchmark"


def load_benchmark_config(path: str | Path) -> BenchmarkConfig:
    config_path = Path(path).resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8"))

    bots = [
        BenchmarkBotConfig(
            algorithm=item["algorithm"],
            entrypoint=item["entrypoint"],
            count=int(item.get("count", 1)),
            name_prefix=item.get("name_prefix"),
            extra_args=[str(arg) for arg in item.get("extra_args", [])],
            env={str(key): str(value) for key, value in item.get("env", {}).items()},
        )
        for item in payload.get("bots", [])
    ]

    config = BenchmarkConfig(
        duration_seconds=float(payload["duration_seconds"]),
        bots=bots,
        server_env={str(key): str(value) for key, value in payload.get("server_env", {}).items()},
        benchmark_name=str(payload.get("benchmark_name", config_path.stem)),
    )
    validate_benchmark_config(config)
    return config


def validate_benchmark_config(config: BenchmarkConfig):
    if config.duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if not config.bots:
        raise ValueError("benchmark config must include at least one bot definition")

    config.benchmark_name = config.benchmark_name.strip() or "snake-benchmark"

    total_bots = 0

    for bot in config.bots:
        bot.algorithm = bot.algorithm.strip()
        bot.entrypoint = bot.entrypoint.strip()
        if bot.name_prefix is not None:
            bot.name_prefix = bot.name_prefix.strip() or None
        if not bot.algorithm.strip():
            raise ValueError("bot algorithm must be non-empty")
        if not bot.entrypoint.strip():
            raise ValueError("bot entrypoint must be non-empty")
        if bot.count <= 0:
            raise ValueError(f"bot count must be positive for algorithm {bot.algorithm!r}")
        total_bots += bot.count

    if total_bots > MAX_BENCHMARK_BOTS:
        raise ValueError(
            f"phase-1 benchmark runner supports at most {MAX_BENCHMARK_BOTS} bots to keep benchmark runs classroom-sized and easy to inspect"
        )