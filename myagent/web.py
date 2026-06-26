"""MyAgent Web 服务 — FastAPI 应用

启动命令: myagent-web
提供 REST API + 静态文件服务，支持浏览器端对话式仿真。
支持多 CAE 后端切换。
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
from myagent.cae import create_generator, create_executor, get_result_reader, list_backends, get_backend_info
from myagent.report import ReportGenerator

# 确保所有 CAE 后端在启动时注册
import myagent.abaqus  # noqa: F401 — 注册 Abaqus 后端
import myagent.nnw     # noqa: F401 — 注册 NNW-HyFLOW 后端
import myagent.fealpy  # noqa: F401 — 注册 fealpy 后端


# ——— TaskManager ———

class TaskManager:
    """仿真任务管理器（线程安全）

    管理任务状态：submitted → generating → executing → extracting → completed/failed
    使用内存 dict 存储，单用户场景无需数据库。
    """

    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self, user_message: str, model_name: str, backend: str = "") -> str:
        """创建新任务

        Args:
            user_message: 用户仿真描述
            model_name: 使用的 LLM 模型名称
            backend: CAE 后端名称

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
                "backend": backend,
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


# ——— 仿真执行（后台线程） ———

def run_simulation_pipeline(task_id: str, user_message: str, model_name: str, backend: str = ""):
    """后台执行完整的 5 阶段仿真流水线

    此函数在独立线程中运行，不阻塞 HTTP 响应。
    每个阶段更新 task_manager 中的任务状态。

    Args:
        task_id: 任务 ID
        user_message: 用户仿真描述
        model_name: LLM 模型名称
        backend: CAE 后端名称（默认读取配置）
    """
    config = get_config()
    if not backend:
        backend = config.cae_backend
    job_dir = None

    try:
        # ——— 阶段 1+2: 参数提取 + 脚本生成 ———
        task_manager.update(task_id, status="generating",
                            status_text="脚本生成中",
                            progress_detail=f"正在生成 {backend} 脚本...")
        generator = create_generator(backend, model_name, config)

        # 先提取参数以获取后端特定信息（如 NNW 的网格路径）
        params = generator.extract_parameters(user_message)

        # Web 端跳过交互确认，直接生成脚本
        script, script_path = generator.generate_script(
            user_input=user_message,
            clarified_params=None,
        )

        # ——— 阶段 3: 执行仿真 ———
        task_manager.update(task_id, status="executing",
                            status_text="仿真执行中",
                            progress_detail=f"正在运行 {backend}（可能需要几分钟）...")
        executor = create_executor(backend, config)

        # 提取后端特定参数（如 NNW 需要的网格路径）
        extra_kwargs = {}
        if backend == "nnw":
            grid_path = params.get("grid", {}).get("path", "") if "error" not in params else ""
            if grid_path:
                from pathlib import Path as _Path
                if _Path(grid_path).exists():
                    extra_kwargs["grid_path"] = grid_path

        exec_result = executor.execute(script_path, **extra_kwargs)

        if not exec_result["success"]:
            error_msg = exec_result.get("error", "仿真执行失败")
            task_manager.update(task_id, status="failed",
                                status_text="仿真失败",
                                error=error_msg,
                                job_dir=exec_result.get("job_dir"))
            return

        job_dir = exec_result["job_dir"]

        # 检查是否需要手动运行
        if exec_result.get("needs_manual_run"):
            note = exec_result.get("note", "")
            task_manager.update(
                task_id,
                status="completed",
                status_text="脚本已准备",
                progress_detail="",
                result_summary={
                    "text": (f"📋 {note}\n\n📁 作业目录: {job_dir}"),
                    "needs_manual": True,
                },
                result_images=[],
                report_path=None,
                job_dir=job_dir,
            )
            return

        # ——— 阶段 4: 结果提取 ———
        task_manager.update(task_id, status="extracting",
                            status_text="提取结果中",
                            progress_detail="正在读取仿真结果...")
        result_reader_cls = get_result_reader(backend)
        result = result_reader_cls.read(job_dir)

        # 将 LLM 提取的项目名称注入结果（供报告使用）
        if result.success and hasattr(generator, 'extracted_params'):
            ep = generator.extracted_params
            if isinstance(ep, dict) and 'analysis_type' in ep:
                result.results_json['summary']['project_name'] = ep['analysis_type']

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
            report_path = ReportGenerator(job_dir, solver_name=backend).generate()
        except Exception as e:
            pass  # 报告生成失败非致命

        # ——— 完成 ———
        summary = result.summary
        task_manager.update(
            task_id,
            status="completed",
            status_text="已完成",
            progress_detail="",
            result_summary={
                "text": result.get_text_summary(),
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


# ——— FastAPI 应用 ———

_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="MyAgent Web",
    description="CAE 自然语言智能助手 Web 端",
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
    backend = body.get("backend") or get_config().cae_backend

    # 验证模型是否已配置
    config = get_config()
    if not config.is_model_configured(model_name):
        raise HTTPException(status_code=400,
                            detail=f"模型 '{model_name}' 未配置 API Key，请在终端中设置")

    # 验证后端是否存在
    available = list_backends()
    if backend not in available:
        raise HTTPException(status_code=400,
                            detail=f"未知后端: '{backend}'，可用: {', '.join(available)}")

    task_id = task_manager.create(user_message, model_name, backend=backend)

    # 启动后台线程执行仿真
    thread = threading.Thread(
        target=run_simulation_pipeline,
        args=(task_id, user_message, model_name, backend),
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


@app.get("/api/backends")
async def api_list_backends():
    """列出可用 CAE 后端"""
    config = get_config()
    current = config.cae_backend
    backends = []
    for name in list_backends():
        info = get_backend_info(name)
        backends.append({
            "name": name,
            "display_name": info.get("name", name),
            "current": name == current,
        })
    return JSONResponse(backends)


# ——— 下载端点 ———

def _safe_job_dir(task_id: str) -> Path:
    """获取任务输出目录，带安全检查"""
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
        if config:
            get_config(config)

        print(f"""
╔══════════════════════════════════════════════╗
║       MyAgent Web — CAE 智能助手             ║
║                                              ║
║  浏览器打开: http://{host}:{port}              ║
║  API 文档:   http://{host}:{port}/docs        ║
║  按 Ctrl+C 退出                               ║
╚══════════════════════════════════════════════╝
""")
        uvicorn.run(app, host=host, port=port, log_level="info")

    _web()
