# MyAgent Web 端实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 CLI 基础上新增 Web 网页端——用户通过浏览器对话提交仿真需求，下载报告。

**Architecture:** FastAPI 提供 REST API + 静态文件服务，前端原生 HTML/JS 实现左右分栏布局。后台用 threading.Thread 执行 5 阶段仿真流水线，前端每 3 秒轮询任务状态。所有核心模块（generator/executor/result/report）零改动直接复用。

**Tech Stack:** Python 3.10+ / FastAPI / uvicorn / 原生 HTML+CSS+JS / threading

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `requirements.txt` | 修改 | +2 行依赖 |
| `setup.py` | 修改 | +5 行 entry_point + install_requires |
| `myagent/web.py` | **新建** | FastAPI + TaskManager + 后台线程 |
| `myagent/static/index.html` | **新建** | 前端页面结构 |
| `myagent/static/app.js` | **新建** | 前端逻辑 |
| `myagent/static/style.css` | **新建** | 前端样式 |
| `tests/test_web.py` | **新建** | Web 模块测试 |

---

### Task 1: 添加 Web 依赖

**Files:**
- Modify: `requirements.txt`
- Modify: `setup.py`

- [ ] **Step 1: requirements.txt 追加两行**

```bash
echo "" >> requirements.txt
echo "# Web 服务" >> requirements.txt
echo "fastapi>=0.110.0" >> requirements.txt
echo "uvicorn>=0.27.0" >> requirements.txt
```

- [ ] **Step 2: setup.py 追加依赖和入口点**

在 `setup.py` 的 `install_requires` 列表末尾（`"colorama>=0.4.6",` 之后）追加：
```python
        "fastapi>=0.110.0",
        "uvicorn>=0.27.0",
```

在 `entry_points` 的 `console_scripts` 列表中追加：
```python
            "myagent-web=myagent.web:cli",
```

完整修改后的 `setup.py`：
```python
"""MyAgent — Abaqus 自然语言智能助手"""

from setuptools import setup, find_packages

setup(
    name="myagent",
    version="0.1.0",
    description="Abaqus 自然语言智能助手 — 用中文描述仿真需求，自动执行有限元分析",
    author="MyAgent",
    python_requires=">=3.10",
    packages=find_packages(),
    install_requires=[
        "openai>=1.0.0",
        "anthropic>=0.30.0",
        "click>=8.1.0",
        "pyyaml>=6.0",
        "numpy>=1.24.0",
        "Pillow>=10.0.0",
        "matplotlib>=3.7.0",
        "colorama>=0.4.6",
        "fastapi>=0.110.0",
        "uvicorn>=0.27.0",
    ],
    entry_points={
        "console_scripts": [
            "myagent=myagent.main:cli",
            "myagent-web=myagent.web:cli",
        ],
    },
)
```

- [ ] **Step 3: 安装新依赖并验证导入**

Run: `pip install fastapi uvicorn`
Run: `"D:/anaconda/envs/ccuse/python.exe" -c "import fastapi; import uvicorn; print('OK')"`
Expected: `OK`

---

### Task 2: 创建 TaskManager（web.py 核心）

**Files:**
- Create: `myagent/web.py`

`TaskManager` 负责管理仿真任务的全生命周期：创建任务、更新状态、查询任务。线程安全的 in-memory 存储。

- [ ] **Step 1: 编写 TaskManager 类**

创建 `myagent/web.py`：

```python
"""MyAgent Web 服务 — FastAPI 应用

启动命令: myagent-web
提供 REST API + 静态文件服务，支持浏览器端对话式仿真。
"""

import os
import json
import uuid
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from myagent.config import get_config
from myagent.llm.factory import get_llm, list_models as list_llm_models
from myagent.abaqus.generator import ScriptGenerator
from myagent.abaqus.executor import AbaqusExecutor
from myagent.abaqus.result import ResultReader
from myagent.report import ReportGenerator


# ——— TaskManager ———

class TaskManager:
    """仿真任务管理器（线程安全）

    管理任务状态：submitted → generating → executing → extracting → completed/failed
    使用内存 dict 存储，单用户场景无需数据库。
    """

    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, user_message: str, model_name: str) -> str:
        """创建新任务

        Args:
            user_message: 用户仿真描述
            model_name: 使用的 LLM 模型名称

        Returns:
            task_id
        """
        task_id = uuid.uuid4().hex[:12]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "user_message": user_message,
                "model_name": model_name,
                "status": "submitted",
                "status_text": "已提交",
                "progress_detail": "",
                "created_at": now,
                "result_summary": None,
                "result_images": [],
                "report_path": None,
                "job_dir": None,
                "error": None,
            }
        return task_id

    def update(self, task_id: str, **kwargs):
        """更新任务字段"""
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].update(kwargs)

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """查询单个任务"""
        with self._lock:
            return self._tasks.get(task_id)

    def list_all(self) -> List[Dict[str, Any]]:
        """列出所有任务（按创建时间倒序）"""
        with self._lock:
            tasks = list(self._tasks.values())
            tasks.sort(key=lambda t: t["created_at"], reverse=True)
            return tasks


# 全局单例
task_manager = TaskManager()
```

- [ ] **Step 2: 验证 Python 语法**

Run: `"D:/anaconda/envs/ccuse/python.exe" -m py_compile D:/MyAgent/myagent/web.py`
Expected: 无输出（成功）

---

### Task 3: 添加仿真执行器和 FastAPI 路由

**Files:**
- Modify: `myagent/web.py`（追加路由和启动逻辑）

- [ ] **Step 1: 追加仿真执行函数**

在 `myagent/web.py` 末尾追加：

```python
# ——— 仿真执行（后台线程） ———

def run_simulation_pipeline(task_id: str, user_message: str, model_name: str):
    """后台执行完整的 5 阶段仿真流水线

    此函数在独立线程中运行，不阻塞 HTTP 响应。
    每个阶段更新 task_manager 中的任务状态。

    Args:
        task_id: 任务 ID
        user_message: 用户仿真描述
        model_name: LLM 模型名称
    """
    config = get_config()
    job_dir = None

    try:
        # ——— 阶段 1: 参数提取 ———
        task_manager.update(task_id, status="generating",
                            status_text="脚本生成中",
                            progress_detail="正在提取参数...")
        generator = ScriptGenerator(model_name=model_name)

        # ——— 阶段 2: 脚本生成（跳过交互确认，直接生成） ———
        task_manager.update(task_id, progress_detail="正在生成 Abaqus 脚本...")
        script, script_path = generator.generate_script(
            user_input=user_message,
            clarified_params=None,  # Web 端跳过交互确认
        )

        # ——— 阶段 3: 执行仿真 ———
        task_manager.update(task_id, status="executing",
                            status_text="仿真执行中",
                            progress_detail="正在运行 Abaqus（可能需要几分钟）...")
        executor = AbaqusExecutor(
            abaqus_command=config.abaqus_command,
            work_dir=config.work_dir,
            timeout=config.timeout,
        )
        exec_result = executor.execute(script_path)

        if not exec_result["success"]:
            error_msg = exec_result.get("error", "仿真执行失败")
            task_manager.update(task_id, status="failed",
                                status_text="仿真失败",
                                error=error_msg,
                                job_dir=exec_result.get("job_dir"))
            return

        job_dir = exec_result["job_dir"]

        # ——— 阶段 4: 结果提取 ———
        task_manager.update(task_id, status="extracting",
                            status_text="提取结果中",
                            progress_detail="正在读取仿真结果...")
        result = ResultReader.read(job_dir)

        if not result.success:
            task_manager.update(task_id, status="failed",
                                status_text="结果提取失败",
                                error=result.error or "无法读取仿真结果",
                                job_dir=job_dir)
            return

        # ——— 阶段 5: 生成 HTML 报告 ———
        task_manager.update(task_id, progress_detail="正在生成分析报告...")
        report_path = None
        try:
            report_path = ReportGenerator(job_dir).generate()
        except Exception as e:
            # 报告生成失败非致命
            pass

        # ——— 完成 ———
        summary = result.summary
        text_summary = ResultReader.get_text_summary(result)

        task_manager.update(
            task_id,
            status="completed",
            status_text="已完成",
            progress_detail="",
            result_summary={
                "text": text_summary,
                "max_stress": summary.get("max_stress_mises"),
                "max_displacement": summary.get("max_displacement"),
                "safety_factor": summary.get("safety_factor"),
            },
            result_images=result.images,
            report_path=report_path,
            job_dir=job_dir,
        )

    except Exception as e:
        task_manager.update(task_id, status="failed",
                            status_text="执行出错",
                            error=str(e),
                            job_dir=job_dir)
```

- [ ] **Step 2: 追加 FastAPI 应用和路由**

在文件末尾继续追加：

```python
# ——— FastAPI 应用 ———

# 确定静态文件目录
_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="MyAgent Web",
    description="Abaqus 自然语言智能助手 Web 端",
    version="0.1.0",
)

# 挂载静态文件目录（必须在路由注册之前）
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/")
async def index():
    """前端页面"""
    index_path = _STATIC_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>前端文件未找到</h1>", status_code=404)
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.post("/api/chat")
async def api_chat(request: Request):
    """提交仿真描述 → 返回 task_id"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体须为 JSON")

    user_message = body.get("message", "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="message 不能为空")

    model_name = body.get("model") or get_config().default_model

    # 验证模型是否已配置
    config = get_config()
    if not config.is_model_configured(model_name):
        raise HTTPException(status_code=400,
                            detail=f"模型 '{model_name}' 未配置 API Key，请在终端中设置")

    task_id = task_manager.create(user_message, model_name)

    # 启动后台线程执行仿真
    thread = threading.Thread(
        target=run_simulation_pipeline,
        args=(task_id, user_message, model_name),
        daemon=True,
    )
    thread.start()

    return JSONResponse({
        "task_id": task_id,
        "status": "submitted",
        "status_text": "已提交",
        "message": f"任务已提交，ID: {task_id}",
    })


@app.get("/api/tasks/{task_id}")
async def api_get_task(task_id: str):
    """查询任务状态"""
    task = task_manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 返回前端需要的字段
    return JSONResponse({
        "task_id": task["task_id"],
        "status": task["status"],
        "status_text": task["status_text"],
        "progress_detail": task["progress_detail"],
        "created_at": task["created_at"],
        "result_summary": task.get("result_summary"),
        "result_images": task.get("result_images", []),
        "report_available": task.get("report_path") is not None,
        "error": task.get("error"),
    })


@app.get("/api/tasks")
async def api_list_tasks():
    """列出所有任务"""
    tasks = task_manager.list_all()
    return JSONResponse([
        {
            "task_id": t["task_id"],
            "user_message": t["user_message"][:80],
            "status": t["status"],
            "status_text": t["status_text"],
            "created_at": t["created_at"],
            "report_available": t.get("report_path") is not None,
        }
        for t in tasks
    ])


@app.get("/api/models")
async def api_list_models():
    """列出可用模型"""
    config = get_config()
    models = list_llm_models(config)
    return JSONResponse([
        {
            "name": m["name"],
            "provider": m["provider"],
            "configured": config.is_model_configured(m["name"]),
        }
        for m in models
    ])


# ——— 下载端点 ———

def _safe_job_dir(task_id: str) -> Path:
    """获取任务输出目录，带安全检查

    Args:
        task_id: 任务 ID

    Returns:
        作业目录 Path

    Raises:
        HTTPException: 任务不存在或目录不存在
    """
    task = task_manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    job_dir_str = task.get("job_dir")
    if not job_dir_str:
        raise HTTPException(status_code=404, detail="任务尚未完成，无输出目录")

    job_dir = Path(job_dir_str)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="输出目录不存在")

    return job_dir


@app.get("/download/{task_id}/report")
async def download_report(task_id: str):
    """下载 HTML 分析报告"""
    job_dir = _safe_job_dir(task_id)
    report_path = job_dir / "analysis_report.html"

    if not report_path.exists():
        raise HTTPException(status_code=404, detail="报告文件不存在")

    return FileResponse(
        path=str(report_path),
        filename=f"report_{task_id}.html",
        media_type="text/html",
    )


@app.get("/download/{task_id}/{filename:path}")
async def download_file(task_id: str, filename: str):
    """下载结果文件（云图 PNG / results.json 等）

    包含路径遍历保护：拒绝 .. 和绝对路径。
    """
    # 安全检查：拒绝路径遍历
    if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
        raise HTTPException(status_code=403, detail="非法文件路径")

    job_dir = _safe_job_dir(task_id)
    file_path = job_dir / filename
    resolved = file_path.resolve()

    # 确保解析后的路径仍在 job_dir 内
    if not str(resolved).startswith(str(job_dir.resolve())):
        raise HTTPException(status_code=403, detail="非法文件路径")

    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    # 根据扩展名设置 MIME 类型
    suffix = resolved.suffix.lower()
    media_type_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".json": "application/json",
        ".html": "text/html",
    }
    media_type = media_type_map.get(suffix, "application/octet-stream")

    return FileResponse(
        path=str(resolved),
        filename=filename,
        media_type=media_type,
    )


# ——— CLI 入口 ———

def cli():
    """myagent-web 命令入口"""
    import uvicorn
    import click

    @click.command()
    @click.option("--host", default="127.0.0.1", help="绑定地址")
    @click.option("--port", default=8000, help="端口号")
    @click.option("--config", "-c", default=None, help="配置文件路径")
    def _web(host, port, config):
        """启动 MyAgent Web 服务"""
        # 预热配置（触发懒加载）
        if config:
            get_config(config)

        print(f"""
╔══════════════════════════════════════════════╗
║       MyAgent Web — Abaqus 智能助手         ║
║                                              ║
║  浏览器打开: http://{host}:{port}              ║
║  API 文档:   http://{host}:{port}/docs        ║
║  按 Ctrl+C 退出                               ║
╚══════════════════════════════════════════════╝
""")
        uvicorn.run(app, host=host, port=port, log_level="info")

    _web()
```

- [ ] **Step 3: 验证导入**

Run: `"D:/anaconda/envs/ccuse/python.exe" -c "from myagent.web import app, task_manager, cli; print('所有导入成功')"`
Expected: `所有导入成功`

---

### Task 4: 创建前端 HTML

**Files:**
- Create: `myagent/static/index.html`

- [ ] **Step 1: 确保 static 目录存在**

Run: `mkdir -p /d/MyAgent/myagent/static`

- [ ] **Step 2: 编写 index.html**

创建 `myagent/static/index.html`：
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MyAgent — Abaqus 自然语言智能助手</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>

<!-- 顶部栏 -->
<header class="header">
  <div class="header-left">
    <h1>🤖 MyAgent</h1>
    <span class="header-subtitle">Abaqus 自然语言智能助手</span>
  </div>
  <div class="header-right">
    <select id="model-select" class="model-select">
      <option value="">加载中...</option>
    </select>
  </div>
</header>

<!-- 主体：左右分栏 -->
<main class="main-container">

  <!-- 左侧：对话区 -->
  <section class="chat-panel">
    <div class="chat-messages" id="chat-messages">
      <div class="message bot">
        <div class="message-avatar">🤖</div>
        <div class="message-bubble">
          <p>你好！我是 MyAgent，请用中文描述你的仿真需求。</p>
          <p class="message-hint">例如："分析一个悬臂梁，长1m，截面50x100mm，钢材料，自由端受1000N的力"</p>
        </div>
      </div>
    </div>

    <div class="chat-input-area">
      <textarea
        id="chat-input"
        class="chat-input"
        placeholder="描述你的仿真需求..."
        rows="3"
      ></textarea>
      <button id="send-btn" class="send-btn" onclick="sendMessage()">
        发送
      </button>
    </div>
  </section>

  <!-- 右侧：任务列表 -->
  <aside class="task-panel">
    <div class="task-panel-header">
      <h2>📊 任务列表</h2>
      <button class="refresh-btn" onclick="refreshTasks()">🔄 刷新</button>
    </div>
    <div class="task-list" id="task-list">
      <div class="task-empty">暂无任务</div>
    </div>
  </aside>

</main>

<!-- 完成提醒弹窗（默认隐藏） -->
<div id="notification" class="notification hidden">
  <div class="notification-content">
    <div class="notification-icon">✅</div>
    <h3 id="notification-title">任务完成!</h3>
    <p id="notification-msg"></p>
    <div class="notification-actions">
      <button class="btn-primary" onclick="dismissNotification()">关闭</button>
    </div>
  </div>
</div>

<script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 3: 验证 HTML 语法**

Run: `"D:/anaconda/envs/ccuse/python.exe" -c "from myagent.web import app; print('HTML页面就绪')"`
Expected: `HTML页面就绪`

---

### Task 5: 创建前端 JS

**Files:**
- Create: `myagent/static/app.js`

- [ ] **Step 1: 编写 app.js**

创建 `myagent/static/app.js`：
```javascript
// MyAgent Web 前端逻辑

let pollingTimer = null;

// ——— 初始化 ———

document.addEventListener('DOMContentLoaded', () => {
    loadModels();
    refreshTasks();
    document.getElementById('chat-input').addEventListener('keydown', (e) => {
        // Ctrl+Enter 发送
        if (e.ctrlKey && e.key === 'Enter') {
            sendMessage();
        }
    });
});

// ——— 模型列表 ———

async function loadModels() {
    try {
        const resp = await fetch('/api/models');
        const models = await resp.json();
        const select = document.getElementById('model-select');
        select.innerHTML = models.map(m =>
            `<option value="${m.name}">${m.name} ${m.configured ? '' : '(未配置)'}</option>`
        ).join('');
    } catch (e) {
        console.error('加载模型列表失败:', e);
    }
}

// ——— 发送消息 ———

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;

    input.value = '';
    input.disabled = true;
    document.getElementById('send-btn').disabled = true;

    // 显示用户消息
    appendMessage('user', message);
    // 显示等待消息
    const loadingMsg = appendMessage('bot', '⏳ 正在处理...');

    try {
        const model = document.getElementById('model-select').value;
        const resp = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, model }),
        });

        if (!resp.ok) {
            const err = await resp.json();
            loadingMsg.querySelector('.message-bubble').innerHTML =
                `<p style="color:#e74c3c;">❌ 提交失败: ${err.detail || '未知错误'}</p>`;
            input.disabled = false;
            document.getElementById('send-btn').disabled = false;
            return;
        }

        const data = await resp.json();
        loadingMsg.querySelector('.message-bubble').innerHTML =
            `<p>✅ 任务已提交 (ID: ${data.task_id})</p>
             <p>仿真正在后台运行，完成后会提醒你。</p>`;

        // 开始轮询任务状态
        startPolling(data.task_id, loadingMsg);

    } catch (e) {
        loadingMsg.querySelector('.message-bubble').innerHTML =
            `<p style="color:#e74c3c;">❌ 网络错误: ${e.message}</p>`;
    }

    input.disabled = false;
    document.getElementById('send-btn').disabled = false;
    refreshTasks();
}

// ——— 消息管理 ———

function appendMessage(role, text) {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.innerHTML = `
        <div class="message-avatar">${role === 'user' ? '👤' : '🤖'}</div>
        <div class="message-bubble"><p>${text}</p></div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
}

// ——— 任务轮询 ———

function startPolling(taskId, messageEl) {
    if (pollingTimer) clearInterval(pollingTimer);

    pollingTimer = setInterval(async () => {
        try {
            const resp = await fetch(`/api/tasks/${taskId}`);
            const task = await resp.json();

            // 更新对话中的进度消息
            let statusText = `🔧 任务状态: ${task.status_text}`;
            if (task.progress_detail) {
                statusText += `\n${task.progress_detail}`;
            }
            messageEl.querySelector('.message-bubble').innerHTML =
                `<p>${statusText}</p>`;

            // 检查完成/失败
            if (task.status === 'completed') {
                clearInterval(pollingTimer);
                pollingTimer = null;
                showCompletionMessage(task, messageEl);
                showNotification(task);
                refreshTasks();
            } else if (task.status === 'failed') {
                clearInterval(pollingTimer);
                pollingTimer = null;
                messageEl.querySelector('.message-bubble').innerHTML =
                    `<p style="color:#e74c3c;">❌ 任务失败: ${task.error || '未知错误'}</p>`;
                refreshTasks();
            }

        } catch (e) {
            console.error('轮询失败:', e);
        }
    }, 3000); // 每 3 秒轮询
}

function showCompletionMessage(task, messageEl) {
    const summary = task.result_summary || {};
    let html = '<p>✅ 仿真完成!</p>';

    if (summary.max_stress !== undefined && summary.max_stress !== null) {
        html += `<p>📊 最大应力: ${summary.max_stress} MPa</p>`;
    }
    if (summary.max_displacement !== undefined && summary.max_displacement !== null) {
        html += `<p>📏 最大位移: ${summary.max_displacement} mm</p>`;
    }

    html += '<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;">';
    if (task.report_available) {
        html += `<a href="/download/${task.task_id}/report" class="btn-download" download>📥 下载报告</a>`;
    }
    if (task.result_images && task.result_images.length > 0) {
        task.result_images.forEach(img => {
            html += `<a href="/download/${task.task_id}/${img}" class="btn-download" download>🖼️ ${img}</a>`;
        });
    }
    html += '</div>';

    messageEl.querySelector('.message-bubble').innerHTML = html;
}

// ——— 完成提醒 ———

function showNotification(task) {
    document.getElementById('notification-title').textContent = '✅ 任务完成!';
    document.getElementById('notification-msg').textContent =
        `仿真已完成，可在右侧任务列表中查看和下载结果。`;
    document.getElementById('notification').classList.remove('hidden');
}

function dismissNotification() {
    document.getElementById('notification').classList.add('hidden');
}

// ——— 任务列表 ———

async function refreshTasks() {
    try {
        const resp = await fetch('/api/tasks');
        const tasks = await resp.json();
        const container = document.getElementById('task-list');

        if (tasks.length === 0) {
            container.innerHTML = '<div class="task-empty">暂无任务</div>';
            return;
        }

        container.innerHTML = tasks.map(t => {
            const statusClass = {
                'submitted': 'status-pending',
                'generating': 'status-pending',
                'executing': 'status-pending',
                'extracting': 'status-pending',
                'completed': 'status-done',
                'failed': 'status-failed',
            }[t.status] || 'status-pending';

            const statusIcon = {
                'submitted': '📨',
                'generating': '🔧',
                'executing': '⚙️',
                'extracting': '📊',
                'completed': '✅',
                'failed': '❌',
            }[t.status] || '⏳';

            let downloadBtns = '';
            if (t.report_available) {
                downloadBtns += `<a href="/download/${t.task_id}/report" class="btn-download-sm" download>📥 报告</a>`;
            }

            return `
            <div class="task-card" onclick="location.href='#task-${t.task_id}'">
              <div class="task-card-header">
                <span class="task-status-icon">${statusIcon}</span>
                <span class="task-status ${statusClass}">${t.status_text}</span>
              </div>
              <div class="task-msg">${escapeHtml(t.user_message)}</div>
              <div class="task-time">${t.created_at}</div>
              <div class="task-actions">${downloadBtns}</div>
            </div>
          `;
        }).join('');
    } catch (e) {
        console.error('刷新任务列表失败:', e);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
```

---

### Task 6: 创建前端 CSS

**Files:**
- Create: `myagent/static/style.css`

- [ ] **Step 1: 编写 style.css**

创建 `myagent/static/style.css`：
```css
/* MyAgent Web 前端样式 */

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    background: #f0f2f5;
    color: #2c3e50;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

/* ——— 顶部栏 ——— */

.header {
    background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
    color: white;
    padding: 12px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-shrink: 0;
}

.header-left h1 { font-size: 20px; }
.header-subtitle { font-size: 12px; opacity: 0.8; margin-left: 4px; }

.model-select {
    padding: 6px 12px;
    border-radius: 6px;
    border: 1px solid rgba(255,255,255,0.3);
    background: rgba(255,255,255,0.15);
    color: white;
    font-size: 13px;
    cursor: pointer;
}
.model-select option { color: #2c3e50; }

/* ——— 主体布局 ——— */

.main-container {
    display: flex;
    flex: 1;
    overflow: hidden;
}

/* ——— 左侧对话区 ——— */

.chat-panel {
    width: 60%;
    display: flex;
    flex-direction: column;
    background: #fafafa;
    border-right: 1px solid #e0e0e0;
}

.chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
}

.message {
    display: flex;
    gap: 10px;
    margin-bottom: 16px;
}

.message.user { flex-direction: row-reverse; }

.message-avatar {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    flex-shrink: 0;
    background: white;
}

.message-bubble {
    max-width: 75%;
    padding: 10px 14px;
    border-radius: 12px;
    font-size: 14px;
    line-height: 1.6;
    word-break: break-word;
}

.message.bot .message-bubble {
    background: #e3f2fd;
    border-radius: 4px 12px 12px 12px;
}

.message.user .message-bubble {
    background: #f3e5f5;
    border-radius: 12px 4px 12px 12px;
}

.message-hint {
    font-size: 12px;
    color: #7f8c8d;
    margin-top: 4px;
}

/* ——— 输入区 ——— */

.chat-input-area {
    display: flex;
    gap: 8px;
    padding: 12px 16px;
    border-top: 1px solid #e0e0e0;
    background: white;
}

.chat-input {
    flex: 1;
    padding: 10px 14px;
    border: 1px solid #ddd;
    border-radius: 8px;
    font-size: 14px;
    font-family: inherit;
    resize: none;
    outline: none;
}

.chat-input:focus { border-color: #3498db; }

.send-btn {
    padding: 10px 24px;
    background: #3498db;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    cursor: pointer;
    transition: background 0.2s;
    align-self: flex-end;
}

.send-btn:hover { background: #2980b9; }
.send-btn:disabled { background: #bdc3c7; cursor: not-allowed; }

/* ——— 右侧任务面板 ——— */

.task-panel {
    width: 40%;
    display: flex;
    flex-direction: column;
    background: white;
    overflow: hidden;
}

.task-panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 16px;
    border-bottom: 1px solid #e0e0e0;
}

.task-panel-header h2 { font-size: 16px; }

.refresh-btn {
    padding: 4px 12px;
    background: #ecf0f1;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
}

.refresh-btn:hover { background: #dfe6e9; }

.task-list {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
}

.task-empty {
    text-align: center;
    color: #95a5a6;
    padding: 40px 0;
    font-size: 14px;
}

/* ——— 任务卡片 ——— */

.task-card {
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 10px;
    cursor: pointer;
    transition: box-shadow 0.2s;
}

.task-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }

.task-card-header {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 6px;
}

.task-status-icon { font-size: 14px; }

.task-status {
    font-size: 12px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 12px;
}

.status-pending { color: #e67e22; background: #fef5e7; }
.status-done { color: #27ae60; background: #e8f8f5; }
.status-failed { color: #e74c3c; background: #fdedec; }

.task-msg {
    font-size: 12px;
    color: #555;
    margin-bottom: 4px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.task-time {
    font-size: 11px;
    color: #95a5a6;
}

.task-actions {
    margin-top: 6px;
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
}

/* ——— 下载按钮 ——— */

.btn-download {
    display: inline-block;
    padding: 6px 12px;
    background: #3498db;
    color: white;
    text-decoration: none;
    border-radius: 6px;
    font-size: 12px;
    transition: background 0.2s;
}

.btn-download:hover { background: #2980b9; }

.btn-download-sm {
    display: inline-block;
    padding: 3px 8px;
    background: #ecf0f1;
    color: #2c3e50;
    text-decoration: none;
    border-radius: 4px;
    font-size: 11px;
    border: 1px solid #ddd;
}

.btn-download-sm:hover { background: #dfe6e9; }

/* ——— 完成提醒弹窗 ——— */

.notification {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
}

.notification.hidden { display: none; }

.notification-content {
    background: white;
    border-radius: 16px;
    padding: 32px;
    text-align: center;
    max-width: 400px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}

.notification-icon { font-size: 48px; margin-bottom: 12px; }

.notification-content h3 {
    font-size: 20px;
    margin-bottom: 8px;
    color: #27ae60;
}

.notification-content p {
    font-size: 14px;
    color: #555;
    margin-bottom: 20px;
}

.btn-primary {
    padding: 10px 32px;
    background: #3498db;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    cursor: pointer;
}

.btn-primary:hover { background: #2980b9; }

/* ——— 响应式 ——— */

@media (max-width: 768px) {
    .main-container { flex-direction: column; }
    .chat-panel { width: 100%; height: 60%; }
    .task-panel { width: 100%; height: 40%; }
}
```

---

### Task 7: 编写测试

**Files:**
- Create: `tests/test_web.py`

- [ ] **Step 1: 编写 Web 模块测试**

创建 `tests/test_web.py`：
```python
"""MyAgent Web 模块测试"""

import pytest
from myagent.web import TaskManager, app
from fastapi.testclient import TestClient


class TestTaskManager:
    """TaskManager 单元测试"""

    def test_create_task(self):
        """测试创建任务"""
        tm = TaskManager()
        task_id = tm.create("分析一个悬臂梁", "deepseek-v4-pro")

        assert len(task_id) == 12
        task = tm.get(task_id)
        assert task is not None
        assert task["status"] == "submitted"
        assert task["user_message"] == "分析一个悬臂梁"

    def test_update_task(self):
        """测试更新任务状态"""
        tm = TaskManager()
        task_id = tm.create("测试", "deepseek-v4-pro")

        tm.update(task_id, status="generating", progress_detail="正在生成脚本...")
        task = tm.get(task_id)
        assert task["status"] == "generating"
        assert task["progress_detail"] == "正在生成脚本..."

    def test_list_tasks_order(self):
        """测试任务列表按时间倒序"""
        tm = TaskManager()
        id1 = tm.create("任务1", "deepseek-v4-pro")
        id2 = tm.create("任务2", "deepseek-v4-pro")

        tasks = tm.list_all()
        # 最新创建的在前面
        assert tasks[0]["task_id"] == id2
        assert tasks[1]["task_id"] == id1

    def test_get_nonexistent_task(self):
        """测试查询不存在的任务"""
        tm = TaskManager()
        assert tm.get("nonexistent") is None

    def test_update_nonexistent_task(self):
        """测试更新不存在的任务（不抛异常）"""
        tm = TaskManager()
        tm.update("nonexistent", status="completed")  # 不应抛异常


class TestWebAPI:
    """Web API 集成测试（不执行真实仿真）"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return TestClient(app)

    def test_index_page(self, client):
        """测试首页返回 HTML"""
        resp = client.get("/")
        assert resp.status_code in (200, 404)  # 200 如果有 index.html，404 如果未创建

    def test_chat_empty_message(self, client):
        """测试空消息被拒绝"""
        resp = client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 400

    def test_chat_missing_message(self, client):
        """测试缺少 message 字段"""
        resp = client.post("/api/chat", json={})
        assert resp.status_code == 400

    def test_list_models(self, client):
        """测试模型列表 API"""
        resp = client.get("/api/models")
        assert resp.status_code == 200
        models = resp.json()
        assert isinstance(models, list)

    def test_get_nonexistent_task(self, client):
        """测试查询不存在的任务"""
        resp = client.get("/api/tasks/nonexistent")
        assert resp.status_code == 404

    def test_list_tasks_empty(self, client):
        """测试空任务列表"""
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_download_nonexistent_task(self, client):
        """测试下载不存在任务的报告"""
        resp = client.get("/download/nonexistent/report")
        assert resp.status_code == 404

    def test_download_path_traversal(self, client):
        """测试路径遍历攻击被拒绝"""
        resp = client.get("/download/test123/../../../etc/passwd")
        assert resp.status_code in (403, 404)  # 安全拒绝
```

- [ ] **Step 2: 运行测试**

Run: `"D:/anaconda/envs/ccuse/python.exe" -m pytest D:/MyAgent/tests/test_web.py -v --tb=short`
Expected: 12 tests PASS

---

### Task 8: 集成验证

**Files:**
- Modify: `myagent/web.py`（修复测试中发现的问题）

- [ ] **Step 1: 确认 StaticFiles 挂载在路由注册之前**

检查 `myagent/web.py` 中 `app.mount("/static", ...)` 是否在所有 `@app.get/post` 装饰器之前：
- `StaticFiles` 挂载必须在路由之前，否则 `/static/*` 会被其他路由拦截

- [ ] **Step 2: 启动 Web 服务并验证页面可访问**

Run (在后台):
```bash
"D:/anaconda/envs/ccuse/python.exe" -c "from myagent.web import cli; cli()" --port 8000 &
```
等待 3 秒，然后：
```bash
curl -s http://127.0.0.1:8000/ | head -5
```
Expected: HTML 内容（`<!DOCTYPE html>`）

- [ ] **Step 3: 验证 API 端点**

```bash
# 模型列表
curl -s http://127.0.0.1:8000/api/models | python -m json.tool

# 任务列表
curl -s http://127.0.0.1:8000/api/tasks | python -m json.tool

# API 文档
curl -s http://127.0.0.1:8000/docs
```
全部应返回正常 JSON / HTML。

- [ ] **Step 4: 停止测试服务器**

```bash
kill %1 2>/dev/null || true
```

- [ ] **Step 5: 运行全部测试确认无回归**

Run: `"D:/anaconda/envs/ccuse/python.exe" -m pytest D:/MyAgent/tests/ -v --tb=short`
Expected: 37 + 12 = 49 tests PASS

---

### Task 9: 文档同步

**Files:**
- Modify: `README.md`
- Modify: `PROGRESS.md`

- [ ] **Step 1: 更新 README.md**

在"交互命令"表格之后、"命令行参数"之前插入 Web 端说明：

```markdown
## Web 端

启动 Web 服务：

```bash
myagent-web
```

浏览器打开 `http://127.0.0.1:8000`，可在网页中对话并下载仿真报告。

| 参数 | 说明 | 示例 |
|------|------|------|
| `--host` | 绑定地址（默认 127.0.0.1） | `--host 0.0.0.0` |
| `--port` | 端口号（默认 8000） | `--port 8080` |
| `--config`, `-c` | 指定配置文件 | `--config my_config.yaml` |
```

在项目结构中添加 `web.py` 和 `static/`：
```
├── myagent/               # 核心包
│   ├── main.py            # CLI 入口
│   ├── web.py             # Web 入口
│   ├── static/            # Web 前端
│   │   ├── index.html
│   │   ├── app.js
│   │   └── style.css
│   ├── ...
```

- [ ] **Step 2: 更新 PROGRESS.md**

在变更日志表最前面添加：
```
| 2026-06-24 | 新增 Web 端：FastAPI + 静态前端，浏览器对话 + 报告下载 |
```

更新文件清单，添加新文件：
```
│   ├── web.py               ✅ Web 服务 (FastAPI)
│   ├── static/              ✅ Web 前端
│   │   ├── index.html       ✅ 左右分栏页面
│   │   ├── app.js           ✅ 前端逻辑
│   │   └── style.css        ✅ 样式
```

---

## 验证清单

| # | 验证项 | 方法 |
|---|--------|------|
| 1 | 语法检查 web.py | `python -m py_compile` |
| 2 | 模块导入成功 | `from myagent.web import app` |
| 3 | Web 测试通过 (12 个) | `pytest tests/test_web.py -v` |
| 4 | 所有原有测试通过 (37 个) | `pytest tests/ -v` |
| 5 | 页面可访问 | `curl http://127.0.0.1:8000/` |
| 6 | API 文档可访问 | `curl http://127.0.0.1:8000/docs` |
| 7 | 模型列表 API | `curl /api/models` |
| 8 | `myagent` CLI 正常工作 | `myagent --help` |
