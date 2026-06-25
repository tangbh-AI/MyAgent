"""CAE 后端工厂 — 注册表 + 工厂函数

参照 LLM 层的 _PROVIDER_REGISTRY 模式：
- 每个 CAE 后端注册三个组件：generator_factory、executor_factory、result_reader_cls
- 通过后端名称（如 "abaqus"）创建对应组件
"""

from typing import Any, Callable, Dict, List, Type

from myagent.cae.base import (
    AbstractScriptGenerator,
    AbstractExecutor,
    AbstractResultReader,
)

# 后端注册表
# key: 后端名称（如 "abaqus"）
# value: {
#     "name": str,                   # 后端显示名称
#     "generator_factory": Callable, # (model_name, config) -> AbstractScriptGenerator
#     "executor_factory": Callable,  # (config) -> AbstractExecutor
#     "result_reader_cls": Type[AbstractResultReader],
# }
_BACKEND_REGISTRY: Dict[str, dict] = {}


def register_backend(
    name: str,
    generator_factory: Callable,
    executor_factory: Callable,
    result_reader_cls: Type[AbstractResultReader],
    display_name: str = "",
):
    """注册一个 CAE 后端

    Args:
        name: 后端名称（如 "abaqus"），用于配置中切换
        generator_factory: (model_name, config) -> AbstractScriptGenerator
        executor_factory: (config) -> AbstractExecutor
        result_reader_cls: AbstractResultReader 的子类
        display_name: 显示名称，默认为 name
    """
    _BACKEND_REGISTRY[name] = {
        "name": display_name or name,
        "generator_factory": generator_factory,
        "executor_factory": executor_factory,
        "result_reader_cls": result_reader_cls,
    }


def create_generator(
    backend: str,
    model_name: str,
    config: Any,
) -> AbstractScriptGenerator:
    """通过工厂创建脚本生成器

    Args:
        backend: 后端名称
        model_name: LLM 模型名称
        config: Config 对象

    Returns:
        AbstractScriptGenerator 实例

    Raises:
        ValueError: 后端未注册
    """
    if backend not in _BACKEND_REGISTRY:
        available = list_backends()
        raise ValueError(
            f"未知的 CAE 后端: '{backend}'，可用后端: {available}"
        )
    factory = _BACKEND_REGISTRY[backend]["generator_factory"]
    return factory(model_name, config)


def create_executor(
    backend: str,
    config: Any,
) -> AbstractExecutor:
    """通过工厂创建仿真执行器

    Args:
        backend: 后端名称
        config: Config 对象

    Returns:
        AbstractExecutor 实例

    Raises:
        ValueError: 后端未注册
    """
    if backend not in _BACKEND_REGISTRY:
        available = list_backends()
        raise ValueError(
            f"未知的 CAE 后端: '{backend}'，可用后端: {available}"
        )
    factory = _BACKEND_REGISTRY[backend]["executor_factory"]
    return factory(config)


def get_result_reader(backend: str) -> Type[AbstractResultReader]:
    """获取结果读取器类

    Args:
        backend: 后端名称

    Returns:
        AbstractResultReader 的子类

    Raises:
        ValueError: 后端未注册
    """
    if backend not in _BACKEND_REGISTRY:
        available = list_backends()
        raise ValueError(
            f"未知的 CAE 后端: '{backend}'，可用后端: {available}"
        )
    return _BACKEND_REGISTRY[backend]["result_reader_cls"]


def list_backends() -> List[str]:
    """列出所有已注册的 CAE 后端名称"""
    return list(_BACKEND_REGISTRY.keys())


def get_backend_info(backend: str) -> Dict:
    """获取后端信息

    Args:
        backend: 后端名称

    Returns:
        包含 name 等信息的字典
    """
    if backend not in _BACKEND_REGISTRY:
        return {"name": backend}
    return {"name": _BACKEND_REGISTRY[backend]["name"]}
