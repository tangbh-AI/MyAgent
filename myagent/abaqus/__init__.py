"""Abaqus 操作层 — 脚本生成、执行、结果提取"""

from myagent.abaqus.generator import ScriptGenerator
from myagent.abaqus.executor import AbaqusExecutor
from myagent.abaqus.result import ResultReader, SimulationResult
from myagent.abaqus.knowledge import get_abaqus_system_prompt

# 注册 Abaqus 后端到 CAE 工厂
from myagent.cae.factory import register_backend


def _create_abaqus_generator(model_name, config):
    return ScriptGenerator(model_name=model_name)


def _create_abaqus_executor(config):
    return AbaqusExecutor(
        abaqus_command=config.abaqus_command,
        work_dir=config.work_dir,
        timeout=config.timeout,
    )


register_backend(
    name="abaqus",
    generator_factory=_create_abaqus_generator,
    executor_factory=_create_abaqus_executor,
    result_reader_cls=ResultReader,
    display_name="Abaqus",
)

__all__ = [
    "ScriptGenerator",
    "AbaqusExecutor",
    "ResultReader",
    "SimulationResult",
    "get_abaqus_system_prompt",
]
