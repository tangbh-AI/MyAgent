"""配置管理模块 — 加载和解析 config.yaml"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class Config:
    """MyAgent 配置管理器

    加载 config.yaml，支持环境变量替换（${VAR_NAME} 语法）。
    敏感信息（API Key）可以通过环境变量覆盖配置文件中的值。
    """

    def __init__(self, config_path: Optional[str] = None):
        """初始化配置

        Args:
            config_path: 配置文件路径，默认为项目根目录下的 config.yaml
        """
        if config_path is None:
            # 默认路径：myagent 包所在目录的上层
            package_dir = Path(__file__).parent
            config_path = str(package_dir.parent / "config.yaml")

        self.config_path = config_path
        self._raw_config: Dict[str, Any] = {}
        self._config: Dict[str, Any] = {}
        self._load()

    def _load(self):
        """加载 YAML 配置文件"""
        config_file = Path(self.config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        with open(config_file, "r", encoding="utf-8") as f:
            self._raw_config = yaml.safe_load(f) or {}

        # 收集未解析的环境变量（仅记录，不在此处警告）
        self._unresolved_vars: list = []

        # 递归替换环境变量
        self._config = self._resolve_env_vars(self._raw_config)

    def _resolve_env_vars(self, obj: Any, _path: str = "") -> Any:
        """递归解析配置中的环境变量引用 ${VAR_NAME}

        检测未设置的环境变量并收集警告信息。

        Args:
            obj: 配置对象（dict, list, str 等）
            _path: 当前配置路径（用于错误提示）

        Returns:
            解析后的对象
        """
        if isinstance(obj, dict):
            return {k: self._resolve_env_vars(v, f"{_path}.{k}" if _path else k)
                    for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._resolve_env_vars(item, f"{_path}[{i}]") for i, item in enumerate(obj)]
        elif isinstance(obj, str):
            # 匹配 ${VAR_NAME} 或 ${VAR_NAME:default_value}
            pattern = r"\$\{(\w+)(?::([^}]*))?\}"
            matches = re.findall(pattern, obj)

            for var_name, default in matches:
                if var_name not in os.environ and not default:
                    self._unresolved_vars.append((_path, var_name))

            def replace_env(match):
                var_name = match.group(1)
                default = match.group(2)
                if default:
                    return os.environ.get(var_name, default)
                value = os.environ.get(var_name)
                if value is None:
                    # 环境变量未设置 — 返回空字符串避免将 ${VAR_NAME} 字面量
                    # 作为 API Key 发送，导致难以诊断的 401 错误
                    return ""
                return value
            return re.sub(pattern, replace_env, obj)
        else:
            return obj

    @property
    def default_model(self) -> str:
        """获取默认模型名称"""
        return self._config.get("default_model", "")

    @property
    def models(self) -> List[Dict[str, Any]]:
        """获取所有模型配置列表"""
        return self._config.get("models", [])

    def get_model_config(self, model_name: str) -> Optional[Dict[str, Any]]:
        """根据名称获取模型配置

        Args:
            model_name: 模型名称（如 deepseek-v3, glm-4 等）

        Returns:
            模型配置字典，未找到返回 None
        """
        for model in self.models:
            if model.get("name") == model_name:
                return model
        return None

    def is_model_configured(self, model_name: str) -> bool:
        """检查模型是否已配置 API Key（可用）

        Args:
            model_name: 模型名称

        Returns:
            True 如果模型存在且 API Key 非空
        """
        cfg = self.get_model_config(model_name)
        if cfg is None:
            return False
        key = cfg.get("api_key", "")
        # key 为空字符串或仍是未解析的 ${...} 占位符
        return bool(key) and not key.startswith("${")

    @property
    def abaqus_config(self) -> Dict[str, Any]:
        """获取 Abaqus 配置"""
        return self._config.get("abaqus", {})

    @property
    def abaqus_command(self) -> str:
        """获取 Abaqus 命令路径"""
        return self.abaqus_config.get("command_path", "abaqus")

    @property
    def abaqus_version(self) -> str:
        """获取 Abaqus 版本"""
        return self.abaqus_config.get("version", "2024")

    @property
    def work_dir(self) -> str:
        """获取工作输出目录"""
        return self.abaqus_config.get("work_dir", "output")

    # ——— NNW-HyFLOW 配置 ———

    @property
    def nnw_config(self) -> Dict[str, Any]:
        """获取 NNW-HyFLOW 配置"""
        return self._config.get("nnw", {})

    @property
    def nnw_install_path(self) -> str:
        """获取 NNW-HyFLOW 安装路径"""
        return self.nnw_config.get("install_path", "")

    @property
    def nnw_solver_path(self) -> str:
        """获取 NNW-HyFLOW 求解器完整路径

        拼接 install_path + bin/ + solver
        """
        install = self.nnw_install_path
        solver = self.nnw_config.get("solver", "X64/PHengLEIv3d0.exe")
        if install:
            return str(Path(install) / "bin" / solver)
        return solver

    # ——— fealpy 配置 ———

    @property
    def fealpy_config(self) -> Dict[str, Any]:
        """获取 fealpy 配置"""
        return self._config.get("fealpy", {})

    @property
    def fealpy_python_path(self) -> str:
        """获取 fealpy 使用的 Python 路径

        空字符串 = 自动检测当前环境的 Python (sys.executable)
        """
        val = self.fealpy_config.get("python_path", "")
        if not val:
            import sys
            return sys.executable
        return val

    @property
    def fealpy_work_dir(self) -> str:
        """获取 fealpy 输出目录"""
        return self.fealpy_config.get("work_dir", "output")

    @property
    def fealpy_timeout(self) -> int:
        """获取 fealpy 仿真超时时间（秒）"""
        return self.fealpy_config.get("timeout", 3600)

    @property
    def simulation_config(self) -> Dict[str, Any]:
        """获取仿真默认设置"""
        return self._config.get("simulation", {})

    # ——— CAE 后端选择 ———

    @property
    def cae_backend(self) -> str:
        """获取当前 CAE 后端名称"""
        cae_cfg = self._config.get("cae", {})
        return cae_cfg.get("backend", "abaqus")

    @property
    def default_mesh_size(self) -> float:
        """获取默认网格尺寸"""
        return self.simulation_config.get("default_mesh_size", 5.0)

    @property
    def timeout(self) -> int:
        """获取仿真超时时间（秒）"""
        return self.simulation_config.get("timeout", 3600)

    # ——— 配置写入方法 ———

    def set_model_api_key(self, model_name: str, api_key: str) -> bool:
        """设置指定模型的 API Key（直接写入原始配置，不经过环境变量解析）

        Args:
            model_name: 模型名称
            api_key: 新的 API Key

        Returns:
            True 成功，False 模型未找到
        """
        models = self._raw_config.get("models", [])
        for model in models:
            if model.get("name") == model_name:
                model["api_key"] = api_key
                self._save()
                # 同步更新已解析的配置
                resolved_models = self._config.get("models", [])
                for rm in resolved_models:
                    if rm.get("name") == model_name:
                        rm["api_key"] = api_key
                        break
                return True
        return False

    def add_model(
        self,
        name: str,
        provider: str,
        model_id: str,
        base_url: str = "",
        api_key: str = ""
    ) -> bool:
        """添加新的模型配置

        Args:
            name: 模型名称（唯一标识）
            provider: 提供者类型 (openai_compat / anthropic)
            model_id: 实际 API 模型 ID
            base_url: API 端点 URL
            api_key: API Key（可为空字符串，后续设置）

        Returns:
            True 成功，False 模型名已存在
        """
        # 检查是否已存在
        models = self._raw_config.get("models", [])
        for model in models:
            if model.get("name") == name:
                return False

        new_model = {
            "name": name,
            "provider": provider,
            "api_key": api_key,
            "model_id": model_id,
        }
        if base_url:
            new_model["base_url"] = base_url
        else:
            # anthropic provider 不需要 base_url（用官方端点）
            # openai_compat 通常需要
            pass

        models.append(new_model)
        self._save()

        # 同步到已解析配置
        self._config.setdefault("models", []).append(
            self._resolve_env_vars(new_model)
        )
        return True

    def set_default_model(self, model_name: str):
        """更改默认模型

        Args:
            model_name: 新的默认模型名称
        """
        self._raw_config["default_model"] = model_name
        self._config["default_model"] = model_name
        self._save()

    def set_cae_backend(self, backend: str):
        """设置当前 CAE 后端并持久化到 config.yaml

        参照 set_default_model() 模式，操作 _raw_config 确保环境变量引用
        在写回时保持完整。

        Args:
            backend: 后端名称（如 "abaqus"）
        """
        cae = self._raw_config.setdefault("cae", {})
        cae["backend"] = backend
        self._config.setdefault("cae", {})["backend"] = backend
        self._save()

    def _save(self):
        """将当前原始配置写回 config.yaml"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                self._raw_config,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )
        # 清除全局缓存，下次 get_config 会重新加载
        global _config_instance
        _config_instance = None

    def reload(self):
        """重新加载配置文件"""
        self._load()


# 全局配置实例（懒加载）
_config_instance: Optional[Config] = None


def get_config(config_path: Optional[str] = None) -> Config:
    """获取全局配置实例

    Args:
        config_path: 配置文件路径，仅首次调用时生效

    Returns:
        Config 实例
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_path)
    return _config_instance
