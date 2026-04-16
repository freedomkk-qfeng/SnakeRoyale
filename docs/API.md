# SnakeRoyale — API 文档

## 概述

SnakeRoyale 是一个多人在线贪吃蛇对战平台。服务器运行游戏引擎，客户端通过网络连接控制各自的蛇。

- **服务器地址**: `http://<host>:15000`
- **通信协议**: HTTP (注册) + WebSocket (游戏)
- **数据格式**: JSON

## 游戏规则

| 项目 | 值 |
|------|-----|
| 场地大小 | 100 × 100 格子 |
| 坐标系 | (0,0) 为左上角，x 向右增长，y 向下增长 |
| Tick 速率 | 10 次/秒 |
| 初始蛇长度 | 3 |
| 死亡条件 | 撞墙 / 撞自己 / 撞到别的蛇 / 头对头碰撞 |
| 死亡后 | 自动在随机位置重生，分数清零 |
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
- `400` — name 为空或 JSON 格式错误
- `409` — 名字已被占用

> ⚠️ 请保存好你的 `key`，后续所有操作都需要它。

---

## 2. 连接游戏

### `WebSocket /ws?key=<你的key>`

用注册时获得的 key 建立 WebSocket 连接。连接成功后，你的蛇会自动在场地上随机出生。

**连接示例 (Python):**
```python
import aiohttp

async with aiohttp.ClientSession() as session:
    async with session.ws_connect("http://host:15000/ws?key=你的key") as ws:
        async for msg in ws:
            data = msg.json()
            # 处理消息...
```

---

## 3. 消息协议

### 3.1 服务器 → 客户端

#### `welcome` — 连接成功

连接成功后立即收到：

```json
{
  "type": "welcome",
  "you": "你的key",
  "name": "你的名字",
  "field": {"width": 100, "height": 100},
  "tick_rate": 10
}
```

#### `state` — 游戏状态 (每 tick 一次)

```json
{
  "type": "state",
  "tick": 1234,
  "you": "你的key",
  "field": {"width": 100, "height": 100},
  "snakes": [
    {
      "id": "player_key",
      "name": "玩家名",
      "body": [[10, 5], [9, 5], [8, 5]],
      "direction": "right",
      "alive": true,
      "score": 7,
      "length": 10
    }
  ],
  "foods": [[20, 30], [55, 12], ...]
}
```

**字段说明:**
- `snakes[].body` — 蛇身坐标数组，`body[0]` 是蛇头
- `snakes[].direction` — 当前移动方向: `"up"` / `"down"` / `"left"` / `"right"`
- `you` — 你的 key，用来在 snakes 列表中找到自己
- `foods` — 所有食物的坐标

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

## 4. 查看排行榜

### `GET /status`

查看当前游戏状态和排行榜（HTTP 接口，无需鉴权）。

**响应:**
```json
{
  "tick": 5678,
  "players_registered": 15,
  "players_connected": 8,
  "snakes_alive": 8,
  "leaderboard": [
    {"name": "张三", "score": 42, "length": 45},
    {"name": "李四", "score": 35, "length": 38}
  ]
}
```

---

## 5. 快速开始

### 第一步：注册
```bash
curl -X POST http://localhost:15000/register \
  -H "Content-Type: application/json" \
  -d '{"name": "my_snake"}'
```

### 第二步：编写 AI 客户端

你的 AI 需要做的事情很简单：
1. 连接 WebSocket
2. 每收到一个 `state` 消息，分析当前局面
3. 发送 `move` 消息决定下一步方向

**AI 策略提示:**
- 避开墙壁：检查蛇头离四面墙的距离
- 避开自己和其他蛇：检查四个方向是否有蛇身
- 追逐食物：找到最近的食物，朝它移动
- 高级策略：路径规划（BFS/A*）、预判对手动向等

### 第三步：运行测试
```bash
# 查看排行榜
curl http://localhost:15000/status
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
