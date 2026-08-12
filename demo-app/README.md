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

主界面是「五步流程 + 右侧常驻 Pi Agent」的分栏工作台：

1. **Studio（工作室）**：浏览已集成的方法与数据库 flashcard 目录
2. **Compose（编排）**：在 Method × Database 连线矩阵中选边，查看每对连接的 Actor 工作流
3. **Query（查询）**：交互式 NL→SQL 工作台——左侧 Schema 树（表/列/主外键、搜索、SQL 命中高亮），右侧「问题 → 管线阶段 → SQL 编辑器（CodeMirror，schema 补全）→ 结果表（排序/复制/CSV 导出）」纵向流；支持 direct 生成器与 workflow 多 Actor 两种模式，可继承 Compose 选中的管线
4. **Run（运行）**：设置采样参数，启动/暂停/恢复 config 评估任务，查看进度与产物
5. **History（历史）**：浏览归档 run，展开图表对比

右侧 **Pi Agent** 与 Query 工作台双向联动：Pi 回答中的 ```sql 代码块可一键「送入查询工作台」；工作台的查询上下文（问题、SQL、阶段耗时、错误）可一键「让 Pi 分析」。

LLM 凭据可在顶栏 **Configure LLM** 写入仓库根目录 `.env`（不会回显密钥）。
