"""Abaqus 结果提取 — 读取仿真输出文件"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class SimulationResult:
    """仿真结果数据类

    封装一次仿真运行的所有结果数据。
    """

    def __init__(self, job_dir: str):
        """初始化

        Args:
            job_dir: 仿真作业输出目录
        """
        self.job_dir = Path(job_dir)
        self.success = False
        self.results_json: Dict[str, Any] = {}
        self.images: List[str] = []
        self.raw_data: Dict[str, Any] = {}
        self.paths_data: Dict[str, Any] = {}
        self.error: Optional[str] = None

    @property
    def summary(self) -> Dict[str, Any]:
        """获取结果摘要"""
        return self.results_json.get("summary", {})

    @property
    def max_stress(self) -> Optional[float]:
        """获取最大 von Mises 应力"""
        return self.summary.get("max_stress_mises")

    @property
    def max_displacement(self) -> Optional[float]:
        """获取最大位移"""
        return self.summary.get("max_displacement")

    @property
    def image_paths(self) -> List[str]:
        """获取所有结果图片的绝对路径"""
        return [str(self.job_dir / img) for img in self.images]


class ResultReader:
    """仿真结果读取器

    读取 Abaqus 仿真完成后生成的 results.json 和图片文件。
    """

    @staticmethod
    def read(job_dir: str) -> SimulationResult:
        """读取仿真结果

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

        # 1. 查找并读取 results.json
        json_path = job_path / "results.json"
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    result.results_json = json.load(f)
                # 检查 results.json 中是否有错误标记
                if result.results_json.get("error"):
                    result.error = result.results_json["error"]
                else:
                    result.success = True
            except (json.JSONDecodeError, IOError) as e:
                result.error = f"读取 results.json 失败: {e}"
        else:
            # ——— 提供详细诊断 ———
            result.error = ResultReader._diagnose_missing_results(job_path)

        # 2. 读取路径采样数据 (paths.json)
        paths_json = job_path / "paths.json"
        if paths_json.exists():
            try:
                with open(paths_json, "r", encoding="utf-8") as f:
                    result.paths_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass  # 非致命，路径数据可选

        # 3. 查找结果图片
        image_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}
        for ext in image_extensions:
            for img_file in job_path.glob(f"*{ext}"):
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

        # 检查作业目录中的关键文件
        odb_files = list(job_path.glob("*.odb"))
        sta_files = list(job_path.glob("*.sta"))
        msg_files = list(job_path.glob("*.msg"))
        log_files = list(job_path.glob("*.log"))
        py_files = list(job_path.glob("*.py"))
        dat_files = list(job_path.glob("*.dat"))

        if py_files:
            parts.append(f"脚本已生成 ({len(py_files)} 个 .py)")
        else:
            parts.append("脚本未生成 — 生成阶段可能失败")

        if odb_files:
            parts.append(f"ODB 已生成 ({len(odb_files)} 个) 但结果保存代码未执行")
        else:
            parts.append("无 ODB — Abaqus 求解可能失败")

        if msg_files:
            # 尝试读取最后几行错误
            try:
                msg_path = msg_files[0]
                with open(msg_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = [l.strip() for l in f.readlines() if l.strip()]
                error_lines = [l for l in lines[-5:] if "error" in l.lower()]
                if error_lines:
                    parts.append(f".msg 错误: {'; '.join(error_lines[-2:])}")
            except:
                pass

        if sta_files:
            parts.append(f"求解状态文件存在 (.sta) — 作业可能未完成")
            # 检查 sta 文件最后一行
            try:
                sta_path = sta_files[0]
                with open(sta_path, "r", encoding="utf-8", errors="replace") as f:
                    sta_lines = [l.strip() for l in f.readlines() if l.strip()]
                if sta_lines:
                    parts.append(f".sta 最后状态: {sta_lines[-1][:100]}")
            except:
                pass

        if log_files:
            parts.append(f"日志文件存在 (.log) — 检查是否有错误")

        if not odb_files and not sta_files and not msg_files:
            parts.append("Abaqus 可能未正常启动 — 检查 Abaqus 安装和许可证")

        return "; ".join(parts)

    @staticmethod
    def get_text_summary(result: SimulationResult) -> str:
        """生成结果的文本摘要

        Args:
            result: 仿真结果对象

        Returns:
            文本摘要
        """
        if not result.success:
            return f"仿真结果读取失败: {result.error}"

        summary = result.summary
        lines = []

        if "max_stress_mises" in summary:
            lines.append(f"  - 最大 von Mises 应力: {summary['max_stress_mises']:.2f} MPa")
        if "max_displacement" in summary:
            lines.append(f"  - 最大位移: {summary['max_displacement']:.2f} mm")
        if "max_principal_stress" in summary:
            lines.append(f"  - 最大主应力: {summary['max_principal_stress']:.2f} MPa")
        if "min_principal_stress" in summary:
            lines.append(f"  - 最小主应力: {summary['min_principal_stress']:.2f} MPa")
        if "total_force" in summary:
            lines.append(f"  - 总反力: {summary['total_force']:.2f} N")
        if "safety_factor" in summary:
            sf = summary['safety_factor']
            lines.append(f"  - 安全系数: {sf:.2f}")

        if "additional" in summary:
            for key, value in summary["additional"].items():
                lines.append(f"  - {key}: {value}")

        if not lines:
            lines.append("  (结果数据暂无)")

        lines.append(f"\n  [img] 结果图片: {len(result.images)} 张")
        for img in result.images:
            lines.append(f"     - {img}")

        return "\n".join(lines)
