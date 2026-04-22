# SnakeRoyale — 运维指南

当前版本：`0.4.0`

## 概览

这份文档负责部署方式、运行参数、弱网实验和测试入口。

## 1. 部署方式

### Docker Compose

推荐默认栈：

```bash
docker compose up -d
```

会启动：
- `server` — 游戏服务器，监听 `15000`
- `bot` — 20 个示例 AI 客户端

完整弱网实验栈：

```bash
docker compose -f docker-compose.full.yml up -d
```

还会额外启动：
- `toxiproxy` — 代理管理/API `8474`，代理后的游戏入口 `15001`
- `bot_toxic` — 通过代理接入的示例 bot

浏览器入口：
- `http://localhost:15000/` — 实时 Dashboard
- `http://localhost:15000/docs` — API 文档
- `http://localhost:15000/replay` — benchmark 回放查看页

### 手动部署

```bash
# 启动 server
cd server
pip install -r requirements.txt
python server.py

# 另开终端启动示例 client
cd client
pip install -r requirements.txt
python run_clients.py -n 10
python run_clients.py -n 5 --server http://192.168.1.100:15000
```

## 2. 运行配置

服务端默认读取 `config/server.json`：

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

环境变量仍然可以覆盖配置文件。

常用参数：
- `tick_rate` / `SNAKE_TICK_RATE` — 游戏主循环频率
- `send_timeout_ms` / `SNAKE_SEND_TIMEOUT_MS` — 单次 WebSocket 发送超时
- `disconnect_grace_ms` / `SNAKE_DISCONNECT_GRACE_MS` — 断线保活窗口
- `spectator_reconnect_ms` / `SNAKE_SPECTATOR_RECONNECT_MS` — Dashboard 自动重连间隔
- `max_registered_players` / `SNAKE_MAX_REGISTERED_PLAYERS` — 注册总量上限，`0` 表示关闭
- `max_spectators` / `SNAKE_MAX_SPECTATORS` — 观战上限，`0` 表示关闭

compose 文件已经显式挂载 `config/server.json`，并设置 `SNAKE_SERVER_CONFIG=/app/config/server.json`，所以修改这份文件后，下次容器启动就会生效，不需要重建镜像。

如果要指向自定义配置文件：

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

如果你是直接把文件挂到 `/app/config/server.json`，则无需修改 `SNAKE_SERVER_CONFIG`。

## 3. 弱网实验

弱网实验依赖 `docker-compose.full.yml`。走代理的 bot 连 `http://toxiproxy:15001`，普通 bot 和 Dashboard 仍连 `http://server:15000`。

常用 Toxiproxy 管理 API：

```bash
# 添加 250ms 下行延迟 + 50ms 抖动
curl -X POST http://localhost:8474/proxies/snake_server/toxics \
  -H 'Content-Type: application/json' \
  -d '{"name":"latency_downstream","type":"latency","stream":"downstream","attributes":{"latency":250,"jitter":50}}'

# 100ms 后模拟 reset
curl -X POST http://localhost:8474/proxies/snake_server/toxics \
  -H 'Content-Type: application/json' \
  -d '{"name":"reset_downstream","type":"reset_peer","stream":"downstream","attributes":{"timeout":100}}'

# 下行黑洞，60ms 后断开
curl -X POST http://localhost:8474/proxies/snake_server/toxics \
  -H 'Content-Type: application/json' \
  -d '{"name":"timeout_downstream","type":"timeout","stream":"downstream","attributes":{"timeout":60}}'

# 只允许再通过 512 字节
curl -X POST http://localhost:8474/proxies/snake_server/toxics \
  -H 'Content-Type: application/json' \
  -d '{"name":"limit_downstream","type":"limit_data","stream":"downstream","attributes":{"bytes":512}}'

# 清空 toxics
curl -X POST http://localhost:8474/reset
```

启动弱网 bot：

```bash
docker compose -f docker-compose.full.yml up -d
docker compose -f docker-compose.full.yml up -d bot_toxic
python client.py --server http://localhost:15001 --name LaggyBot
```

验证断线保活时，建议直接看服务端状态接口，而不是代理入口：

```bash
curl http://localhost:15000/status
```

`players_grace_disconnected` 最适合判断代理故障下的连接是否仍在保活窗口内。

## 4. 测试

运行测试：

```bash
python -m pytest tests -v
```

如果还没安装 pytest：

```bash
pip install pytest
```

如果本机没有 Docker，Toxiproxy 相关测试会自动跳过，但核心本地测试仍可正常运行。

测试分层：
- `tests/test_game_logic.py` — 游戏规则和统计口径
- `tests/test_server_e2e.py` — 注册 / WebSocket / 观战 / 重连场景
- `tests/test_toxiproxy_integration.py` — Docker 驱动的弱网端到端覆盖