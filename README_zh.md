# 🐍 SnakeRoyale · 蛇蛇大逃杀

[English](README.md)

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![AI Coded](https://img.shields.io/badge/AI_Coded-100%25-A855F7?logo=github-copilot&logoColor=white)](https://github.com/features/copilot)

多人在线贪吃蛇对战平台，适用于 AI 编程教学与算法实践。部署服务器，编写 AI 客户端，在对战中学习路径规划、博弈策略等算法。

![Dashboard](docs/screenshot_zh.png)

当前版本：`0.4.0`

## 文档总览

核心文档：

1. [README](README_zh.md) - 项目概览和入口。
2. [DESIGN](docs/DESIGN.md) - 架构设计、网络模型和关键取舍。
3. [API](docs/API.md) - 客户端与服务端接口契约。
4. [CHANGELOG](CHANGELOG.md) - 版本演进记录。

补充指南：

1. [运维指南](docs/OPERATIONS.md) - 部署、配置、弱网实验和测试。
2. [Benchmark 指南](docs/BENCHMARK.md) - benchmark 执行器、配置结构、产物和回放流程。

## 项目结构

```
snake-royale/
├── docker-compose.yml      # 默认栈：server + bot
├── docker-compose.full.yml # 完整栈：server + bot + toxiproxy + bot_toxic
├── CHANGELOG.md            # 版本变更记录
├── config/
│   ├── server.json         # 服务端运行默认配置
│   └── toxiproxy.json      # Toxiproxy 启动配置
├── server/
│   ├── server.py           # aiohttp 服务器 (HTTP + WebSocket)
│   ├── game.py             # 游戏引擎
│   ├── static/
│   │   ├── index.html      # 实时 Dashboard (观战 + 排行榜)
│   │   ├── docs.html       # API 文档页
│   │   └── replay.html     # benchmark 回放查看页
│   ├── requirements.txt
│   └── Dockerfile
├── client/
│   ├── client.py           # 示例 AI 客户端 (BFS 寻路)
│   ├── run_clients.py      # 批量启动脚本
│   ├── requirements.txt
│   └── Dockerfile
├── benchmark/
│   ├── config.py           # Benchmark 配置结构
│   ├── report.py           # 汇总报告生成
│   ├── runner.py           # 固定时长 benchmark 执行器
│   └── examples/
│       └── mixed_room.json # 混合 bot benchmark 示例
├── docs/
│   ├── API.md              # API 文档 (Markdown, 中文)
│   ├── API_en.md           # API 文档 (Markdown, English)
│   ├── BENCHMARK.md        # Benchmark 指南（中文）
│   ├── BENCHMARK_en.md     # Benchmark guide (English)
│   ├── DESIGN.md           # 设计说明（中文）
│   ├── DESIGN_en.md        # Design doc (English)
│   ├── OPERATIONS.md       # 运维指南（中文）
│   └── OPERATIONS_en.md    # Operations guide (English)
├── tests/
│   ├── test_client_retry.py
│   ├── test_game_logic.py
│   ├── test_server_e2e.py
│   ├── test_toxiproxy_integration.py
│   └── test_support.py
└── README.md               # English entry documentation
```

## 快速开始

### Docker Compose（推荐）

```bash
docker compose up -d
```

默认栈会启动：
- **server** — 游戏服务器，监听 `15000` 端口
- **bot** — 20 个示例 AI 客户端自动加入对战

如果要启动完整弱网实验环境：

```bash
docker compose -f docker-compose.full.yml up -d
```

完整栈还会额外启动：
- **toxiproxy** — 可选 TCP 代理，暴露 `8474` / `15001`
- **bot_toxic** — 通过代理接入的弱网示例 bot

浏览器访问：
- `http://localhost:15000/` — 实时 Dashboard 观战
- `http://localhost:15000/docs` — API 文档
- `http://localhost:15000/replay` — benchmark 回放查看页

更详细的部署、配置、弱网实验和测试入口见 [docs/OPERATIONS.md](docs/OPERATIONS.md)。

## 游戏规则

| 项目 | 值 |
|------|-----|
| 场地大小 | 100 × 100 |
| Tick 速率 | 可通过 `config/server.json` 或 `SNAKE_TICK_RATE` 覆盖，默认 10 次/秒 |
| 初始长度 | 3 |
| 死亡条件 | 撞墙 / 撞自己 / 撞别人 / 头对头 |
| 死亡机制 | 蛇身变为食物散落原地，随时间缓慢腐烂 |
| 重生 | 死亡后自动在随机位置重生 |

## 指南入口

- [docs/OPERATIONS.md](docs/OPERATIONS.md) - 部署、配置、弱网实验和测试
- [docs/BENCHMARK.md](docs/BENCHMARK.md) - benchmark 执行器、配置结构、产物和回放流程

## 编写你的 AI

### 1. 获取示例 Client SDK & 文档

- API 文档：`http://<server>:15000/docs`
- 下载 client SDK 压缩包：`http://<server>:15000/download/client-sdk.zip`
- 查看默认 BFS 客户端源码：`http://<server>:15000/api/client-source`

### 2. 安装依赖 & 运行

```bash
pip install aiohttp
python client.py --server http://<server>:15000 --name "my_snake"
python random_client.py --server http://<server>:15000 --name "my_random_snake"
python client.py --server http://<server>:15000 --name "my_snake" --reconnect-delay-ms 1500
```

SDK 已经内置了注册、重连和 WebSocket 通信处理，内置 BFS / random 两个客户端只关注决策逻辑。
示例客户端的断线重连间隔也支持配置：
- CLI 参数：`--reconnect-delay-ms`
- 环境变量：`SNAKE_CLIENT_RECONNECT_DELAY_MS`

如果注册时遇到临时重名，SDK 会自动追加后缀重试，而不是只尝试一次。

### 3. 开发自己的 AI

参考示例客户端和 API 文档，实现你自己的决策逻辑。每个 tick 服务器推送完整游戏状态，你的客户端返回一个方向（`up` / `down` / `left` / `right`）。

**策略方向：**
- 入门：避开墙壁和蛇身，随机选安全方向
- 进阶：BFS / A* 寻找最近食物
- 高级：空间评估（flood fill）、预判对手、围杀策略

## API 概览

| 接口 | 说明 |
|------|------|
| `POST /register` | 注册玩家，获取 key |
| `WS /ws?key=xxx` | WebSocket 游戏连接 |
| `GET /status` | 排行榜和游戏状态 |
| `WS /spectate` | Dashboard 观战连接 |
| `GET /api/runtime-config` | Dashboard 运行时配置 |
| `GET /replay` | benchmark 回放查看页 |
| `GET /docs` | 完整 API 文档 |

详细协议见 `http://<server>:15000/docs`

## 技术栈

- Python 3.12 + aiohttp
- 纯 WebSocket 通信，无额外依赖
- 单 HTML 文件 Dashboard（Canvas 渲染）

测试说明见 [docs/OPERATIONS.md](docs/OPERATIONS.md)。

## License

[Apache License 2.0](LICENSE)
