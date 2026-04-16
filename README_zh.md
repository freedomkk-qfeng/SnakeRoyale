# 🐍 SnakeRoyale · 蛇蛇大逃杀

[English](README.md)

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![AI Coded](https://img.shields.io/badge/AI_Coded-100%25-A855F7?logo=github-copilot&logoColor=white)](https://github.com/features/copilot)

多人在线贪吃蛇对战平台，适用于 AI 编程教学与算法实践。部署服务器，编写 AI 客户端，在对战中学习路径规划、博弈策略等算法。

![Dashboard](docs/screenshot_zh.png)

## 项目结构

```
snake-royale/
├── docker-compose.yml      # 一键拉起服务
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
└── docs/
    ├── API.md              # API 文档 (Markdown, 中文)
    └── API_en.md           # API 文档 (Markdown, English)
```

## 快速开始

### Docker Compose（推荐）

```bash
docker compose up -d
```

启动后：
- **server** — 游戏服务器，监听 `15000` 端口
- **bot** — 20 个示例 AI 客户端自动加入对战

浏览器访问：
- `http://localhost:15000/` — 实时 Dashboard 观战
- `http://localhost:15000/docs` — API 文档

bot 数量可在 `docker-compose.yml` 中修改 `-n` 参数。

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
| Tick 速率 | 10 次/秒 |
| 初始长度 | 3 |
| 死亡条件 | 撞墙 / 撞自己 / 撞别人 / 头对头 |
| 死亡机制 | 蛇身变为食物散落原地，随时间缓慢腐烂 |
| 重生 | 死亡后自动在随机位置重生 |

## 编写你的 AI

### 1. 获取示例客户端 & 文档

- API 文档：`http://<server>:15000/docs`
- 示例客户端下载：`http://<server>:15000/download/client.py`

### 2. 安装依赖 & 运行

```bash
pip install aiohttp
python client.py --server http://<server>:15000 --name "my_snake"
```

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
| `GET /docs` | 完整 API 文档 |

详细协议见 `http://<server>:15000/docs`

## 技术栈

- Python 3.12 + aiohttp
- 纯 WebSocket 通信，无额外依赖
- 单 HTML 文件 Dashboard（Canvas 渲染）

## License

[Apache License 2.0](LICENSE)
