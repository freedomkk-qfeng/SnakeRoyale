# 🐍 SnakeRoyale · 蛇蛇大逃杀

[English](README.md)

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![AI Coded](https://img.shields.io/badge/AI_Coded-100%25-A855F7?logo=github-copilot&logoColor=white)](https://github.com/features/copilot)

多人在线贪吃蛇对战平台，适用于 AI 编程教学与算法实践。部署服务器，编写 AI 客户端，在对战中学习路径规划、博弈策略等算法。

![Dashboard](docs/screenshot_zh.png)

当前版本：`0.3.0`

## 文档总览

从 `0.2.0` 开始，项目文档固定为四个部分：

1. [README](README_zh.md) - 项目介绍、部署方式、运行方式和测试入口。
2. [DESIGN](docs/DESIGN.md) - 架构设计、网络模型和关键取舍。
3. [API](docs/API.md) - 客户端与服务端接口契约。
4. [CHANGELOG](CHANGELOG.md) - 版本演进记录。

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
│   │   └── docs.html       # API 文档页
│   ├── requirements.txt
│   └── Dockerfile
├── client/
│   ├── client.py           # 示例 AI 客户端 (BFS 寻路)
│   ├── run_clients.py      # 批量启动脚本
│   ├── requirements.txt
│   └── Dockerfile
├── docs/
│   ├── API.md              # API 文档 (Markdown, 中文)
│   ├── API_en.md           # API 文档 (Markdown, English)
│   ├── DESIGN.md           # 设计说明（中文）
│   └── DESIGN_en.md        # Design doc (English)
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

如果课堂网络环境一般，建议直接在 `config/server.json` 里调节服务默认参数：

```json
{
    "tick_rate": 10,
    "send_timeout_ms": 80,
    "disconnect_grace_ms": 3000,
    "spectator_reconnect_ms": 2000,
    "max_registered_players": 200,
    "max_spectators": 50
}
```

如果需要临时覆盖，环境变量仍然生效，而且优先级高于配置文件。compose 文件里现在显式写了 `SNAKE_SERVER_CONFIG=/app/config/server.json`，并把宿主机上的 `config/server.json` 绑定挂载进去，所以你修改这份文件后，下一次容器启动就会生效，不需要重建镜像。

如果你想强制指定自己的配置文件，可以这样做：

```bash
SNAKE_SERVER_CONFIG=/absolute/path/to/custom-server.json python server/server.py
```

```yaml
services:
    server:
        environment:
            SNAKE_SERVER_CONFIG: /app/config/classroom-a.json
        volumes:
            - ./config/classroom-a.json:/app/config/classroom-a.json:ro
```

如果你只是把自定义配置直接挂载到容器里的 `/app/config/server.json`，那连 `SNAKE_SERVER_CONFIG` 都不用改。

浏览器访问：
- `http://localhost:15000/` — 实时 Dashboard 观战
- `http://localhost:15000/docs` — API 文档

bot 数量可在 `docker-compose.yml` 或 `docker-compose.full.yml` 中修改 `-n` 参数。

### 手动部署

```bash
# 启动服务器
cd server
pip install -r requirements.txt
python server.py

# 启动示例客户端（另开终端）
cd client
pip install -r requirements.txt
python run_clients.py -n 10                # 启动 10 个 AI
python run_clients.py -n 5 --server http://192.168.1.100:15000  # 指定服务器
```

## 游戏规则

| 项目 | 值 |
|------|-----|
| 场地大小 | 100 × 100 |
| Tick 速率 | 可通过 `config/server.json` 或 `SNAKE_TICK_RATE` 覆盖，默认 10 次/秒 |
| 初始长度 | 3 |
| 死亡条件 | 撞墙 / 撞自己 / 撞别人 / 头对头 |
| 死亡机制 | 蛇身变为食物散落原地，随时间缓慢腐烂 |
| 重生 | 死亡后自动在随机位置重生 |

## 服务调优

服务端会先从 `config/server.json` 读取默认配置；如果同时设置了环境变量，则环境变量优先。

- `tick_rate` / `SNAKE_TICK_RATE`：服务端 tick 频率。课堂无线网络或投屏环境卡顿时，优先把这个值往下调。
- `send_timeout_ms` / `SNAKE_SEND_TIMEOUT_MS`：单次 WebSocket 发送超时。每个连接有独立 sender task，超时只影响该连接自己。
- `disconnect_grace_ms` / `SNAKE_DISCONNECT_GRACE_MS`：断线保活窗口。连接断开后，蛇会按最后方向继续运行，在这个时间内用同一个 key 重连可以续上原来的蛇。
- `spectator_reconnect_ms` / `SNAKE_SPECTATOR_RECONNECT_MS`：Dashboard 观战端断线后的自动重连间隔。
- `max_registered_players` / `SNAKE_MAX_REGISTERED_PLAYERS`：总注册数上限。设为 `0` 表示关闭上限。
- `max_spectators` / `SNAKE_MAX_SPECTATORS`：观战连接数上限。设为 `0` 表示关闭上限。
- Dashboard 新增“生存统计”页签，展示每个 bot 的平均存活长度和平均存活时间，比单次历史最长更适合课堂观察。

当前服务端的广播机制已经改成“主 game loop 只产出最新状态，每个客户端/观战端各自异步发送”，所以某个慢连接不会再阻塞其他连接的发送链路。

## 弱网实验

弱网实验环境放在 `docker-compose.full.yml` 里。需要模拟弱网络的 bot 连 `http://toxiproxy:15001`，普通 bot 和 Dashboard 还是连 `http://server:15000`。

常用管理 API 示例：

```bash
# 给下行加 250ms 延迟和 50ms 抖动
curl -X POST http://localhost:8474/proxies/snake_server/toxics \
    -H 'Content-Type: application/json' \
    -d '{"name":"latency_downstream","type":"latency","stream":"downstream","attributes":{"latency":250,"jitter":50}}'

# 100ms 后模拟连接被 reset
curl -X POST http://localhost:8474/proxies/snake_server/toxics \
    -H 'Content-Type: application/json' \
    -d '{"name":"reset_downstream","type":"reset_peer","stream":"downstream","attributes":{"timeout":100}}'

# 让下行数据黑洞化，并在 60ms 后断开连接
curl -X POST http://localhost:8474/proxies/snake_server/toxics \
    -H 'Content-Type: application/json' \
    -d '{"name":"timeout_downstream","type":"timeout","stream":"downstream","attributes":{"timeout":60}}'

# 只允许下行再发 512 字节，超出后断开
curl -X POST http://localhost:8474/proxies/snake_server/toxics \
    -H 'Content-Type: application/json' \
    -d '{"name":"limit_downstream","type":"limit_data","stream":"downstream","attributes":{"bytes":512}}'

# 清空所有 toxics
curl -X POST http://localhost:8474/reset
```

如果要额外拉起一组走弱网代理的示例 bot：

```bash
docker compose -f docker-compose.full.yml up -d

# 或者只启动完整栈里的弱网 bot 组
docker compose -f docker-compose.full.yml up -d bot_toxic

# 或者直接让你自己的 client 走代理入口
python client.py --server http://localhost:15001 --name LaggyBot
```

自动化弱网验证同样走 Docker + Toxiproxy 的真实链路，覆盖了延迟、上行控制滞后、观战链路隔离、reset 后恢复、timeout 黑洞断流以及 limit-data 预算耗尽断流。

验证断线保活时，建议看服务端直连的状态接口，而不是代理入口：

```bash
curl http://localhost:15000/status
```

其中 `players_grace_disconnected` 最适合拿来判断代理故障下的连接是否仍在保活窗口内。

## 编写你的 AI

### 1. 获取示例客户端 & 文档

- API 文档：`http://<server>:15000/docs`
- 示例客户端下载：`http://<server>:15000/download/client.py`

### 2. 安装依赖 & 运行

```bash
pip install aiohttp
python client.py --server http://<server>:15000 --name "my_snake"
python client.py --server http://<server>:15000 --name "my_snake" --reconnect-delay-ms 1500
```

示例客户端的断线重连间隔也支持配置：
- CLI 参数：`--reconnect-delay-ms`
- 环境变量：`SNAKE_CLIENT_RECONNECT_DELAY_MS`

如果注册时遇到临时重名，示例客户端现在会自动追加后缀重试，而不是只尝试一次。

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
| `GET /docs` | 完整 API 文档 |

详细协议见 `http://<server>:15000/docs`

## 技术栈

- Python 3.12 + aiohttp
- 纯 WebSocket 通信，无额外依赖
- 单 HTML 文件 Dashboard（Canvas 渲染）

## 测试

```bash
python -m pytest tests -v
```

如果你的环境里还没有 pytest，请先执行 `pip install pytest`。

如果本机没有可用 Docker，Toxiproxy 相关测试会自动跳过，核心本地测试仍然可以正常跑。

测试套件包含三层：
- `tests/test_game_logic.py`：核心游戏逻辑与统计口径
- `tests/test_server_e2e.py`：注册、WebSocket、观战、断线保活、恢复连接等端到端场景
- `tests/test_toxiproxy_integration.py`：通过真实 Toxiproxy 容器执行的弱网端到端场景

## License

[Apache License 2.0](LICENSE)
