"""Abaqus 脚本生成器 — 将自然语言转化为 Abaqus Python 脚本"""

import os
import re
import json
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from myagent.config import get_config
from myagent.llm.factory import get_llm
from myagent.abaqus.knowledge import (
    get_abaqus_system_prompt, DEFAULT_MATERIALS, RESULT_SAVER_CODE
)


class ScriptGenerator:
    """Abaqus 脚本生成器

    使用 LLM 将用户的自然语言描述转化为 Abaqus Python 仿真脚本。
    包含参数提取（追问缺失参数）和脚本生成两个阶段。
    """

    # 参数提取阶段的 system prompt
    PARAM_EXTRACTION_PROMPT = """你是一个有限元分析参数提取助手。
根据用户的自然语言描述，提取进行 Abaqus 仿真所需的参数。

对于缺失的关键参数（载荷大小/方向、约束条件），标记为 "missing"。
对于次要参数（网格尺寸、输出类型），根据工程经验给出合理默认值。

请以 JSON 格式回复（只输出 JSON）：
{
    "analysis_type": "static / modal / buckling / ...",
    "geometry": {
        "description": "几何描述",
        "dimensions": {"key": value, ...}
    },
    "material": {
        "name": "材料名",
        "known": true/false  // 是否使用预定义材料库
    },
    "loads": [
        {"type": "force/pressure/...", "magnitude": value, "direction": "x/y/z", "location": "..."}
    ],
    "boundary_conditions": [
        {"type": "fixed/pinned/...", "location": "..."}
    ],
    "mesh": {"size": value, "element_type": "C3D8R/..."},
    "outputs": ["stress", "displacement", ...],
    "missing_parameters": ["需追问的参数"],
    "questions": ["向用户追问的具体问题"]
}"""

    def __init__(self, model_name: Optional[str] = None, output_dir: Optional[str] = None):
        """初始化脚本生成器

        Args:
            model_name: LLM 模型名称，默认使用配置文件中的 default_model
            output_dir: 脚本输出目录
        """
        config = get_config()
        self.model_name = model_name or config.default_model
        self.llm = get_llm(self.model_name, config)
        self.output_dir = Path(output_dir or config.work_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 用于存储对话历史和上下文
        self.conversation_history: List[Dict[str, str]] = []
        self.extracted_params: Dict = {}

    def extract_parameters(self, user_input: str) -> Dict:
        """从用户输入中提取仿真参数

        第一阶段：分析用户输入，提取已知参数，标记缺失参数。

        Args:
            user_input: 用户的自然语言描述

        Returns:
            参数提取结果字典，包含 extracted 和 missing 部分
        """
        messages = [
            {"role": "system", "content": self.PARAM_EXTRACTION_PROMPT},
            {"role": "user", "content": user_input},
        ]

        response = self.llm.chat(messages, temperature=0.1, max_tokens=2000)

        # 尝试解析 JSON 响应
        try:
            # 提取 JSON 部分（LLM 可能在 JSON 前后加了其他文字）
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                params = json.loads(json_match.group())
            else:
                params = {"error": "无法解析参数", "raw_response": response}
        except json.JSONDecodeError as e:
            params = {"error": f"JSON 解析失败: {e}", "raw_response": response}

        self.extracted_params = params
        return params

    def get_clarification_questions(self, params: Optional[Dict] = None) -> List[str]:
        """从参数提取结果中获取需要向用户确认的问题

        Args:
            params: 参数提取结果，默认使用最近一次提取的结果

        Returns:
            问题列表
        """
        if params is None:
            params = self.extracted_params

        return params.get("questions", [])

    def has_missing_params(self, params: Optional[Dict] = None) -> bool:
        """检查是否有缺失的关键参数

        Args:
            params: 参数提取结果

        Returns:
            True 如果有缺失参数
        """
        if params is None:
            params = self.extracted_params
        missing = params.get("missing_parameters", [])
        return len(missing) > 0

    def generate_script(
        self,
        user_input: str,
        output_dir: Optional[str] = None,
        clarified_params: Optional[str] = None
    ) -> Tuple[str, str]:
        """生成 Abaqus Python 仿真脚本

        第二阶段：根据完整参数生成可执行的 Abaqus 脚本。
        生成的脚本末尾会强制注入结果保存代码，确保 results.json 必定生成。

        Args:
            user_input: 用户的原始描述
            output_dir: 脚本输出目录
            clarified_params: 用户补充确认的参数信息

        Returns:
            (完整脚本内容, 脚本文件路径) 元组
        """
        # 构建用户消息
        user_message = f"请为以下仿真需求生成 Abaqus Python 脚本：\n\n{user_input}"

        if clarified_params:
            user_message += f"\n\n补充确认的参数：\n{clarified_params}"

        if output_dir:
            user_message += f"\n\n输出目录：{output_dir}"
        else:
            user_message += "\n\n输出目录：当前工作目录（.）"

        user_message += (
            "\n\n你只需完成：建模、材料、截面、装配、分析步、载荷/边界、网格、作业提交。"
            "\n作业名用 'SimJob'，模型名用 'Model-1'。"
            "\n不要写后处理代码，系统会自动处理结果提取。"
        )

        messages = [
            {"role": "system", "content": get_abaqus_system_prompt()},
            {"role": "user", "content": user_message},
        ]

        # 生成脚本（非流式，需要完整的脚本）
        response = self.llm.chat(
            messages,
            temperature=0.2,
            max_tokens=8192,
        )

        # 提取 Python 代码块
        script = self._extract_code(response)

        # ——— 强制注入结果保存代码 ———
        script = script.rstrip() + "\n\n" + RESULT_SAVER_CODE

        # 保存脚本文件
        if output_dir:
            script_dir = Path(output_dir)
        else:
            script_dir = self.output_dir
        script_dir.mkdir(parents=True, exist_ok=True)

        script_path = script_dir / "abaqus_simulation.py"
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)

        return script, str(script_path)

    def _extract_code(self, response: str) -> str:
        """从 LLM 响应中提取 Python 代码块

        Args:
            response: LLM 的完整响应文本

        Returns:
            提取出的 Python 代码
        """
        # 尝试匹配 ```python ... ``` 代码块
        pattern = r'```python\s*\n(.*?)\n```'
        matches = re.findall(pattern, response, re.DOTALL)

        if matches:
            # 如果有多个代码块，合并它们
            return "\n\n".join(matches)

        # 尝试匹配 ``` ... ```（无语言标记）
        pattern = r'```\s*\n(.*?)\n```'
        matches = re.findall(pattern, response, re.DOTALL)

        if matches:
            return "\n\n".join(matches)

        # 如果没有代码块标记，返回整个响应
        # 尝试去除开头的解释文字
        lines = response.strip().split("\n")
        code_lines = []
        in_code = False

        for line in lines:
            if line.strip().startswith("from ") or line.strip().startswith("import "):
                in_code = True
            if in_code:
                code_lines.append(line)

        if code_lines:
            return "\n".join(code_lines)

        return response.strip()

    def switch_model(self, model_name: str):
        """切换 LLM 模型

        Args:
            model_name: 新的模型名称
        """
        self.model_name = model_name
        self.llm = get_llm(model_name)
