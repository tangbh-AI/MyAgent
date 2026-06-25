"""MyAgent CLI 入口 — 交互对话循环

启动命令: myagent 或 myagent chat
支持 --model 切换模型，--config 指定配置文件
支持多 CAE 后端，通过 config.yaml 切换
"""

import os
import sys
from pathlib import Path
from typing import Optional

import click

from myagent.config import Config, get_config
from myagent.llm.factory import get_llm, list_models as list_llm_models
from myagent.cae import (
    create_generator, create_executor, get_result_reader,
    list_backends, get_backend_info,
)
from myagent.presenter import Presenter

# 确保所有 CAE 后端在启动时注册
import myagent.abaqus  # noqa: F401 — 注册 Abaqus 后端
import myagent.nnw     # noqa: F401 — 注册 NNW-HyFLOW 后端


class MyAgent:
    """MyAgent 主控制器

    管理交互对话循环，协调各模块完成 NL → CAE 仿真的完整流程。
    支持多 CAE 后端，通过 config.yaml 的 cae.backend 切换。
    """

    def __init__(self, model_name: Optional[str] = None, config_path: Optional[str] = None):
        """初始化 MyAgent

        Args:
            model_name: LLM 模型名称
            config_path: 配置文件路径
        """
        # 加载配置
        self.config = get_config(config_path)
        self.model_name = model_name or self.config.default_model
        self.backend = self.config.cae_backend
        self.backend_info = get_backend_info(self.backend)
        self.presenter = Presenter(
            auto_open_images=False,
            backend_name=self.backend_info.get("name", self.backend),
        )
        self._components_ready = False

    def _init_components(self):
        """初始化/重建各组件（通过 CAE 工厂创建）"""
        try:
            self.generator = create_generator(self.backend, self.model_name, self.config)
        except Exception as e:
            raise RuntimeError(
                f"初始化 LLM 失败（模型 '{self.model_name}'，后端 '{self.backend}'）: {e}"
            )

        self.executor = create_executor(self.backend, self.config)
        self._result_reader_cls = get_result_reader(self.backend)
        self._components_ready = True

    def run(self):
        """启动交互对话循环"""
        self.presenter.show_welcome(self.backend_info.get("name", self.backend))

        # 检查默认模型是否已配置 Key，未配置则现场激活
        if not self.config.is_model_configured(self.model_name):
            print(f"[!]  默认模型 '{self.model_name}' 未配置 API Key。")
            if not self._activate_model(self.model_name):
                print("[X] 未设置 API Key，无法启动。请设置后重试。")
                return

        # 初始化组件
        self._init_components()

        while True:
            try:
                # 读取用户输入
                user_input = click.prompt("[user]", prompt_suffix="> ").strip()

                if not user_input:
                    continue

                # 处理内置命令
                if self._handle_command(user_input):
                    continue

                # 处理仿真请求
                self._handle_simulation(user_input)

            except KeyboardInterrupt:
                print("\n\nBye!")
                break
            except EOFError:
                print("\n\nBye!")
                break
            except Exception as e:
                print(f"\n[X] 发生错误: {e}")
                print("请重试或输入 'help' 查看帮助。")

    def _handle_command(self, user_input: str) -> bool:
        """处理内置命令

        Args:
            user_input: 用户输入

        Returns:
            True 如果是命令并已处理，False 否则
        """
        cmd = user_input.lower().strip()

        if cmd in ("exit", "quit", "q"):
            print("Bye!")
            sys.exit(0)

        elif cmd == "help":
            self.presenter.show_help()
            return True

        elif cmd == "models":
            self._list_models()
            return True

        elif cmd.startswith("model add "):
            # model add <name> <provider> <model_id> [base_url] [api_key]
            args = user_input[10:].strip().split()
            self._model_add(*args)
            return True

        elif cmd.startswith("model default "):
            # model default <name>
            name = user_input[15:].strip()
            self._model_set_default(name)
            return True

        elif cmd.startswith("model "):
            # model <name> — 切换模型
            new_model = user_input[6:].strip()
            self._switch_model(new_model)
            return True

        elif cmd.startswith("apikey set "):
            # apikey set <model> <key>
            parts = user_input[11:].strip().split(maxsplit=1)
            if len(parts) == 2:
                self._apikey_set(parts[0], parts[1])
            else:
                print("[X] 用法: apikey set <模型名> <API_KEY>")
            return True

        elif cmd.startswith("apikey show"):
            # apikey show [model]
            parts = user_input[11:].strip()
            model_name = parts if parts else None
            self._apikey_show(model_name)
            return True

        elif cmd == "clear":
            self.generator.conversation_history.clear()
            self.generator.extracted_params = {}
            print("[clear]  对话上下文已清空。")
            return True

        elif cmd == "backend":
            # 显示当前后端 + 可用列表
            print(f"\n[i] 当前 CAE 后端: {self.backend_info.get('name', self.backend)} [{self.backend}]")
            self._list_backends()
            return True

        elif cmd == "backend list":
            self._list_backends()
            return True

        elif cmd.startswith("backend "):
            # backend <name> — 切换后端
            new_backend = cmd[8:].strip()
            self._switch_backend(new_backend)
            return True

        return False

    def _list_models(self):
        """列出所有可用模型，标注配置状态"""
        models = list_llm_models(self.config)
        configured = 0
        print(f"\n[models] 可用模型 ({len(models)} 个):")
        for m in models:
            name = m["name"]
            marker = " * 当前" if name == self.model_name else ""
            has_key = self.config.is_model_configured(name)
            if has_key:
                configured += 1
                status = "[OK] 已配置"
            else:
                status = "[--] 未配置"
            print(f"  {status}  {name} [{m['provider']}] -> {m['model_id']}{marker}")
        print(f"\n  (已配置 {configured}/{len(models)}，未配置模型需切换时输入 Key 激活)")
        print()

    def _switch_model(self, model_name: str):
        """切换 AI 模型（未配置 Key 则现场激活）

        Args:
            model_name: 模型名称
        """
        # 验证模型是否存在
        if not self.config.get_model_config(model_name):
            print(f"[X] 模型 '{model_name}' 不存在。输入 'models' 查看可用模型。")
            return

        # 如果未配置 Key，现场激活
        if not self.config.is_model_configured(model_name):
            print(f"[--] 模型 '{model_name}' 未配置 API Key。")
            if not self._activate_model(model_name):
                return  # 用户取消

        # 验证可以创建 LLM 实例
        try:
            get_llm(model_name, self.config)
        except Exception as e:
            print(f"[X] 无法初始化模型 '{model_name}': {e}")
            return

        self.model_name = model_name
        self._init_components()
        print(f"[OK] 已切换到模型: {model_name}")

    def _switch_backend(self, backend_name: str):
        """切换 CAE 后端

        参照 _switch_model() 模式：验证 → 保存 → 重建组件。

        Args:
            backend_name: 后端名称
        """
        available = list_backends()
        if backend_name not in available:
            print(f"[X] 未知后端: '{backend_name}'，可用: {', '.join(available)}")
            return

        if backend_name == self.backend:
            print(f"[i] 已在使用后端: {self.backend_info.get('name', self.backend)}")
            return

        # 持久化到 config.yaml
        self.config.set_cae_backend(backend_name)

        # 更新状态
        self.backend = backend_name
        self.backend_info = get_backend_info(self.backend)

        # 重建组件
        self._init_components()
        print(f"[OK] 已切换到后端: {self.backend_info.get('name', self.backend)}")

    def _list_backends(self):
        """列出所有可用的 CAE 后端"""
        backends = list_backends()
        print(f"\n[backend] 可用 CAE 后端 ({len(backends)} 个):")
        for name in backends:
            info = get_backend_info(name)
            marker = " * 当前" if name == self.backend else ""
            print(f"  - {info.get('name', name)} [{name}]{marker}")
        print()

    def _activate_model(self, model_name: str) -> bool:
        """激活未配置的模型 — 要求用户输入 API Key

        Args:
            model_name: 模型名称

        Returns:
            True 成功激活，False 用户取消
        """
        print(f"   请输入 '{model_name}' 的 API Key（留空取消）:")
        api_key = click.prompt("   API Key", prompt_suffix="> ", default="").strip()
        if not api_key:
            print("   [skip]  已取消。")
            return False

        self.config.set_model_api_key(model_name, api_key)
        print(f"   [OK] '{model_name}' 已激活。")
        return True

    def _model_add(self, *args):
        """添加新模型: model add <name> <provider> <model_id> [base_url] [api_key]

        Args:
            args: (name, provider, model_id, base_url?, api_key?)
        """
        if len(args) < 3:
            print("[X] 用法: model add <名称> <provider> <model_id> [base_url] [api_key]")
            print("   provider: openai_compat 或 anthropic")
            print("   示例: model add my-model openai_compat my-model-id https://api.example.com sk-xxx")
            return

        name = args[0]
        provider = args[1]
        model_id = args[2]
        base_url = args[3] if len(args) > 3 else ""
        api_key = args[4] if len(args) > 4 else ""

        if provider not in ("openai_compat", "anthropic"):
            print(f"[X] 不支持的 provider: {provider}，请使用 openai_compat 或 anthropic")
            return

        # 重新加载配置以获取最新状态
        self.config.reload()
        success = self.config.add_model(name, provider, model_id, base_url, api_key)

        if success:
            print(f"[OK] 模型 '{name}' 已添加到配置文件")
            print(f"   provider: {provider}, model_id: {model_id}")
            if base_url:
                print(f"   base_url: {base_url}")
            if api_key:
                masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
                print(f"   api_key: {masked}")
            else:
                print(f"   [!]  未设置 API Key，请用 'apikey set {name} <key>' 设置")
        else:
            print(f"[X] 模型 '{name}' 已存在，请使用其他名称")

    def _model_set_default(self, name: str):
        """设置默认模型: model default <name>

        Args:
            name: 模型名称
        """
        if not name:
            print("[X] 用法: model default <模型名>")
            return

        # 验证模型存在
        self.config.reload()
        if not self.config.get_model_config(name):
            print(f"[X] 模型 '{name}' 不存在")
            return

        self.config.set_default_model(name)
        self.model_name = name
        print(f"[OK] 默认模型已设置为: {name}")

    def _apikey_set(self, model_name: str, api_key: str):
        """设置 API Key: apikey set <模型名> <API_KEY>

        Args:
            model_name: 模型名称
            api_key: API Key
        """
        if not model_name or not api_key:
            print("[X] 用法: apikey set <模型名> <API_KEY>")
            return

        self.config.reload()
        success = self.config.set_model_api_key(model_name, api_key)

        if success:
            masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
            print(f"[OK] 模型 '{model_name}' 的 API Key 已更新: {masked}")
        else:
            print(f"[X] 模型 '{model_name}' 不存在")
            print("   用 'models' 查看可用模型，或用 'model add' 添加新模型")

    def _apikey_show(self, model_name: Optional[str] = None):
        """显示 API Key（脱敏）: apikey show [模型名]

        Args:
            model_name: 模型名称，不指定则显示所有
        """
        self.config.reload()
        models = self.config.models

        if model_name:
            models = [m for m in models if m.get("name") == model_name]
            if not models:
                print(f"[X] 模型 '{model_name}' 不存在")
                return

        print(f"\n[key] API Key 配置 ({len(models)} 个模型):")
        for m in models:
            key = m.get("api_key", "")
            if key:
                if len(key) > 12:
                    masked = key[:8] + "..." + key[-4:]
                else:
                    masked = "***"
            else:
                masked = "(未设置)"
            print(f"  - {m['name']}: {masked}")
        print()

    def _handle_simulation(self, user_input: str):
        """处理仿真请求 — 完整的 NL → 仿真流程

        Args:
            user_input: 用户的自然语言描述
        """
        # ——— 阶段 1: 参数提取 ———
        self.presenter.show_progress("generate", "分析需求，提取参数...")

        params = self.generator.extract_parameters(user_input)

        if "error" in params:
            print(f"[!]  参数提取出现问题: {params['error']}")
            # 即使参数提取有问题，也尝试直接生成脚本

        # 展示提取的参数（供用户确认）
        self._show_extracted_params(params)

        # ——— 阶段 2: 参数确认 ———
        clarified_params = ""

        # 如果有缺失的关键参数，追问用户
        if self.generator.has_missing_params(params):
            missing = params.get("missing_parameters", [])
            print(f"\n[!]  以下关键参数缺失: {', '.join(missing)}")

            questions = self.generator.get_clarification_questions(params)
            if questions:
                print("\n🤖 MyAgent 需要确认:")
                for q in questions:
                    answer = click.prompt(f"   {q}", prompt_suffix="> ").strip()
                    if answer:
                        clarified_params += f"\n{q}\n回答: {answer}\n"

        # 总是给用户确认的机会
        print("\n📋 以上参数确认无误？")
        confirm = click.prompt(
            "   (Enter 确认 / 输入修改意见 / 'skip' 跳过确认直接生成)",
            prompt_suffix="> ",
            default=""
        ).strip()

        if confirm.lower() == "skip":
            pass  # 跳过确认
        elif confirm:
            # 用户有修改意见
            clarified_params += f"\n用户修改意见:\n{confirm}\n"

        # ——— 阶段 3: 脚本生成 ———
        backend_label = self.backend_info.get("name", self.backend)
        self.presenter.show_progress("generate", f"正在生成 {backend_label} 脚本...")

        script, script_path = self.generator.generate_script(
            user_input=user_input,
            clarified_params=clarified_params if clarified_params else None,
        )

        print(f"[OK] 脚本已生成: {script_path}")
        print(f"   脚本长度: {len(script)} 字符 / {len(script.splitlines())} 行")

        # ——— 阶段 4: 执行仿真 ———
        self.presenter.show_progress("execute", f"正在运行 {backend_label} 仿真（可能需要几分钟）...")

        # 提取后端特定参数（如 NNW 需要的网格路径）
        extra_kwargs = {}
        if self.backend == "nnw":
            grid_path = params.get("grid", {}).get("path", "")
            if grid_path:
                from pathlib import Path as _Path
                if _Path(grid_path).exists():
                    extra_kwargs["grid_path"] = grid_path
                    print(f"[i] 网格路径: {grid_path}")
                else:
                    print(f"[!] 网格路径不存在: {grid_path}，将依赖参数文件中的路径")

        exec_result = self.executor.execute(script_path, **extra_kwargs)

        if not exec_result["success"]:
            print(f"\n[X] 仿真执行失败!")
            print(f"   错误: {exec_result.get('error', '未知错误')}")
            if exec_result.get("stderr"):
                print(f"   详细信息:\n{exec_result['stderr'][:500]}")
            return

        # 检查是否需要手动运行
        if exec_result.get("needs_manual_run"):
            note = exec_result.get("note", "")
            job_dir = exec_result.get("job_dir", "")
            print(f"\n[📋] {note}")
            print(f"[📁] 作业目录: {job_dir}")
            return

        print(f"[OK] 仿真计算完成 (耗时 {exec_result['duration']} 秒)")

        # ——— 阶段 5: 结果提取 ———
        self.presenter.show_progress("extract")

        result = self._result_reader_cls.read(exec_result["job_dir"])

        # 将 LLM 提取的项目名称注入结果（供报告使用）
        if result.success and hasattr(self.generator, 'extracted_params'):
            ep = self.generator.extracted_params
            if isinstance(ep, dict) and 'analysis_type' in ep:
                result.results_json['summary']['project_name'] = ep['analysis_type']

        # ——— 阶段 5.5: 生成可视化报告 ———
        report_path = None
        if result.success:
            try:
                from myagent.report import ReportGenerator
                self.presenter.show_progress("report", "生成分析报告...")
                report_path = ReportGenerator(
                    exec_result["job_dir"],
                    solver_name=self.backend_info.get("name", self.backend)
                ).generate()
            except Exception as e:
                print(f"  [!] 报告生成失败 (非致命): {e}")

        # ——— 阶段 6: 呈现结果 ———
        output = self.presenter.present(result, exec_result, report_path)
        print("\n" + output)

        # 将结果摘要存入对话历史
        text_summary = result.get_text_summary()
        self.generator.conversation_history.append({
            "role": "assistant",
            "content": f"仿真完成。结果摘要:\n{text_summary}"
        })

    def _show_extracted_params(self, params: dict):
        """展示提取的参数（简化版）

        Args:
            params: 参数提取结果
        """
        if "error" in params:
            return

        print("\n📋 提取的参数:")

        # 分析类型
        analysis_type = params.get("analysis_type", "")
        if analysis_type:
            print(f"   分析类型: {analysis_type}")

        # 几何
        geometry = params.get("geometry", {})
        if geometry.get("description"):
            print(f"   几何: {geometry['description']}")
        if geometry.get("dimensions"):
            dims = geometry["dimensions"]
            dims_str = ", ".join(f"{k}={v}mm" for k, v in dims.items())
            print(f"   尺寸: {dims_str}")

        # 材料
        material = params.get("material", {})
        if material.get("name"):
            known = " (预定义)" if material.get("known") else ""
            print(f"   材料: {material['name']}{known}")

        # 载荷
        loads = params.get("loads", [])
        if loads:
            for load in loads:
                print(f"   载荷: {load.get('type')} {load.get('magnitude')}N "
                      f"方向{load.get('direction', '?')} @ {load.get('location', '?')}")

        # 边界条件
        bcs = params.get("boundary_conditions", [])
        if bcs:
            for bc in bcs:
                print(f"   约束: {bc.get('type')} @ {bc.get('location', '?')}")

        # 网格
        mesh = params.get("mesh", {})
        if mesh.get("size"):
            print(f"   网格: {mesh['size']}mm, {mesh.get('element_type', 'C3D8R')}")


# ——— Click CLI 入口 ———

@click.command()
@click.option(
    "--model", "-m",
    default=None,
    help="指定使用的 AI 模型（如 deepseek-v3, glm-4, claude-sonnet）"
)
@click.option(
    "--config", "-c",
    default=None,
    help="指定配置文件路径"
)
@click.option(
    "--list-models", "-l",
    is_flag=True,
    help="列出所有可用模型"
)
def cli(model: Optional[str], config: Optional[str], list_models: bool):
    """MyAgent — CAE 自然语言智能助手

    用中文描述仿真需求，自动生成 CAE 脚本并执行分析。
    支持多种 CAE 后端。
    """
    if list_models:
        # 只列出模型，不启动对话
        cfg = get_config(config)
        models = list_llm_models(cfg)
        configured = sum(1 for m in models if cfg.is_model_configured(m["name"]))
        print(f"\n[models] 可用模型 ({len(models)} 个，已配置 {configured} 个):")
        for m in models:
            status = "[OK]" if cfg.is_model_configured(m["name"]) else "[--]"
            print(f"  {status} {m['name']} [{m['provider']}] -> {m['model_id']}")
        print()
        return

    # 启动交互对话
    agent = MyAgent(model_name=model, config_path=config)
    agent.run()


if __name__ == "__main__":
    cli()
