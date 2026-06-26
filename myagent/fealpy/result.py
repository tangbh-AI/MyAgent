"""fealpy 结果提取 — 读取仿真输出文件和生成图片"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
import numpy as np

from myagent.cae.base import SimulationResult, AbstractResultReader


class ResultReader(AbstractResultReader):
    """fealpy 仿真结果读取器

    读取 fealpy 仿真完成后生成的 results.json 和图片文件。
    """

    @staticmethod
    def read(job_dir: str) -> SimulationResult:
        """读取 fealpy 仿真结果

        Args:
            job_dir: 仿真作业输出目录

        Returns:
            SimulationResult 对象
        """
        result = SimulationResult(job_dir)
        job_path = Path(job_dir)

        if not job_path.exists():
            result.error = f"作业目录不存在: {job_dir}"
            return result

        # 1. 读取 results.json
        json_path = job_path / "results.json"
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    result.results_json = json.load(f)
                if result.results_json.get("error"):
                    result.error = result.results_json["error"]
                else:
                    result.success = True
            except (json.JSONDecodeError, IOError) as e:
                result.error = f"读取 results.json 失败: {e}"
        else:
            result.error = ResultReader._diagnose_missing_results(job_path)

        # 2. 读取 paths.json (可选)
        paths_json = job_path / "paths.json"
        if paths_json.exists():
            try:
                with open(paths_json, "r", encoding="utf-8") as f:
                    result.paths_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        # 3. 查找结果图片
        image_extensions = {".png", ".jpg", ".jpeg", ".bmp"}
        for ext in image_extensions:
            for img_file in job_path.glob(f"*{ext}"):
                if img_file.name not in result.images:
                    result.images.append(img_file.name)
            for img_file in job_path.glob(f"*{ext.upper()}"):
                if img_file.name not in result.images:
                    result.images.append(img_file.name)

        return result

    @staticmethod
    def _diagnose_missing_results(job_path: Path) -> str:
        """诊断 results.json 缺失的原因

        Args:
            job_path: 作业目录

        Returns:
            诊断信息
        """
        parts = ["未找到 results.json"]

        py_files = list(job_path.glob("*.py"))
        log_files = list(job_path.glob("*.log"))
        png_files = list(job_path.glob("*.png"))

        if py_files:
            parts.append(f"脚本已生成 ({len(py_files)} 个 .py)")
        else:
            parts.append("脚本未生成 — 生成阶段可能失败")

        if log_files:
            # 读取最后几行
            try:
                log_path = log_files[0]
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = [l.strip() for l in f.readlines() if l.strip()]
                error_lines = [l for l in lines[-5:] if "error" in l.lower()]
                if error_lines:
                    parts.append(f"日志错误: {'; '.join(error_lines[-2:])}")
            except Exception:
                pass

        if png_files:
            parts.append(f"图片已生成 ({len(png_files)} 个) 但 results.json 缺失")

        if not py_files and not log_files:
            parts.append("脚本可能未正常执行 — 检查 fealpy 是否正确安装")

        return "; ".join(parts)
