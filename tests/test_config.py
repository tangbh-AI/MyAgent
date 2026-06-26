"""测试配置加载 — 覆盖 Config 类的全部功能"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, '.')

from myagent.config import Config


def test_config_load():
    """基本配置加载测试"""
    c = Config('config.yaml')
    assert c.default_model == 'deepseek-v4-pro', f"默认模型应为 deepseek-v4-pro，实际: {c.default_model}"
    assert len(c.models) == 10, f"应有 10 个模型，实际: {len(c.models)}"
    assert str(c.abaqus_version) == '2024'
    assert c.timeout == 3600
    assert c.default_mesh_size == 5.0
    print(f'✅ test_config_load: 默认模型={c.default_model}, 模型数={len(c.models)}, '
          f'Abaqus={c.abaqus_command}, 超时={c.timeout}s, 网格={c.default_mesh_size}mm')


def test_env_var_resolution():
    """测试环境变量解析 ${VAR_NAME}"""
    # 设置临时环境变量
    os.environ['TEST_MYAGENT_KEY'] = 'sk-test-12345678'
    os.environ['TEST_MYAGENT_URL'] = 'https://test.api.com/v1'

    # 创建临时配置文件
    temp_config = tempfile.NamedTemporaryFile(
        mode='w', suffix='.yaml', delete=False, encoding='utf-8')
    temp_config.write("""
default_model: test-model
models:
  - name: test-model
    provider: openai_compat
    api_key: ${TEST_MYAGENT_KEY}
    base_url: ${TEST_MYAGENT_URL}
    model_id: test-model-v1
  - name: unset-model
    provider: openai_compat
    api_key: ${NONEXISTENT_VAR}
    base_url: https://default.api.com
    model_id: unset-v1
abaqus:
  command_path: /fake/abaqus
  version: "2024"
    """)
    temp_config.close()

    try:
        c = Config(temp_config.name)

        # 已设置的环境变量应正确解析
        test_model = c.get_model_config('test-model')
        assert test_model is not None
        assert test_model['api_key'] == 'sk-test-12345678', \
            f"环境变量应被解析，实际: {test_model['api_key']}"
        assert test_model['base_url'] == 'https://test.api.com/v1'

        # 未设置的环境变量应被替换为空字符串
        unset_model = c.get_model_config('unset-model')
        assert unset_model is not None
        assert unset_model['api_key'] == '', \
            f"未设置的环境变量应返回空字符串，实际: '{unset_model['api_key']}'"

        print('✅ test_env_var_resolution: 环境变量解析正确')
    finally:
        os.unlink(temp_config.name)
        del os.environ['TEST_MYAGENT_KEY']
        del os.environ['TEST_MYAGENT_URL']


def test_is_model_configured():
    """测试模型是否已配置 API Key 的判断"""
    c = Config('config.yaml')

    # 使用环境变量引用的模型 — 如果环境变量未设置，应显示未配置
    deepseek = c.is_model_configured('deepseek-v4-pro')
    # 如果 DEEPSEEK_API_KEY 环境变量已设置，则为 True；否则为 False
    expected = 'DEEPSEEK_API_KEY' in os.environ
    assert deepseek == expected, \
        f"deepseek-v4-pro 配置状态应为 {expected}，实际: {deepseek}"

    # 不存在的模型
    assert c.is_model_configured('nonexistent-model') is False

    print(f'✅ test_is_model_configured: deepseek-v4-pro={"已配置" if deepseek else "未配置(需设置环境变量)"}')


def test_abaqus_properties():
    """测试 Abaqus 配置属性"""
    c = Config('config.yaml')
    assert 'abaqus' in c.abaqus_command.lower()
    assert str(c.abaqus_version) == '2024'
    print(f'✅ test_abaqus_properties: command={c.abaqus_command}, version={c.abaqus_version}')


def test_simulation_defaults():
    """测试仿真默认值"""
    c = Config('config.yaml')
    assert c.default_mesh_size == 5.0
    assert c.timeout == 3600
    print(f'✅ test_simulation_defaults: mesh_size={c.default_mesh_size}, timeout={c.timeout}')


def test_model_factory():
    """测试模型工厂"""
    from myagent.llm.factory import list_models
    models = list_models()
    assert len(models) == 10
    for m in models:
        assert 'name' in m
        assert 'provider' in m
        assert 'model_id' in m
        assert m['provider'] in ('openai_compat', 'anthropic')
    print(f'✅ test_model_factory: {len(models)} 个模型，格式正确')


def test_get_model_config():
    """测试获取指定模型配置"""
    c = Config('config.yaml')

    # 存在的模型
    m = c.get_model_config('glm-4')
    assert m is not None
    assert m['provider'] == 'openai_compat'
    assert 'glm-4' in m['model_id']

    # 不存在的模型
    assert c.get_model_config('nonexistent') is None

    print(f'✅ test_get_model_config: glm-4 配置获取正常')


def test_cae_backend_default():
    """测试 CAE 后端默认值"""
    c = Config('config.yaml')
    assert c.cae_backend in ('abaqus', 'fealpy', 'nnw'), f"后端应为可用后端之一，实际: {c.cae_backend}"
    print(f'✅ test_cae_backend_default: 默认后端={c.cae_backend}')


def test_set_cae_backend():
    """测试动态切换 CAE 后端并持久化"""
    temp_config = tempfile.NamedTemporaryFile(
        mode='w', suffix='.yaml', delete=False, encoding='utf-8')
    temp_config.write("""
default_model: test
models: []
cae:
  backend: abaqus
""")
    temp_config.close()

    try:
        c = Config(temp_config.name)
        assert c.cae_backend == 'abaqus'

        # 切换到 test_backend
        c.set_cae_backend('test_backend')
        assert c.cae_backend == 'test_backend'

        # 从磁盘重新读取验证持久化
        c2 = Config(temp_config.name)
        assert c2.cae_backend == 'test_backend', \
            f"持久化失败，预期 test_backend，实际: {c2.cae_backend}"

        # 切换回 abaqus
        c2.set_cae_backend('abaqus')
        assert c2.cae_backend == 'abaqus'

        c3 = Config(temp_config.name)
        assert c3.cae_backend == 'abaqus'

        print('✅ test_set_cae_backend: 动态切换 + 持久化正常')
    finally:
        os.unlink(temp_config.name)


if __name__ == '__main__':
    test_config_load()
    test_env_var_resolution()
    test_is_model_configured()
    test_abaqus_properties()
    test_simulation_defaults()
    test_model_factory()
    test_get_model_config()
    test_cae_backend_default()
    test_set_cae_backend()
    print('\n🎉 全部配置测试通过！')
