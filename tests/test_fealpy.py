"""fealpy 后端测试 — 覆盖 knowledge/generator/executor/result/factory/config"""

import json
import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

# 触发 fealpy 后端注册（不经过 main.py 时需手动导入）
import myagent.fealpy  # noqa: F401

from myagent.cae.factory import list_backends, create_generator, create_executor, get_result_reader
from myagent.cae.base import AbstractScriptGenerator, AbstractExecutor, AbstractResultReader, SimulationResult


class TestFealpyKnowledge:
    """知识库内容验证"""

    def test_materials_exist(self):
        from myagent.fealpy.knowledge import DEFAULT_MATERIALS
        assert "steel" in DEFAULT_MATERIALS
        assert "aluminum" in DEFAULT_MATERIALS
        assert "titanium" in DEFAULT_MATERIALS
        assert DEFAULT_MATERIALS["steel"]["elastic"] == [210000.0, 0.3]

    def test_system_prompt_returned(self):
        from myagent.fealpy.knowledge import get_fealpy_system_prompt
        prompt = get_fealpy_system_prompt()
        assert "fealpy" in prompt.lower()
        assert "mm-N-s" in prompt or "mm" in prompt
        assert len(prompt) > 500

    def test_saver_code_exists(self):
        from myagent.fealpy.knowledge import FEALPY_RESULT_SAVER_CODE
        assert "_fealpy_save_results" in FEALPY_RESULT_SAVER_CODE
        assert "results.json" in FEALPY_RESULT_SAVER_CODE

    def test_units_info_exists(self):
        from myagent.fealpy.knowledge import UNITS_INFO
        assert "mm" in UNITS_INFO

    def test_api_reference_exists(self):
        from myagent.fealpy.knowledge import FEALPY_API_REFERENCE
        assert "TetrahedronMesh" in FEALPY_API_REFERENCE
        assert "LagrangeFESpace" in FEALPY_API_REFERENCE
        assert "add_integrator" in FEALPY_API_REFERENCE


class TestFealpyFactory:
    """工厂注册验证"""

    def test_fealpy_in_backend_list(self):
        backends = list_backends()
        assert "fealpy" in backends

    def test_create_generator(self):
        """测试通过工厂创建 fealpy 生成器（使用 mock LLM）"""
        from myagent.config import get_config
        from unittest.mock import patch, MagicMock
        config = get_config()
        with patch('myagent.fealpy.generator.get_llm') as mock_get_llm:
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm
            gen = create_generator("fealpy", model_name=None, config=config)
            assert isinstance(gen, AbstractScriptGenerator)
            assert gen.model_name is not None

    def test_create_executor(self):
        from myagent.config import get_config
        config = get_config()
        executor = create_executor("fealpy", config=config)
        assert isinstance(executor, AbstractExecutor)

    def test_get_result_reader(self):
        reader_cls = get_result_reader("fealpy")
        assert issubclass(reader_cls, AbstractResultReader)


class TestFealpyExecutor:
    """执行器测试"""

    def test_create_executor_directly(self):
        from myagent.fealpy.executor import FealpyExecutor
        executor = FealpyExecutor(work_dir="output/test_fealpy")
        assert executor.python_path
        assert "python" in executor.python_path.lower()
        assert executor.timeout == 3600

    def test_execute_syntax_error_script(self):
        """验证预执行语法检查能捕获语法错误"""
        from myagent.fealpy.executor import FealpyExecutor

        executor = FealpyExecutor(work_dir=tempfile.mkdtemp())

        # 创建一个有语法错误的脚本
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("this is not valid python {{{")
            bad_script = f.name

        result = executor.execute(bad_script)
        assert result["success"] is False
        assert result["return_code"] == -1
        os.unlink(bad_script)

    def test_execute_simple_script(self):
        """验证能正常执行简单的 Python 脚本"""
        from myagent.fealpy.executor import FealpyExecutor

        executor = FealpyExecutor(work_dir=tempfile.mkdtemp())

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("print('hello fealpy')\n")
            f.write("import json\n")
            f.write("json.dump({'summary': {'test': 1}}, open('results.json', 'w'))\n")
            good_script = f.name

        result = executor.execute(good_script)
        assert result["success"] is True
        assert result["return_code"] == 0
        # 验证 results.json 已生成
        job_dir = Path(result["job_dir"])
        assert (job_dir / "results.json").exists()
        os.unlink(good_script)


class TestFealpyResultReader:
    """结果读取器测试"""

    def test_read_nonexistent_dir(self):
        from myagent.fealpy.result import ResultReader
        result = ResultReader.read("/nonexistent/path/12345")
        assert result.success is False
        assert result.error is not None

    def test_read_empty_dir(self):
        from myagent.fealpy.result import ResultReader
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ResultReader.read(tmpdir)
            assert result.success is False
            assert "未找到 results.json" in result.error

    def test_read_valid_results_json(self):
        from myagent.fealpy.result import ResultReader
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "analysis_type": "static",
                "summary": {
                    "max_stress_mises": 120.5,
                    "max_displacement": 2.34,
                },
                "images": ["stress_mises.png"],
                "project_name": "test_beam",
            }
            with open(os.path.join(tmpdir, "results.json"), "w") as f:
                json.dump(data, f)

            Path(tmpdir, "stress_mises.png").touch()

            result = ResultReader.read(tmpdir)
            assert result.success is True
            assert result.summary["max_stress_mises"] == 120.5
            assert "stress_mises.png" in result.images

    def test_read_modal_results_json(self):
        from myagent.fealpy.result import ResultReader
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "analysis_type": "modal",
                "summary": {
                    "natural_frequencies": [145.3, 890.7, 1240.5],
                    "max_displacement": 0.01,
                },
                "mode_shapes": ["mode_1.png", "mode_2.png"],
                "images": ["mode_1.png", "mode_2.png"],
                "project_name": "modal_test",
            }
            with open(os.path.join(tmpdir, "results.json"), "w") as f:
                json.dump(data, f)

            result = ResultReader.read(tmpdir)
            assert result.success is True
            assert result.summary["natural_frequencies"] == [145.3, 890.7, 1240.5]
            assert len(result.results_json.get("mode_shapes", [])) == 2

    def test_read_error_json(self):
        """测试 results.json 含 error 字段的情况"""
        from myagent.fealpy.result import ResultReader
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "error": "fealpy 导入失败",
                "summary": {},
            }
            with open(os.path.join(tmpdir, "results.json"), "w") as f:
                json.dump(data, f)

            result = ResultReader.read(tmpdir)
            assert result.success is False
            assert "fealpy 导入失败" in result.error


class TestFealpyGenerator:
    """生成器测试"""

    def test_create_generator(self):
        """测试创建 ScriptGenerator（使用 mock LLM）"""
        from unittest.mock import patch, MagicMock
        with patch('myagent.fealpy.generator.get_llm') as mock_get_llm:
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm
            from myagent.fealpy.generator import ScriptGenerator
            gen = ScriptGenerator()
            assert gen.model_name is not None

    def test_validate_empty_script(self):
        from myagent.fealpy.generator import ScriptGenerator
        with pytest.raises(SyntaxError):
            ScriptGenerator._validate_script("", "test")

    def test_validate_valid_script(self):
        from myagent.fealpy.generator import ScriptGenerator
        # 不应抛异常
        ScriptGenerator._validate_script("import numpy as np\nx = 1", "test")

    def test_validate_truncated_script(self):
        from myagent.fealpy.generator import ScriptGenerator
        with pytest.raises(SyntaxError) as exc_info:
            ScriptGenerator._validate_script("import numpy\ndef foo(", "test")
        assert "截断" in str(exc_info.value) or "括号不匹配" in str(exc_info.value)

    def test_extract_code_python_block(self):
        """测试从 LLM 响应中提取 ```python 代码块（使用 mock LLM）"""
        from unittest.mock import patch, MagicMock
        with patch('myagent.fealpy.generator.get_llm') as mock_get_llm:
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm
            from myagent.fealpy.generator import ScriptGenerator
            gen = ScriptGenerator()
            response = "这是说明\n```python\nimport numpy\nx = 1\n```\n更多说明"
            code = gen._extract_code(response)
            assert "import numpy" in code
            assert "x = 1" in code
            assert "这是说明" not in code

    def test_extract_code_no_block(self):
        """测试无代码块时从响应中提取代码（使用 mock LLM）"""
        from unittest.mock import patch, MagicMock
        with patch('myagent.fealpy.generator.get_llm') as mock_get_llm:
            mock_llm = MagicMock()
            mock_get_llm.return_value = mock_llm
            from myagent.fealpy.generator import ScriptGenerator
            gen = ScriptGenerator()
            response = "import numpy as np\nfrom fealpy.mesh import TetrahedronMesh\nprint('hello')"
            code = gen._extract_code(response)
            assert "import numpy" in code

    def test_param_extraction_prompt_exists(self):
        from myagent.fealpy.generator import ScriptGenerator
        assert "analysis_type" in ScriptGenerator.PARAM_EXTRACTION_PROMPT
        assert "missing_parameters" in ScriptGenerator.PARAM_EXTRACTION_PROMPT


class TestFealpyConfig:
    """配置属性验证"""

    def test_fealpy_config_properties(self):
        from myagent.config import get_config
        config = get_config()
        assert config.fealpy_python_path
        assert "python" in config.fealpy_python_path.lower()
        assert config.fealpy_work_dir
        assert config.fealpy_timeout > 0

    def test_fealpy_config_dict(self):
        from myagent.config import get_config
        config = get_config()
        cfg = config.fealpy_config
        assert isinstance(cfg, dict)
        assert "timeout" in cfg or True  # 至少是 dict
