# SnakeRoyale — API 文档

当前版本：`0.3.0`

## 概述

SnakeRoyale 是一个多人在线贪吃蛇对战平台。服务器运行游戏引擎，客户端通过网络连接控制各自的蛇。

- **服务器地址**: `http://<host>:15000`
- **通信协议**: HTTP (注册) + WebSocket (游戏)
- **数据格式**: JSON
- **Dashboard**: `http://<host>:15000/`
- **本文档**: `http://<host>:15000/docs`

## 游戏规则

| 项目 | 值 |
|------|-----|
| 场地大小 | 100 × 100 格子 |
| 坐标系 | (0,0) 为左上角，x 向右增长，y 向下增长 |
| Tick 速率 | 可通过 `config/server.json` 或 `SNAKE_TICK_RATE` 覆盖，默认 10 次/秒 |
| 初始蛇长度 | 3 |
| 死亡条件 | 撞墙 / 撞自己 / 撞到别的蛇 / 头对头碰撞 |
| 死亡后 | 自动在随机位置重生，长度恢复为 3，分数清零 |
| 死亡掉落 | 蛇死亡后身体变成等量食物散落在原位，随时间缓慢腐烂 |
| 食物 | 吃到 +1 长度 +1 分 |

---

## 1. 注册

### `POST /register`

注册一个玩家名字，获取游戏密钥。

**Request Body:**
```json
{
  "name": "你的名字"
}
```

**成功响应 (200):**
```json
{
  "key": "a1b2c3d4e5f6g7h8",
  "name": "你的名字"
}
```

**错误响应:**
- `400` — name 为空、超过 20 个字符、或 JSON 格式错误
- `409` — 名字已被占用
- `503` — 已达到注册上限

> ⚠️ 请保存好你的 `key`，后续所有操作都需要它。

---

## 2. 连接游戏

### `WebSocket /ws?key=<你的key>`

用注册时获得的 key 建立 WebSocket 连接。连接成功后，你的蛇会自动在场地上随机出生。

**连接示例 (Python):**
```python
import aiohttp, asyncio

async def main():
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect("http://host:15000/ws?key=你的key") as ws:
            async for msg in ws:
                data = msg.json()
                # 处理消息...

asyncio.run(main())
```

**连接示例 (JavaScript / Node.js):**
```javascript
const WebSocket = require('ws');
const ws = new WebSocket('ws://host:15000/ws?key=你的key');

ws.on('message', (data) => {
    const state = JSON.parse(data);
    // 处理消息...
});
```

### `WebSocket /spectate`

连接 Dashboard 的观战流，不需要鉴权 key。

- 成功时会持续收到与 Dashboard 相同的全量状态快照。
- 如果当前观战连接已达到上限，握手会以 `503` 拒绝。

---

## 3. 消息协议

### 3.1 服务器 → 客户端

#### `welcome` — 连接成功

连接成功后立即收到：

```json
{
  "type": "welcome",
  "you": 1,
  "name": "你的名字",
  "field": {"width": 100, "height": 100},
  "tick_rate": 10,
  "send_timeout_ms": 80,
  "disconnect_grace_ms": 3000,
  "resumed": false
}
```

> `you` 是你的蛇在场上的公开 ID（整数），用来在 `state` 消息的 `snakes` 列表中找到自己。

如果连接意外断开，服务端会保留一小段断线窗口；在 `disconnect_grace_ms` 对应的时间内，用同一个 key 重连时，`resumed` 会是 `true`，表示你接回的是原来的蛇，而不是重新出生。

`welcome` 额外字段：
- `send_timeout_ms` — 当前服务端判定单次发送超时的阈值
- `disconnect_grace_ms` — 当前断线保活窗口，窗口内可用同一个 key 恢复原蛇
- `resumed` — 是否是在断线保活窗口内恢复原连接

#### `state` — 游戏状态 (每 tick 一次)

```json
{
  "type": "state",
  "tick": 1234,
  "you": 1,
  "tick_rate": 10,
  "field": {"width": 100, "height": 100},
  "snakes": [
    {
      "id": 1,
      "name": "玩家名",
      "body": [[10, 5], [9, 5], [8, 5]],
      "direction": "right",
      "alive": true,
      "score": 7,
      "length": 10
    }
  ],
  "foods": [[20, 30], [55, 12]],
  "record": {"name": "最强玩家", "length": 58},
  "performance": [
    {
      "id": 1,
      "name": "Bot_01",
      "alive": true,
      "rounds": 4,
      "completed_rounds": 3,
      "avg_length": 8.75,
      "avg_survival_ticks": 42.5,
      "avg_survival_seconds": 7.08,
      "best_length": 18,
      "current_length": 9
    }
  ]
}
```

**字段说明:**
- `snakes[].id` — 蛇的公开 ID（整数），找到 `id == you` 的蛇就是你自己
- `snakes[].body` — 蛇身坐标数组，`body[0]` 是蛇头
- `snakes[].direction` — 当前移动方向: `"up"` / `"down"` / `"left"` / `"right"`
- `you` — 你的公开 ID（整数），用来在 snakes 列表中找到自己
- `tick_rate` — 当前服务端 tick 配置，客户端可以用它估算每一步的时间预算
- `foods` — 所有食物的坐标 `[x, y]`
- `record` — 历史最长蛇记录：`name` 为玩家名，`length` 为最大长度
- `performance` — Dashboard/运维统计字段，包含每个 bot 的平均存活长度、平均存活时间、样本轮次等聚合信息
- `performance[].rounds` — 已完成生命周期数，加上当前正在进行的一轮（如果 bot 还活着）

#### `death` — 死亡通知

```json
{
  "type": "death",
  "reason": "hit wall"
}
```

可能的死亡原因:
- `"hit wall"` — 撞墙
- `"hit self"` — 撞到自己
- `"hit snake XXX"` — 撞到名为 XXX 的蛇
- `"head-to-head collision"` — 头对头碰撞

#### `respawn` — 重生通知

```json
{
  "type": "respawn"
}
```

死亡后会立即收到此消息，表示你的蛇已经重新出生。下一个 `state` 消息中就能看到新的位置。

### 3.2 客户端 → 服务器

#### `move` — 改变方向

```json
{
  "type": "move",
  "direction": "up"
}
```

- 方向: `"up"` / `"down"` / `"left"` / `"right"`
- 不能 180° 掉头（例如正在向右走，不能直接向左）
- 每个 tick 只会采纳最后一次方向指令
- 不发送则保持当前方向继续前进

---

## 4. 查看排行榜 / 游戏状态

### `GET /status`

查看当前游戏状态和排行榜（HTTP 接口，无需鉴权）。

```json
{
  "version": "0.3.0",
  "tick": 5678,
  "tick_rate": 10,
  "send_timeout_ms": 80,
  "disconnect_grace_ms": 3000,
  "max_registered_players": 200,
  "max_spectators": 50,
  "players_registered": 15,
  "players_connected": 8,
  "players_grace_disconnected": 2,
  "snakes_alive": 8,
  "leaderboard": [
    {"name": "张三", "score": 42, "length": 45},
    {"name": "李四", "score": 35, "length": 38}
  ],
  "performance": [
    {"name": "Bot_01", "avg_length": 8.75, "avg_survival_seconds": 7.08, "rounds": 4}
  ]
}
```

其中 `players_grace_disconnected` 表示当前处于断线保活窗口、尚未被正式移除的玩家数量。

在 Toxiproxy 弱网实验里，这个字段也是验证代理故障是否正确进入/退出断线保活窗口的主要观测点。

- `version` — 当前服务端版本号
- `max_registered_players` — 当前注册上限。`0` 表示不设上限。
- `max_spectators` — 当前观战连接上限。`0` 表示不设上限。

### `GET /api/runtime-config`

返回 Dashboard 使用的运行时配置。

```json
{
  "version": "0.3.0",
  "tick_rate": 10,
  "send_timeout_ms": 80,
  "disconnect_grace_ms": 3000,
  "spectator_reconnect_ms": 2000,
  "max_registered_players": 200,
  "max_spectators": 50
}
```

---

## 5. 快速开始

### 第一步：注册

```bash
curl -X POST http://<host>:15000/register \
  -H "Content-Type: application/json" \
  -d '{"name": "my_snake"}'
```

### 第二步：编写 AI 客户端

你的 AI 需要做的事情很简单：
1. 用上面拿到的 key 连接 WebSocket
2. 每收到一个 `state` 消息，分析当前局面
3. 发送 `move` 消息决定下一步方向

**AI 策略提示:**
- 避开墙壁：检查蛇头离四面墙的距离
- 避开自己和其他蛇：检查四个方向是否有蛇身
- 追逐食物：找到最近的食物，朝它移动
- 高级策略：路径规划（BFS/A*）、预判对手动向、围杀对手等

### 第三步：运行 & 观战

```bash
# 查看排行榜
curl http://<host>:15000/status

# 浏览器打开 Dashboard 观战
# http://<host>:15000/
```

---

## 6. 错误处理

| 场景 | 处理方式 |
|------|---------|
| WebSocket 断开 | 重新连接即可，用同一个 key |
| 发送无效 JSON | 服务器忽略该消息 |
| 发送无效方向 | 服务器忽略该消息 |
| key 无效 | WebSocket 连接被拒绝 (401) |
| 重复连接 | 被拒绝 (409)，先断开旧连接 |
| 达到注册上限 | `POST /register` 返回 503 |
| 达到观战上限 | `WS /spectate` 握手返回 503 |

---

## 7. 示例客户端代码

我们提供了一个使用 BFS 寻路的 Python AI 客户端示例，可直接复制使用：

- **[📄 查看示例代码 (client.py)](/api/client-source)** — 在浏览器中打开，直接复制
- **[⬇ 下载 client.py](/download/client.py)** — 下载文件到本地

依赖安装：`pip install aiohttp`

运行方式：
```bash
python client.py --server http://<host>:15000 --name "你的名字"
```

---

## 附录：坐标示意图

```
(0,0) ──────────────── (99,0)
  │                       │
  │      游 戏 场 地       │
  │                       │
(0,99) ─────────────── (99,99)
```

方向与坐标变化：
- `up`: y - 1
- `down`: y + 1
- `left`: x - 1
- `right`: x + 1
