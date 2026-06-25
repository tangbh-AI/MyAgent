"""结果呈现器 — 展示仿真结果（图片 + 自然语言描述）"""

import os
import webbrowser
from pathlib import Path
from typing import List, Optional

from myagent.cae.base import SimulationResult


class Presenter:
    """仿真结果呈现器

    负责将仿真结果以用户友好的方式呈现：
    1. 显示数值结果摘要
    2. 展示图片路径
    3. （可选）用 LLM 生成自然语言分析
    4. （可选）自动打开结果图片
    """

    def __init__(self, auto_open_images: bool = False, backend_name: str = "Abaqus"):
        """初始化呈现器

        Args:
            auto_open_images: 是否自动打开结果图片
            backend_name: CAE 后端显示名称
        """
        self.auto_open_images = auto_open_images
        self.backend_name = backend_name

    def present(
        self,
        result: SimulationResult,
        execution_info: dict,
        report_path: Optional[str] = None,
    ) -> str:
        """呈现仿真结果

        Args:
            result: 仿真结果对象
            execution_info: 执行信息（来自 executor）
            report_path: HTML 分析报告路径

        Returns:
            格式化的呈现文本
        """
        lines = []
        lines.append("=" * 60)
        lines.append("                    [result] 仿真结果")
        lines.append("=" * 60)

        # 执行信息
        lines.append(f"\n[time] 执行耗时: {execution_info.get('duration', 'N/A')} 秒")
        lines.append(f"[dir] 输出目录: {execution_info.get('job_dir', 'N/A')}")

        if not result.success:
            lines.append(f"\n[X] 仿真失败")
            if result.error:
                lines.append(f"   错误信息: {result.error}")
            if execution_info.get("error"):
                lines.append(f"   执行错误: {execution_info['error']}")
            return "\n".join(lines)

        # 数值结果
        lines.append("\n[data] 关键结果:")
        text_summary = result.get_text_summary()
        lines.append(text_summary)

        # 图片文件
        if result.images:
            lines.append(f"\n[img] 结果图片 ({len(result.images)} 张):")
            for img in result.images:
                lines.append(f"   [img] {img}")

        lines.append("\n" + "=" * 60)

        # 报告路径
        if report_path:
            lines.append(f"\n[report] 可视化分析报告: {report_path}")

        # 自动打开图片
        if self.auto_open_images and result.images:
            self._open_images(result)

        return "\n".join(lines)

    def _open_images(self, result: SimulationResult):
        """自动打开结果图片

        Args:
            result: 仿真结果
        """
        for img_path in result.image_paths:
            if os.path.exists(img_path):
                try:
                    webbrowser.open(img_path)
                except Exception:
                    pass  # 无法打开图片时静默失败

    @staticmethod
    def show_progress(stage: str, message: str = "", backend_name: str = "CAE"):
        """显示进度信息

        Args:
            stage: 当前阶段名称
            message: 补充信息
            backend_name: CAE 后端显示名称（默认 "CAE"）
        """
        stages = {
            "generate": f"[gen] 生成 {backend_name} 脚本...",
            "execute": f"[run] 执行 {backend_name} 仿真计算...",
            "extract": "[data] 提取仿真结果...",
            "analyze": "[bot] 分析结果数据...",
            "report": "[report] 生成可视化报告...",
        }

        prefix = stages.get(stage, f"[{stage}]")
        if message:
            print(f"{prefix} {message}")
        else:
            print(prefix)

    @staticmethod
    def show_welcome(backend_name: str = "Abaqus"):
        """显示欢迎信息

        Args:
            backend_name: CAE 后端显示名称
        """
        print("\n" + "=" * 60)
        print(f"       [bot] MyAgent — {backend_name} 自然语言智能助手")
        print("=" * 60)
        print("用中文描述你的仿真需求，我来帮你自动完成分析。")
        print("输入 'help' 查看帮助，输入 'quit' 或 'exit' 退出。")
        print("=" * 60 + "\n")

    @staticmethod
    def show_help():
        """显示帮助信息"""
        print("""
[help] 可用命令:
  exit / quit    — 退出 MyAgent
  help           — 显示此帮助信息

[bot] 模型管理:
  models                    — 列出所有可用模型
  model <name>              — 切换 AI 模型 (如: model glm-4)
  model default <name>      — 设置默认模型
  model add <名称> <provider> <model_id> [base_url] [api_key]
                            — 添加新模型 (provider: openai_compat / anthropic)
                            示例: model add my-model openai_compat gpt-4 https://api.openai.com/v1 sk-xxx

[key] API Key 管理:
  apikey set <模型名> <key>  — 设置/更新模型的 API Key
  apikey show [模型名]       — 查看 API Key（脱敏显示）

[backend] CAE 后端切换:
  backend           — 显示当前后端和可用后端列表
  backend list      — 列出所有可用后端
  backend <name>    — 切换到指定后端

[tool] 其他:
  clear          — 清空对话上下文

[tip] 使用示例:
  > 分析一个悬臂梁，长1米，矩形截面50x100mm，钢材料，自由端受向下1000N的力
  > 对这块板做模态分析，材料是铝，四边固定
  > 计算这个轴在扭矩500Nm下的应力分布
""")
