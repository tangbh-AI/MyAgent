"""CAE 工厂测试 — 后端注册 + 工厂函数"""

import sys
sys.path.insert(0, '.')

# 导入注册后端
import myagent.abaqus  # noqa: F401

from myagent.cae.factory import (
    register_backend, create_generator, create_executor,
    get_result_reader, list_backends, get_backend_info,
)
from myagent.cae.base import (
    SimulationResult, AbstractScriptGenerator,
    AbstractExecutor, AbstractResultReader,
)
from myagent.config import get_config


def test_list_backends():
    """测试列出所有后端"""
    backends = list_backends()
    assert 'abaqus' in backends
    assert len(backends) >= 1
    print(f'✅ test_list_backends: {backends}')


def test_get_backend_info():
    """测试获取后端信息"""
    abaqus_info = get_backend_info('abaqus')
    assert abaqus_info['name'] == 'Abaqus'

    # 未知后端返回 backend 名称本身
    unknown_info = get_backend_info('unknown_backend')
    assert unknown_info['name'] == 'unknown_backend'

    print(f'✅ test_get_backend_info: Abaqus={abaqus_info}')


def test_create_abaqus_generator():
    """测试创建 Abaqus 脚本生成器"""
    config = get_config()
    generator = create_generator('abaqus', 'deepseek-v4-pro', config)
    assert isinstance(generator, AbstractScriptGenerator)
    print(f'✅ test_create_abaqus_generator: {type(generator).__name__}')


def test_create_abaqus_executor():
    """测试创建 Abaqus 执行器"""
    config = get_config()
    executor = create_executor('abaqus', config)
    assert isinstance(executor, AbstractExecutor)
    print(f'✅ test_create_abaqus_executor: {type(executor).__name__}')


def test_get_result_readers():
    """测试获取结果读取器"""
    abaqus_reader = get_result_reader('abaqus')
    assert issubclass(abaqus_reader, AbstractResultReader)

    print(f'✅ test_get_result_readers: Abaqus={abaqus_reader.__name__}')


def test_unknown_backend():
    """测试未知后端抛出异常"""
    config = get_config()
    try:
        create_generator('unknown', 'deepseek-v4-pro', config)
        assert False, '应该抛出 ValueError'
    except ValueError as e:
        assert 'unknown' in str(e)
    print(f'✅ test_unknown_backend: 正确拒绝未知后端')


def test_simulation_result_basic():
    """测试 SimulationResult 基本功能"""
    r = SimulationResult('/tmp/test')
    assert r.success is False
    assert r.max_stress is None
    assert r.max_displacement is None
    assert r.images == []

    r.success = True
    r.results_json = {
        "summary": {"max_stress_mises": 100.0, "max_displacement": 2.0}
    }
    r.images = ['a.png']

    assert r.max_stress == 100.0
    assert r.max_displacement == 2.0

    text = r.get_text_summary()
    assert '100.00' in text
    assert '2.00' in text
    print('✅ test_simulation_result_basic: SimulationResult 工作正常')


def test_register_custom_backend():
    """测试注册自定义后端（验证注册机制可扩展）"""
    # 创建一个简单的存根
    class CustomGenerator(AbstractScriptGenerator):
        def extract_parameters(self, user_input):
            return {}
        def generate_script(self, user_input, clarified_params=None):
            return ("# test", "/tmp/test.py")
        def switch_model(self, model_name):
            pass

    class CustomExecutor(AbstractExecutor):
        def execute(self, script_path, **kwargs):
            return {"success": True, "job_dir": "/tmp", "stdout": "",
                    "stderr": "", "return_code": 0, "duration": 0, "error": None}

    class CustomResultReader(AbstractResultReader):
        @staticmethod
        def read(job_dir):
            r = SimulationResult(job_dir)
            r.success = True
            return r

    # 注册
    register_backend(
        "test_backend",
        lambda model, cfg: CustomGenerator(),
        lambda cfg: CustomExecutor(),
        CustomResultReader,
        display_name="测试后端",
    )

    assert 'test_backend' in list_backends()

    config = get_config()
    gen = create_generator('test_backend', 'any', config)
    assert isinstance(gen, CustomGenerator)

    exec = create_executor('test_backend', config)
    assert isinstance(exec, CustomExecutor)

    reader = get_result_reader('test_backend')
    assert issubclass(reader, AbstractResultReader)

    # 清理
    from myagent.cae.factory import _BACKEND_REGISTRY
    del _BACKEND_REGISTRY['test_backend']
    print('✅ test_register_custom_backend: 自定义后端注册/工厂/清理正常')


if __name__ == '__main__':
    test_list_backends()
    test_get_backend_info()
    test_create_abaqus_generator()
    test_create_abaqus_executor()
    test_get_result_readers()
    test_unknown_backend()
    test_simulation_result_basic()
    test_register_custom_backend()
    print('\n🎉 CAE 工厂全部测试通过！')
