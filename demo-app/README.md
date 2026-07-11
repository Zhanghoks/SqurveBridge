# SqurveBridge · demo-app

React/Vite 前端，配合 `demo/api_server.py` 使用。

## 推荐启动方式

在仓库根目录：

```bash
./demo/start.sh    # 同时拉起 API + 本前端
./demo/stop.sh     # 关闭
```

打开 <http://127.0.0.1:5173>。完整说明见 [`../demo/README.md`](../demo/README.md)。

## 仅前端开发

```bash
# 需另开终端先启动 API
../.venv/bin/python ../demo/api_server.py

npm ci          # 首次
npm run dev     # http://127.0.0.1:5173 ，/api → :7861
```

## 功能概览

- **SQL Studio**：选择 method/benchmark、配置 Actor 工作流、生成并执行 SQL
- **Experiment Board**：多方法同协议对比与 Formal tables
- **Archive**：阅读 `artifacts/` / `tmp/demo-runs/` 产物

LLM 凭据可在顶栏 **Configure LLM** 写入仓库根目录 `.env`（不会回显密钥）。
