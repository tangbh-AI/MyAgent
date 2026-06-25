"""CAE 后端抽象基类

定义所有 CAE 后端必须实现的接口，以及后端无关的共享数据结构。
参照 LLM 层的 AbstractLLM 设计模式。
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ——— 共享数据类 ———

class SimulationResult:
    """仿真结果数据类 — 所有 CAE 后端共用

    封装一次仿真运行的所有结果数据，后端无关。
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

    def get_text_summary(self) -> str:
        """生成结果的文本摘要 — 后端无关

        各后端可通过在 read() 中设置 _text_summary 属性来提供
        后端特定的摘要格式（如 CFD 的气动力系数）。
        默认实现处理通用的 FEA 结果字段。

        Returns:
            文本摘要字符串
        """
        if not self.success:
            return f"仿真结果读取失败: {self.error}"

        # 如果后端已经预计算了文本摘要，直接使用
        if hasattr(self, '_text_summary') and self._text_summary:
            return self._text_summary

        summary = self.summary
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

        lines.append(f"\n  [img] 结果图片: {len(self.images)} 张")
        for img in self.images:
            lines.append(f"     - {img}")

        return "\n".join(lines)


# ——— 抽象基类 ———

class AbstractScriptGenerator(ABC):
    """仿真脚本生成器抽象基类

    使用 LLM 将自然语言描述转化为 CAE 仿真脚本。
    子类需提供后端特定的 system prompt 和脚本生成逻辑。
    """

    def __init__(self):
        self.conversation_history: List[Dict[str, str]] = []
        self.extracted_params: Dict = {}

    @abstractmethod
    def extract_parameters(self, user_input: str) -> Dict:
        """从用户输入提取仿真参数

        Args:
            user_input: 用户自然语言描述

        Returns:
            参数提取结果字典，包含 extracted 和 missing 部分
        """
        ...

    @abstractmethod
    def generate_script(
        self,
        user_input: str,
        clarified_params: Optional[str] = None
    ) -> Tuple[str, str]:
        """生成 CAE 仿真脚本

        Args:
            user_input: 用户原始描述
            clarified_params: 补充确认的参数

        Returns:
            (完整脚本内容, 脚本文件路径) 元组
        """
        ...

    @abstractmethod
    def switch_model(self, model_name: str):
        """切换 LLM 模型"""
        ...

    def has_missing_params(self, params: Optional[Dict] = None) -> bool:
        """检查是否有缺失的关键参数

        Args:
            params: 参数提取结果，默认使用最近一次提取的结果

        Returns:
            True 如果有缺失参数
        """
        if params is None:
            params = self.extracted_params
        missing = params.get("missing_parameters", [])
        return len(missing) > 0

    def get_clarification_questions(self, params: Optional[Dict] = None) -> List[str]:
        """获取需要向用户确认的问题列表

        Args:
            params: 参数提取结果，默认使用最近一次提取的结果

        Returns:
            问题列表
        """
        if params is None:
            params = self.extracted_params
        return params.get("questions", [])


class AbstractExecutor(ABC):
    """仿真执行器抽象基类

    负责执行 CAE 仿真脚本，管理输出目录、超时、日志等。
    """

    @abstractmethod
    def execute(self, script_path: str, **kwargs) -> Dict:
        """执行仿真脚本

        Args:
            script_path: 脚本文件路径
            **kwargs: 后端特定参数

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
        ...


class AbstractResultReader(ABC):
    """仿真结果读取器抽象基类

    读取仿真完成后生成的结果数据和图片文件。
    """

    @staticmethod
    @abstractmethod
    def read(job_dir: str) -> SimulationResult:
        """读取仿真结果

        Args:
            job_dir: 仿真作业输出目录

        Returns:
            SimulationResult 对象
        """
        ...
