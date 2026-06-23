"""Abaqus 执行器 — 调用 Abaqus CAE 运行仿真脚本"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple


class AbaqusExecutor:
    """Abaqus 脚本执行器

    负责调用 Abaqus CAE 执行 Python 脚本，
    管理输出目录、超时、日志等。
    """

    def __init__(
        self,
        abaqus_command: str = "abaqus",
        work_dir: str = "output",
        timeout: int = 3600
    ):
        """初始化执行器

        Args:
            abaqus_command: Abaqus 命令路径（.bat 文件）
            work_dir: 输出目录基础路径
            timeout: 执行超时时间（秒）
        """
        self.abaqus_command = abaqus_command
        self.work_dir = Path(work_dir)
        self.timeout = timeout
        self._ensure_work_dir()

    def _ensure_work_dir(self):
        """确保输出目录存在"""
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        script_path: str,
        job_name: Optional[str] = None,
        cpus: int = 4
    ) -> Dict:
        """执行 Abaqus 仿真脚本

        Args:
            script_path: Python 脚本文件路径
            job_name: 作业名称（用于创建子目录），默认为脚本名
            cpus: 使用的 CPU 核心数

        Returns:
            执行结果字典：
            {
                "success": bool,
                "job_dir": str,        # 作业输出目录
                "stdout": str,         # 标准输出
                "stderr": str,         # 错误输出
                "return_code": int,    # 返回码
                "duration": float,     # 执行耗时（秒）
                "error": str or None,  # 错误信息
            }
        """
        script_path = Path(script_path)

        # 确定作业目录
        if job_name is None:
            job_name = script_path.stem

        # 创建时间戳子目录避免覆盖
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_dir = self.work_dir / f"{job_name}_{timestamp}"
        job_dir.mkdir(parents=True, exist_ok=True)

        # 将脚本复制到作业目录
        import shutil
        dest_script = job_dir / script_path.name
        shutil.copy2(script_path, dest_script)

        # 构建 Abaqus 命令
        # abaqus cae noGUI=script.py — 在作业目录中执行
        command = (
            f'"{self.abaqus_command}" '
            f'cae noGUI={dest_script.name}'
        )

        print(f"\n[执行器] 执行命令: {command}")
        print(f"[执行器] 工作目录: {job_dir}")

        # 执行
        start_time = datetime.now()

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(job_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
                errors="replace",
            )

            duration = (datetime.now() - start_time).total_seconds()
            stdout = result.stdout
            stderr = result.stderr
            return_code = result.returncode
            success = return_code == 0

            # 检查是否有错误
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
            error = f"找不到 Abaqus 命令: {self.abaqus_command}"

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
        """从 Abaqus 输出中提取错误信息

        Args:
            stdout: 标准输出
            stderr: 标准错误

        Returns:
            格式化的错误消息
        """
        errors = []

        # 查找常见错误模式
        patterns = [
            (r'Error:\s*(.*)', "错误"),
            (r'Abaqus Error:\s*(.*)', "Abaqus 错误"),
            (r'Abaqus/Standard .*? error\s*\n(.*?)\n', "求解器错误"),
            (r'SyntaxError:\s*(.*)', "语法错误"),
            (r'NameError:\s*(.*)', "名称错误"),
            (r'AttributeError:\s*(.*)', "属性错误"),
            (r'KeyError:\s*(.*)', "键错误"),
            (r'TypeError:\s*(.*)', "类型错误"),
            (r'ValueError:\s*(.*)', "值错误"),
            (r"File.*line \d+.*\n(.*)", "脚本错误"),
        ]

        # 合并 stdout 和 stderr 搜索
        combined = stdout + "\n" + stderr

        for pattern, label in patterns:
            matches = re.findall(pattern, combined, re.IGNORECASE)
            for match in matches:
                errors.append(f"[{label}] {match.strip()}")

        if errors:
            return "\n".join(errors[-5:])  # 最多返回最后5条

        # 如果没有匹配到特定模式，返回尾部输出
        tail = stderr.strip() or stdout.strip()
        if tail:
            lines = tail.split("\n")
            return "\n".join(lines[-10:])  # 最后10行

        return "未知错误"
