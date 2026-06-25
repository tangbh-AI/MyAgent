"""NNW-HyFLOW 脚本生成器 — 将自然语言转化为 .hypara 参数文件"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from myagent.config import get_config
from myagent.llm.factory import get_llm
from myagent.cae.base import AbstractScriptGenerator
from myagent.nnw.knowledge import get_nnw_system_prompt


class ScriptGenerator(AbstractScriptGenerator):
    """NNW-HyFLOW 脚本生成器

    使用 LLM 将用户的自然语言描述转化为 NNW .hypara 参数文件。
    包含参数提取和文件生成两个阶段。
    """

    # 参数提取阶段的 system prompt
    PARAM_EXTRACTION_PROMPT = """你是一个计算流体力学 (CFD) 参数提取助手。
根据用户的自然语言描述，提取进行 NNW-HyFLOW (PHengLEI) 仿真所需的参数。

对于缺失的关键参数（马赫数、网格文件路径），标记为 "missing"。
对于次要参数（湍流模型、CFL数、离散格式），根据工程经验给出合理默认值。

请以 JSON 格式回复（只输出 JSON）：
{
    "analysis_type": "CFD 分析类型（如：亚声速翼型绕流、超声速进气道、高超声速钝体等）",
    "flow_conditions": {
        "mach_number": 0.5,
        "attack_angle_deg": 2.0,
        "sideslip_angle_deg": 0.0,
        "reynolds_number": 1.0e6,
        "temperature_k": 288.15,
        "dimensionality": "3D / 2D"
    },
    "grid": {
        "path": "网格文件路径（.cgns 或 .fts）",
        "type": "structured / unstructured / hybrid",
        "format": "cgns / fts"
    },
    "turbulence": {
        "model": "sa / sst / laminar / euler",
        "name": "四字简称"
    },
    "schemes": {
        "inviscid_flux": "roe / steger / vanleer / ausmpwplus",
        "limiter": "smooth / minmod / vencat",
        "time_integration": "lusgs"
    },
    "boundary_conditions": [
        {"name": "Farfield", "type": 4, "description": "远场"},
        {"name": "Symmetry", "type": 3, "description": "对称面"},
        {"name": "downwall", "type": 2, "description": "下壁面"},
        {"name": "upwall", "type": 2, "description": "上壁面"}
    ],
    "_bc_note": "边界名称必须与 CGNS 网格中的 patch 名称完全一致。如不确定具体的 patch 名称（如机翼的上下表面可能叫 downwall/upwall 或其他），询问用户或标记为 missing。有多个壁面时必须分别为每个壁面写一个条目。",
    "output": {
        "variables": "需要的可视化变量",
        "report_type": "气动力系数 / 流场云图 / 残差收敛"
    },
    "missing_parameters": ["需追问的参数，如 '网格文件路径'"],
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

        # 调用抽象基类的初始化
        super().__init__()

    def extract_parameters(self, user_input: str) -> Dict:
        """从用户输入中提取 CFD 仿真参数

        Args:
            user_input: 用户的自然语言描述

        Returns:
            参数提取结果字典
        """
        messages = [
            {"role": "system", "content": self.PARAM_EXTRACTION_PROMPT},
            {"role": "user", "content": user_input},
        ]

        response = self.llm.chat(messages, temperature=0.1, max_tokens=2000)

        # 尝试解析 JSON 响应
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                params = json.loads(json_match.group())
            else:
                params = {"error": "无法解析参数", "raw_response": response}
        except json.JSONDecodeError as e:
            params = {"error": f"JSON 解析失败: {e}", "raw_response": response}

        self.extracted_params = params

        # 记录对话历史（用于多轮对话上下文）
        self.conversation_history.append({
            "role": "user",
            "content": user_input[:1000]  # 截断以控制上下文长度
        })

        return params

    def generate_script(
        self,
        user_input: str,
        output_dir: Optional[str] = None,
        clarified_params: Optional[str] = None
    ) -> Tuple[str, str]:
        """生成 NNW-HyFLOW .hypara 参数文件

        使用 LLM 根据用户描述生成 5 个配置文件：
        key.hypara, cfd_para.hypara, grid_para.hypara,
        boundary_condition.hypara, partition.hypara

        Args:
            user_input: 用户的原始描述
            output_dir: 输出目录
            clarified_params: 用户补充确认的参数信息

        Returns:
            (完整脚本内容, 输出目录路径) 元组
        """
        # 构建用户消息
        user_message = f"请为以下 CFD 仿真需求生成 NNW-HyFLOW .hypara 参数文件：\n\n{user_input}"

        if clarified_params:
            user_message += f"\n\n补充确认的参数：\n{clarified_params}"

        # 附加上下文参数
        if self.extracted_params and "error" not in self.extracted_params:
            params_json = json.dumps(self.extracted_params, ensure_ascii=False, indent=2)
            user_message += f"\n\n已提取的参数供参考：\n```json\n{params_json}\n```"

        messages = [
            {"role": "system", "content": get_nnw_system_prompt()},
            {"role": "user", "content": user_message},
        ]

        # 生成文件内容
        response = self.llm.chat(
            messages,
            temperature=0.2,
            max_tokens=16384,
        )

        # 保存到作业目录
        if output_dir:
            job_dir = Path(output_dir)
        else:
            job_dir = self.output_dir

        bin_dir = job_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)

        self._save_hypara_files(response, bin_dir)

        # 记录对话历史（用于多轮对话上下文）
        file_count = len(list(bin_dir.glob("*.hypara")))
        self.conversation_history.append({
            "role": "assistant",
            "content": f"已生成 {file_count} 个 .hypara 文件到 {bin_dir}"
        })

        # 返回（全部内容, 作业目录）
        return response, str(job_dir)

    def _save_hypara_files(self, response: str, bin_dir: Path):
        """将 LLM 响应解析为独立的 .hypara 文件并保存

        LLM 响应格式：
        ===FILE: key.hypara===
        (内容)
        ===FILE: cfd_para.hypara===
        (内容)
        ...

        Args:
            response: LLM 响应文本
            bin_dir: 保存文件的 bin/ 目录
        """
        # 用正则提取各个文件块
        pattern = r'===FILE:\s*(\S+\.hypara)\s*===\s*\n(.*?)(?=\n===FILE:|$)'
        matches = re.findall(pattern, response, re.DOTALL)

        if not matches:
            # 回退：尝试根据内容特征分拆
            print("[NNW Generator] 警告: 未检测到 ===FILE:=== 标记，尝试回退解析")
            self._fallback_save(response, bin_dir)
            return

        saved_files = []
        for filename, content in matches:
            content = content.strip()
            if not content:
                continue
            filepath = bin_dir / filename
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content + "\n")
            saved_files.append(filename)
            print(f"[NNW Generator] 已保存: {filepath}")

        if not saved_files:
            print("[NNW Generator] 警告: 未生成任何 .hypara 文件")

    def _fallback_save(self, response: str, bin_dir: Path):
        """回退方案：根据文件名关键词拆分原始响应

        Args:
            response: LLM 响应文本
            bin_dir: 保存目录
        """
        file_sections = {
            "key.hypara": ["string title", "ndim", "nparafile"],
            "cfd_para.hypara": ["refMachNumber", "viscousType", "CFLStart", "maxSimuStep"],
            "grid_para.hypara": ["gridtype", "from_gtype", "from_gfile"],
            "boundary_condition.hypara": ["nBoundaryConditons", "bcName", "bcType"],
            "partition.hypara": ["pgridtype", "maxproc", "npartmethod"],
        }

        # 尝试根据每行的参数名归属到对应文件
        lines = response.strip().split("\n")
        current_file = None
        file_contents: Dict[str, list] = {f: [] for f in file_sections}

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # 检测文件归属
            matched = None
            for fname, keywords in file_sections.items():
                for kw in keywords:
                    if kw in stripped:
                        matched = fname
                        break
                if matched:
                    break

            if matched:
                file_contents[matched].append(line)

        # 保存非空文件
        for fname, content_lines in file_contents.items():
            if content_lines:
                filepath = bin_dir / fname
                content = "\n".join(content_lines)
                # 简单验证：至少 3 行，有分号
                semicolons = content.count(";")
                if len(content_lines) >= 2 and semicolons >= 1:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(content + "\n")
                    print(f"[NNW Generator] (回退) 已保存: {filepath} ({len(content_lines)} 行)")
                else:
                    print(f"[NNW Generator] (回退) 跳过: {fname} (内容不足: {len(content_lines)} 行, {semicolons} 个分号)")

    def switch_model(self, model_name: str):
        """切换 LLM 模型

        Args:
            model_name: 新的模型名称
        """
        self.model_name = model_name
        self.llm = get_llm(model_name)
