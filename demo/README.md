# SqurveBridge Interactive Demo

本地交互工作台：React 前端（`demo-app/`）+ Flask API（`demo/api_server.py`）+ 内嵌 Pi Agent（`pi/`）。
它用于运行 Text-to-SQL 工作流、查看实验结果和检查持久化证据。

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

运行时 PID / 日志目录：`workspace/sessions/runtime/`（已被 gitignore；可用 `SQURVE_WORKSPACE_DIR` 覆盖）。

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
| `PI_AGENT_PROVIDER` | 跟随 `SQURVE_LLM_PROVIDER` | Pi 使用的模型服务 |
| `PI_AGENT_MODEL` | 跟随 `SQURVE_LLM_MODEL` | Pi 使用的模型 |

示例：

```bash
SQURVE_DEMO_WEB_PORT=5174 ./demo/start.sh
```

## 前置依赖

1. 仓库根目录已有可用的 Python 虚拟环境 `.venv/`（含 demo API 依赖）
2. 已安装 Node.js 22.19+ / npm
3. 首次启动会按需构建 `pi/`，并在缺少 `demo-app/node_modules` 时执行 `npm ci`
4. 本地 LLM 凭据：复制 `.env.example` → `.env`，或在页面中配置 provider

```bash
# 若尚未创建虚拟环境，按仓库主依赖安装后再装 demo 额外包
python3 -m venv .venv
.venv/bin/pip install -r demo/requirements.txt
```

## 页面导览

| 导航 | 作用 |
|------|------|
| **01 SQL Studio** | 选择 method/benchmark、配置 Actor 工作流并生成与执行 SQL |
| **02 Experiment Board** | 同一 dataset 上多方法对比（雷达、Formal tables、错误/特征、成本） |
| **03 Archive** | 浏览 `workspace/artifacts/` 与 `workspace/sessions/evaluations/` 中的 score bundle 与报告 |

## Hugging Face Space 凭据

公开 Space 不配置维护者共享模型 Key。每位访问者分别使用两个入口：

- **Configure SQL API**：配置 Squrve SQL 生成所用的 provider、model 和 Key；
  凭据只保存在当前浏览器会话对应的服务端内存中，空闲最多 30 分钟。
- **Login to Pi**：直接使用 Pi 原生 provider 登录与模型选择；凭据仅存在于该
  Pi 子进程内，结束 Agent session 即清除，与 SQL Key 完全分离。

凭据不会写入浏览器存储、`.env`、文件、日志或 API 响应。页面刷新、会话过期或
Space 重启后可能需要重新输入。公开演示建议使用限额、可撤销的临时 Key；托管 Pi
始终使用 `hosted-readonly` 工具配置。

## 手动启动（调试用）

```bash
# Terminal A
.venv/bin/python demo/api_server.py --host 127.0.0.1 --port 7861

# Terminal B
cd demo-app && npm run dev
```

Vite 将 `/api` 代理到 `http://127.0.0.1:7861`。

## 常见问题

**端口占用**

```bash
./demo/stop.sh
# 或查看占用
lsof -nP -iTCP:7861 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

**前端 Bad Gateway**

通常是 API 未起来。查看 `workspace/sessions/runtime/api.log`，确认 `/api/health` 可访问后再刷新页面。

**重复启动**

`start.sh` 若检测到已有 PID 或端口占用会直接退出，先 `./demo/stop.sh`。

## 安全边界

API 默认只监听 `127.0.0.1`。本地 Pi 会话可使用读写和命令工具，因此不应把本地服务暴露到不受信任的网络。Hugging Face 部署自动切换为 `hosted-readonly`，只向 Pi 开放 `read`、`grep`、`find` 和 `ls`。
