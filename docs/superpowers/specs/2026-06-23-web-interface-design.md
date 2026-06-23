# MyAgent Web 端设计文档

**日期**: 2026-06-23  
**状态**: ✅ 已确认

## 目标

在现有 CLI 终端版基础上，增加 Web 网页端。用户通过网页对话提交仿真需求，后端执行完整的 Abaqus 仿真流水线，生成 HTML 报告后提供下载链接。现有 CLI 端零改动、零影响。

## 技术选型

| 决策项 | 选择 | 理由 |
|--------|------|------|
| Web 框架 | FastAPI | 内置异步支持、自动生成 API 文档、适合后台任务 |
| 服务器 | uvicorn | FastAPI 官方推荐 ASGI 服务器 |
| 前端 | 原生 HTML + CSS + JS | 零构建工具依赖，由 FastAPI 直接托管静态文件 |
| 后台执行 | `threading.Thread` | Abaqus 通过 subprocess 调用，天然阻塞，线程隔离最直接 |
| 任务存储 | 内存 dict | 单用户场景，无需数据库 |
| 交互模式 | 请求-响应 + 轮询 | 用户提交后等待，每 3 秒轮询状态，完成后提醒刷新 |
| 启动方式 | `myagent web` 新命令 | 与 `myagent` CLI 互不干扰 |

## 新增依赖

```
fastapi>=0.110.0
uvicorn>=0.27.0
```

## 页面布局

**A 方案 — 左右分栏**：
- 左侧 60%：对话区（消息列表 + 输入框 + 发送按钮）
- 右侧 40%：任务列表面板（历史任务卡片、状态指示灯、下载按钮）
- 顶部栏：MyAgent 标题 + 当前模型选择
- 任务完成后弹出刷新提醒

## 架构

```
浏览器 (HTML/JS)
  │  POST /api/chat       → 提交仿真描述
  │  GET  /api/tasks/{id}  → 轮询任务状态（每3秒）
  │  GET  /download/...    → 下载报告/图片
  ▼
FastAPI (myagent/web.py)
  │  TaskManager           → 创建任务、管理状态、启后台线程
  │  后台线程              → 执行5阶段流水线
  ▼
核心模块（复用，不改动）
  ├─ ScriptGenerator   → 参数提取 + 脚本生成
  ├─ AbaqusExecutor    → subprocess 执行 Abaqus
  ├─ ResultReader      → ODB → results.json + PNG
  └─ ReportGenerator   → matplotlib → HTML 报告
```

## 新增文件

| 文件 | 职责 | 预估行数 |
|------|------|----------|
| `myagent/web.py` | FastAPI 应用：路由注册、TaskManager、后台线程 | ~180 |
| `myagent/static/index.html` | 前端页面结构：左右分栏 HTML | ~250 |
| `myagent/static/app.js` | 前端逻辑：发送消息、轮询状态、下载 | ~120 |
| `myagent/static/style.css` | 前端样式：消息气泡、任务卡片、响应式 | ~200 |

## 改动文件

| 文件 | 改动内容 | 改动量 |
|------|----------|--------|
| `setup.py` | 新增 `fastapi`/`uvicorn` 依赖；新增 `myagent-web` 入口点 | +5 行 |
| `requirements.txt` | 添加 `fastapi` + `uvicorn` | +2 行 |

## API 端点

| 方法 | 路径 | 说明 | 响应 |
|------|------|------|------|
| `GET` | `/` | 前端页面 | `index.html` |
| `POST` | `/api/chat` | 提交仿真描述 | `{"task_id": "...", "status": "submitted"}` |
| `GET` | `/api/tasks/{task_id}` | 查询任务状态 | `{"status": "...", "progress": {...}, "result": {...}}` |
| `GET` | `/api/tasks` | 列出所有任务 | `[{"task_id": "...", "status": "...", ...}, ...]` |
| `GET` | `/api/models` | 列出可用模型 | `[{"name": "...", "provider": "..."}, ...]` |
| `GET` | `/download/{task_id}/report` | 下载 HTML 报告 | `application/octet-stream` |
| `GET` | `/download/{task_id}/{filename}` | 下载云图/数据 | `application/octet-stream` 或 `image/png` |

## 任务状态机

```
已提交(submitted) → 脚本生成中(generating) → 仿真执行中(executing)
  → 提取结果中(extracting) → 完成(completed)
                              → 失败(failed)
```

前端轮询检测到 `completed` 或 `failed` 后弹出刷新提醒。

## 安全

- 下载路径白名单验证：仅允许 task_id 对应输出目录下的文件
- 拒绝 `..` 等路径遍历字符
- API Key 沿用 config.yaml 的环境变量引用机制

## 测试计划

| 测试类型 | 覆盖范围 |
|----------|----------|
| 单元测试 | `TaskManager` 状态管理 |
| 集成测试 | `POST /api/chat` → 轮询 → 下载 完整流程 |
| 手动验证 | 浏览器中完成一次完整仿真对话 |
