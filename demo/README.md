# SqurveBridge Interactive Demo

本地交互工作台：React 前端（`demo-app/`）+ Flask API（`demo/api_server.py`）。  
对应 EMNLP System Demonstration 中的可运行系统，不是静态幻灯片。

## 一键启动 / 关闭

在**仓库根目录**执行：

```bash
# 启动 API (:7861) + 前端 (:5173)
./demo/start.sh

# 关闭上述进程并释放端口
./demo/stop.sh
```

启动成功后打开：

- 工作台：<http://127.0.0.1:5173>
- API 健康检查：<http://127.0.0.1:7861/api/health>

运行时 PID / 日志目录：`tmp/demo-runtime/`（已被 gitignore）。

| 文件 | 说明 |
|------|------|
| `api.pid` / `web.pid` | 进程号 |
| `api.log` / `web.log` | 标准输出日志 |
| `demo.env` | 本次启动的 host/port 记录 |

### 可选环境变量

| 变量 | 默认 | 含义 |
|------|------|------|
| `SQURVE_DEMO_API_HOST` | `127.0.0.1` | API 监听地址 |
| `SQURVE_DEMO_API_PORT` | `7861` | API 端口 |
| `SQURVE_DEMO_WEB_HOST` | `127.0.0.1` | Vite 监听地址 |
| `SQURVE_DEMO_WEB_PORT` | `5173` | 前端端口 |

示例：

```bash
SQURVE_DEMO_WEB_PORT=5174 ./demo/start.sh
```

## 前置依赖

1. 仓库根目录已有可用的 Python 虚拟环境 `.venv/`（含 demo API 依赖）
2. 已安装 Node.js / npm
3. 首次启动若缺少 `demo-app/node_modules`，脚本会自动执行 `npm ci`
4. LLM 凭据：复制 `.env.example` → `.env`，或在页面右上角 **Configure LLM** 配置

```bash
# 若尚未创建虚拟环境，按仓库主依赖安装后再装 demo 额外包
python3 -m venv .venv
.venv/bin/pip install -r demo/requirements.txt
```

## 页面导览

| 导航 | 作用 |
|------|------|
| **01 SQL Studio** | 选库、配置 Actor 工作流、生成/执行 SQL；method×dataset 连线与 Agent Harness |
| **02 Experiment Board** | 同一 dataset 上多方法对比（雷达、Formal tables、错误/特征、成本） |
| **03 Archive** | 浏览 `artifacts/` 与 `tmp/demo-runs/` 中的 score bundle 与报告 |

## 手动启动（调试用）

```bash
# Terminal A
.venv/bin/python demo/api_server.py --host 127.0.0.1 --port 7861

# Terminal B
cd demo-app && npm run dev
```

Vite 将 `/api` 代理到 `http://127.0.0.1:7861`。

## 可选 Gradio UI

旧版 Gradio 界面仍可单独启动（默认 `:7860`），与上述 React 工作台无关：

```bash
.venv/bin/python demo/gradio_demo.py
```

详见同目录历史说明；**EMNLP demo 录制与审稿请使用 React 工作台**。

## 常见问题

**端口占用**

```bash
./demo/stop.sh
# 或查看占用
lsof -nP -iTCP:7861 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

**前端 Bad Gateway**

通常是 API 未起来。查看 `tmp/demo-runtime/api.log`，确认 `/api/health` 可访问后再刷新页面。

**重复启动**

`start.sh` 若检测到已有 PID 或端口占用会直接退出，先 `./demo/stop.sh`。

## 录制 / 投稿注意

- 投稿 live demo 需提供**可访问的安装包或托管链接**；本地 `localhost` 不能当作公开 live demo URL。
- 视频分镜见 `论文/paper/support/EMNLP2026_DEMO_VIDEO_SCRIPT.md`。
