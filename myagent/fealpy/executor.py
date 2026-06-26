"""fealpy 执行器 — 通过 subprocess 运行 fealpy Python 脚本"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

from myagent.cae.base import AbstractExecutor


class FealpyExecutor(AbstractExecutor):
    """fealpy 脚本执行器

    fealpy 是纯 Python 库，通过 subprocess.run("python script.py") 执行。
    默认使用当前 conda ccuse 环境的 Python。
    """

    def __init__(
        self,
        python_path: str = "",
        work_dir: str = "output",
        timeout: int = 3600,
    ):
        """初始化执行器

        Args:
            python_path: Python 解释器路径，空字符串 = 自动检测 (sys.executable)
            work_dir: 输出目录基础路径
            timeout: 执行超时时间（秒）
        """
        self.python_path = python_path or self._detect_python()
        self.work_dir = Path(work_dir)
        self.timeout = timeout
        self._ensure_work_dir()

    @staticmethod
    def _detect_python() -> str:
        """自动检测 Python 路径（优先使用当前环境的 Python）"""
        import sys
        return sys.executable

    def _ensure_work_dir(self):
        """确保输出目录存在"""
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        script_path: str,
        job_name: Optional[str] = None,
        **kwargs
    ) -> Dict:
        """执行 fealpy 仿真脚本

        Args:
            script_path: Python 脚本文件路径
            job_name: 作业名称

        Returns:
            执行结果字典：
            {
                "success": bool,
                "job_dir": str,
                "stdout": str,
                "stderr": str,
                "return_code": int,
                "duration": float,
                "error": str or None,
            }
        """
        script_path = Path(script_path)

        # 确定作业目录
        if job_name is None:
            job_name = script_path.stem

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_dir = self.work_dir / f"{job_name}_{timestamp}"
        job_dir.mkdir(parents=True, exist_ok=True)

        # 复制脚本到作业目录
        dest_script = job_dir / script_path.name
        shutil.copy2(script_path, dest_script)

        # ——— 预执行语法验证 ———
        script_content = dest_script.read_text(encoding="utf-8")
        try:
            compile(script_content, str(dest_script), "exec")
        except SyntaxError as e:
            error_msg = (
                f"脚本语法错误（可能由 LLM 输出截断导致）:\n"
                f"  文件: {dest_script.name}\n"
                f"  错误: {e.msg} (第 {e.lineno} 行)"
            )
            return {
                "success": False,
                "job_dir": str(job_dir),
                "stdout": "",
                "stderr": error_msg,
                "return_code": -1,
                "duration": 0.0,
                "error": error_msg,
            }

        # 构建命令
        command = f'"{self.python_path}" "{dest_script.name}"'

        print(f"\n[Fealpy Executor] 执行命令: {command}")
        print(f"[Fealpy Executor] 工作目录: {job_dir}")
        print(f"[Fealpy Executor] Python: {self.python_path}")

        start_time = datetime.now()

        try:
            # 继承当前环境变量（确保 conda ccuse 的 Python 能找到 fealpy）
            env = os.environ.copy()

            result = subprocess.run(
                command,
                shell=True,
                cwd=str(job_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
                errors="replace",
                env=env,
            )

            duration = (datetime.now() - start_time).total_seconds()
            stdout = result.stdout
            stderr = result.stderr
            return_code = result.returncode
            success = return_code == 0

            error = None
            if not success:
                error = self._extract_error(stdout, stderr)

        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            success = False
            return_code = -1
            stdout = ""
            stderr = ""
            error = f"仿真执行超时（超过 {self.timeout} 秒）"

        except FileNotFoundError:
            duration = 0
            success = False
            return_code = -1
            stdout = ""
            stderr = ""
            error = f"找不到 Python: {self.python_path}"

        # 保存执行日志
        log_path = job_dir / "execution.log"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"命令: {command}\n")
            f.write(f"Python: {self.python_path}\n")
            f.write(f"返回码: {return_code}\n")
            f.write(f"耗时: {duration:.1f} 秒\n\n")
            f.write("=== STDOUT ===\n")
            f.write(stdout + "\n")
            f.write("=== STDERR ===\n")
            f.write(stderr + "\n")

        return {
            "success": success,
            "job_dir": str(job_dir),
            "stdout": stdout,
            "stderr": stderr,
            "return_code": return_code,
            "duration": round(duration, 1),
            "error": error,
        }

    def _extract_error(self, stdout: str, stderr: str) -> str:
        """从 Python 输出中提取错误信息

        Args:
            stdout: 标准输出
            stderr: 标准错误

        Returns:
            格式化的错误消息
        """
        errors = []
        combined = stdout + "\n" + stderr

        # 常见 Python 错误模式
        patterns = [
            (r'Error:\s*(.*)', "错误"),
            (r'ModuleNotFoundError:\s*(.*)', "模块未找到"),
            (r'ImportError:\s*(.*)', "导入错误"),
            (r'SyntaxError:\s*(.*)', "语法错误"),
            (r'NameError:\s*(.*)', "名称错误"),
            (r'AttributeError:\s*(.*)', "属性错误"),
            (r'TypeError:\s*(.*)', "类型错误"),
            (r'ValueError:\s*(.*)', "值错误"),
            (r'File ".*", line \d+.*\n(.*)', "脚本错误"),
            (r'MemoryError', "内存不足"),
        ]

        for pattern, label in patterns:
            matches = re.findall(pattern, combined, re.IGNORECASE)
            for match in matches:
                errors.append(f"[{label}] {match.strip()}")

        if errors:
            return "\n".join(errors[-5:])

        tail = stderr.strip() or stdout.strip()
        if tail:
            lines = tail.split("\n")
            return "\n".join(lines[-10:])

        return "未知错误"
