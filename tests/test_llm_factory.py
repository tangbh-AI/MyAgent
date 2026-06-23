"""测试 LLM 工厂和提供者 — 覆盖模型创建、异常处理"""
import os
import sys
sys.path.insert(0, '.')

from myagent.config import Config
from myagent.llm.factory import get_llm, list_models
from myagent.llm.base import AbstractLLM
from myagent.llm.openai_compat import OpenAICompatLLM
from myagent.llm.anthropic_llm import AnthropicLLM

# ——— 设置模拟环境变量（供测试 LLM 实例化使用） ———
_NEEDED_VARS = ['GLM_API_KEY', 'DEEPSEEK_API_KEY', 'ANTHROPIC_API_KEY', 'QWEN_API_KEY']
_for_test_vars = {}
for _v in _NEEDED_VARS:
    if _v not in os.environ:
        os.environ[_v] = f'test-dummy-{_v.lower()}'
        _for_test_vars[_v] = True


def test_list_models_format():
    """测试模型列表返回格式"""
    c = Config('config.yaml')
    models = list_models(c)
    assert len(models) == 10
    for m in models:
        assert isinstance(m['name'], str) and m['name'], "name 必须是非空字符串"
        assert m['provider'] in ('openai_compat', 'anthropic'), \
            f"provider 必须是 openai_compat 或 anthropic，实际: {m['provider']}"
        assert isinstance(m['model_id'], str) and m['model_id'], "model_id 必须是非空字符串"
    print(f'✅ test_list_models_format: {len(models)} 个模型格式正确')


def test_get_llm_unknown_model():
    """测试请求不存在的模型时抛出 ValueError"""
    c = Config('config.yaml')
    try:
        get_llm('nonexistent-model-xyz', c)
        assert False, "应该抛出 ValueError"
    except ValueError as e:
        assert '未找到模型' in str(e), f"错误消息应包含'未找到模型'，实际: {e}"
        print(f'✅ test_get_llm_unknown_model: 正确抛出 ValueError')


def test_get_llm_openai_compat():
    """测试创建 OpenAI 兼容实例"""
    c = Config('config.yaml')
    # GLM-4 使用 openai_compat provider
    llm = get_llm('glm-4', c)
    assert isinstance(llm, OpenAICompatLLM), \
        f"应为 OpenAICompatLLM 实例，实际: {type(llm).__name__}"
    assert llm.model_name == 'glm-4'
    assert 'glm-4' in llm.model_id
    print(f'✅ test_get_llm_openai_compat: {llm}')


def test_get_llm_anthropic():
    """测试创建 Anthropic 实例"""
    c = Config('config.yaml')
    # claude-sonnet 使用 anthropic provider
    llm = get_llm('claude-sonnet', c)
    assert isinstance(llm, AnthropicLLM), \
        f"应为 AnthropicLLM 实例，实际: {type(llm).__name__}"
    assert llm.model_name == 'claude-sonnet'
    assert 'claude-sonnet' in llm.model_id
    print(f'✅ test_get_llm_anthropic: {llm}')


def test_get_llm_deepseek_anthropic():
    """测试 DeepSeek Anthropic 兼容端点（自定义 base_url）"""
    c = Config('config.yaml')
    llm = get_llm('deepseek-v4-pro-anthropic', c)
    assert isinstance(llm, AnthropicLLM)
    assert llm.base_url == 'https://api.deepseek.com/anthropic', \
        f"base_url 应为 DeepSeek Anthropic 端点，实际: {llm.base_url}"
    print(f'✅ test_get_llm_deepseek_anthropic: base_url={llm.base_url}')


def test_get_llm_deepseek_openai():
    """测试 DeepSeek OpenAI 兼容端点"""
    c = Config('config.yaml')
    llm = get_llm('deepseek-v4-pro', c)
    assert isinstance(llm, OpenAICompatLLM)
    assert llm.base_url == 'https://api.deepseek.com', \
        f"base_url 应为 DeepSeek API 端点，实际: {llm.base_url}"
    assert llm.model_id == 'deepseek-v4-pro'
    print(f'✅ test_get_llm_deepseek_openai: base_url={llm.base_url}, model_id={llm.model_id}')


def test_abstract_llm_repr():
    """测试 AbstractLLM 的 __repr__"""
    llm = get_llm('glm-4')
    r = repr(llm)
    assert 'OpenAICompatLLM' in r
    assert 'glm-4' in r
    print(f'✅ test_abstract_llm_repr: {r}')


def test_get_llm_deepseek_r1():
    """测试 DeepSeek R1 推理模型"""
    c = Config('config.yaml')
    llm = get_llm('deepseek-r1', c)
    assert isinstance(llm, OpenAICompatLLM)
    assert llm.model_id == 'deepseek-reasoner', \
        f"model_id 应为 deepseek-reasoner，实际: {llm.model_id}"
    print(f'✅ test_get_llm_deepseek_r1: model_id={llm.model_id}')


if __name__ == '__main__':
    test_list_models_format()
    test_get_llm_unknown_model()
    test_get_llm_openai_compat()
    test_get_llm_anthropic()
    test_get_llm_deepseek_anthropic()
    test_get_llm_deepseek_openai()
    test_abstract_llm_repr()
    test_get_llm_deepseek_r1()
    print('\n🎉 全部 LLM 工厂测试通过！')
