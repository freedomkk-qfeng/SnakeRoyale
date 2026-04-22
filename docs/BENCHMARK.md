# SnakeRoyale — Benchmark 指南

当前版本：`0.4.0`

## 概览

0.4.0 增加了本地 benchmark 工作流，用来做可脚本化的混合 bot 对比。

当前能力：
- 启动一个固定时长的房间，并混跑多组 bot；等 roster 就绪后，再切到一个干净的 benchmark 计时起点。
- 输出权威回放 `replay.jsonl`，从正式 benchmark 计时窗口开始逐 tick 记录，保存与服务端 live 广播一致的 tick 状态快照，并附带唯一 `benchmark_run_id` 及该 tick 的后续回放事件。
- 生成 `summary.json` 和 `summary.md`，按 bot 和按算法都基于服务端原始统计做精确聚合，并复用同一个 `benchmark_run_id`。
- 如果某个配置里的 bot 根本没成功加入房间，benchmark 会直接失败。
- 如果某个 bot 在 benchmark 还没跑完前就退出，或者虽然进程还活着但已经掉出房间，benchmark 也会直接失败。
- phase-1 当前限制最多 `20` 个 benchmark bot。

## 1. 运行 Benchmark

示例命令：

```bash
python benchmark/runner.py \
  --config benchmark/examples/mixed_room.json \
  --output /tmp/snake-benchmark-demo
```

## 2. 配置结构

示例配置：

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

顶层字段：
- `benchmark_name` — 产物和回放页里使用的名称
- `duration_seconds` — 正式 benchmark 的计时长度
- `server_env` — 只对当前 run 生效的临时 server 覆盖参数
- `bots` — 要启动的 bot 组

每个 bot 组支持：
- `algorithm` — summary 里使用的算法标签
- `entrypoint` — 启动脚本路径
- `count` — 该组实例数量
- `name_prefix` — 可选的 bot 名字前缀
- `extra_args` — 启动 bot 时追加的 CLI 参数
- `env` — 可选的每组环境变量

## 3. 输出产物

输出目录会包含：
- `replay.jsonl` — metadata + 每个 benchmark tick 与 live 广播一致的状态快照，附带 `benchmark_run_id` 和该 tick 的后续回放事件
- `summary.json` — 机器可读结果，包含 `benchmark_run_id`
- `summary.md` — 人类可读摘要
- `roster.json` — 解析后的参赛 bot、算法标签和入口映射

## 4. 回放查看页

如果需要本地查看回放页，先启动 server UI：

```bash
python server/server.py
```

然后打开 `http://localhost:15000/replay`，上传 `replay.jsonl`。

如果同时上传 `summary.json`，页面会展示算法赢家和聚合统计卡片；如果 `benchmark_run_id` 或核心 benchmark 元数据不匹配，则会拒绝叠加。

## 5. 说明与限制

- 当前 benchmark 工作流是本地、单次 run 导向的。
- 这些产物面向分析和回放，不面向并发 benchmark 编排。
- phase 1 故意把 benchmark 房间限制在 `20` 个 bot 以内，方便课堂观察和讲解。