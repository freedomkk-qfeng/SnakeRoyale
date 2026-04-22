from collections import defaultdict


def _format_metric(value: float) -> str:
    return f"{value:.2f}"


def build_summary(*, per_bot: list[dict], duration_seconds: float, replay_file: str, benchmark_name: str, benchmark_run_id: str, start_tick: int, tick: int, tick_rate: int, version: str) -> tuple[dict, str]:
    per_bot.sort(key=lambda item: (-item["avg_survival_seconds"], -item["avg_length"], item["name"]))

    grouped: dict[str, dict] = defaultdict(lambda: {
        "bot_instances": 0,
        "rounds": 0,
        "total_life_ticks": 0.0,
        "total_length_accumulator": 0.0,
        "best_length": 0,
    })

    for item in per_bot:
        group = grouped[item["algorithm"]]
        group["bot_instances"] += 1
        group["rounds"] += item["rounds"]
        group["total_life_ticks"] += item["total_life_ticks"]
        group["total_length_accumulator"] += item["total_length_accumulator"]
        group["best_length"] = max(group["best_length"], item["best_length"])

    per_algorithm: list[dict] = []
    for algorithm, item in grouped.items():
        avg_survival_ticks = item["total_life_ticks"] / item["rounds"] if item["rounds"] else 0.0
        avg_length = item["total_length_accumulator"] / item["total_life_ticks"] if item["total_life_ticks"] else 0.0
        per_algorithm.append({
            "algorithm": algorithm,
            "bot_instances": item["bot_instances"],
            "rounds": item["rounds"],
            "avg_survival_ticks": avg_survival_ticks,
            "avg_survival_seconds": avg_survival_ticks / tick_rate,
            "avg_length": avg_length,
            "best_length": item["best_length"],
        })

    per_algorithm.sort(key=lambda item: (-item["avg_survival_seconds"], -item["avg_length"], item["algorithm"]))

    summary = {
        "benchmark_name": benchmark_name,
        "benchmark_run_id": benchmark_run_id,
        "duration_seconds": duration_seconds,
        "start_tick": start_tick,
        "tick": tick,
        "tick_rate": tick_rate,
        "version": version,
        "replay_file": replay_file,
        "per_bot": per_bot,
        "per_algorithm": per_algorithm,
        "winners": {
            "bot_by_avg_survival_seconds": per_bot[0] if per_bot else None,
            "bot_by_avg_length": max(per_bot, key=lambda item: (item["avg_length"], item["avg_survival_seconds"], item["name"])) if per_bot else None,
            "algorithm_by_avg_survival_seconds": per_algorithm[0] if per_algorithm else None,
            "algorithm_by_avg_length": max(per_algorithm, key=lambda item: (item["avg_length"], item["avg_survival_seconds"], item["algorithm"])) if per_algorithm else None,
        },
    }
    return summary, render_summary_markdown(summary)


def render_summary_markdown(summary: dict) -> str:
    lines = [
        f"# {summary['benchmark_name']}",
        "",
        f"- Version: {summary['version']}",
        f"- Run ID: {summary['benchmark_run_id']}",
        f"- Duration: {summary['duration_seconds']} seconds",
        f"- Tick rate: {summary['tick_rate']}",
        f"- Start tick: {summary['start_tick']}",
        f"- Final tick: {summary['tick']}",
        f"- Replay: {summary['replay_file']}",
        "",
    ]

    winners = summary["winners"]
    if winners["bot_by_avg_survival_seconds"]:
        lines.extend([
            "## Winners",
            "",
            f"- Longest average survival bot: {winners['bot_by_avg_survival_seconds']['name']} ({_format_metric(winners['bot_by_avg_survival_seconds']['avg_survival_seconds'])}s)",
            f"- Longest average survival algorithm: {winners['algorithm_by_avg_survival_seconds']['algorithm']} ({_format_metric(winners['algorithm_by_avg_survival_seconds']['avg_survival_seconds'])}s)",
            f"- Highest average length bot: {winners['bot_by_avg_length']['name']} ({_format_metric(winners['bot_by_avg_length']['avg_length'])})",
            f"- Highest average length algorithm: {winners['algorithm_by_avg_length']['algorithm']} ({_format_metric(winners['algorithm_by_avg_length']['avg_length'])})",
            "",
        ])

    lines.extend([
        "## Per Algorithm",
        "",
        "| Algorithm | Bots | Rounds | Avg Survival (s) | Avg Length | Best Length |",
        "|-----------|------|--------|------------------|------------|-------------|",
    ])
    for item in summary["per_algorithm"]:
        lines.append(
            f"| {item['algorithm']} | {item['bot_instances']} | {item['rounds']} | {_format_metric(item['avg_survival_seconds'])} | {_format_metric(item['avg_length'])} | {item['best_length']} |"
        )

    lines.extend([
        "",
        "## Per Bot",
        "",
        "| Bot | Algorithm | Rounds | Avg Survival (s) | Avg Length | Best Length |",
        "|-----|-----------|--------|------------------|------------|-------------|",
    ])
    for item in summary["per_bot"]:
        lines.append(
            f"| {item['name']} | {item['algorithm']} | {item['rounds']} | {_format_metric(item['avg_survival_seconds'])} | {_format_metric(item['avg_length'])} | {item['best_length']} |"
        )

    lines.append("")
    return "\n".join(lines)