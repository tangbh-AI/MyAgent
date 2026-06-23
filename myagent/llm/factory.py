"""LLM 工厂模块 — 根据配置创建对应的模型实例"""

from typing import Dict, List, Optional

from myagent.config import Config, get_config
from myagent.llm.base import AbstractLLM
from myagent.llm.openai_compat import OpenAICompatLLM
from myagent.llm.anthropic_llm import AnthropicLLM


# 模型提供者注册表
_PROVIDER_REGISTRY = {
    "openai_compat": OpenAICompatLLM,
    "anthropic": AnthropicLLM,
}


def register_provider(name: str, provider_class: type):
    """注册新的模型提供者类型

    Args:
        name: 提供者标识（如 openai_compat, anthropic）
        provider_class: AbstractLLM 的子类
    """
    _PROVIDER_REGISTRY[name] = provider_class


def get_llm(model_name: str, config: Optional[Config] = None) -> AbstractLLM:
    """根据模型名称获取 LLM 实例

    Args:
        model_name: 模型名称（如 deepseek-v3, claude-sonnet）
        config: 配置对象，默认使用全局配置

    Returns:
        LLM 实例

    Raises:
        ValueError: 模型名称未找到或提供者不支持
    """
    if config is None:
        config = get_config()

    model_config = config.get_model_config(model_name)
    if model_config is None:
        available = [m["name"] for m in config.models]
        raise ValueError(
            f"未找到模型 '{model_name}'，"
            f"可用模型: {', '.join(available)}"
        )

    provider = model_config.get("provider", "")
    provider_class = _PROVIDER_REGISTRY.get(provider)

    if provider_class is None:
        raise ValueError(
            f"不支持的模型提供者 '{provider}'，"
            f"支持的类型: {', '.join(_PROVIDER_REGISTRY.keys())}"
        )

    return provider_class(model_name, model_config)


def list_models(config: Optional[Config] = None) -> List[Dict[str, str]]:
    """列出所有可用的模型

    Args:
        config: 配置对象，默认使用全局配置

    Returns:
        模型信息列表 [{"name": ..., "provider": ..., "model_id": ...}, ...]
    """
    if config is None:
        config = get_config()

    return [
        {
            "name": m.get("name", ""),
            "provider": m.get("provider", ""),
            "model_id": m.get("model_id", ""),
        }
        for m in config.models
    ]
