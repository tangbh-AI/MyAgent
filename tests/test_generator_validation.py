"""测试 _validate_script() — LLM 脚本生成语法验证

覆盖：合法脚本、截断检测、括号不匹配、空脚本等场景。
"""

import pytest
from myagent.abaqus.generator import ScriptGenerator as AbaqusScriptGenerator


# ——— Abaqus 生成器验证 ———

ABAQUS_VALID_SCRIPT = """from abaqus import *
from abaqusConstants import *

mdb.Model(name='Model-1')
print('done')
"""


class TestAbaqusValidateScript:
    """测试 AbaqusScriptGenerator._validate_script()"""

    def test_valid_script_passes(self):
        """合法脚本通过验证"""
        AbaqusScriptGenerator._validate_script(ABAQUS_VALID_SCRIPT, "test")

    def test_empty_script_raises(self):
        """空脚本抛出异常"""
        with pytest.raises(SyntaxError, match="空脚本"):
            AbaqusScriptGenerator._validate_script("", "test")

    def test_truncated_for_keyword(self):
        """截断特征: 末行仅有 'for'"""
        code = "from abaqus import *\nfor"
        with pytest.raises(SyntaxError, match="截断") as exc_info:
            AbaqusScriptGenerator._validate_script(code, "test")
        assert "语句体缺失" in str(exc_info.value)

    def test_truncated_def_keyword(self):
        """截断特征: 末行仅有 'def'"""
        code = "from abaqus import *\ndef"
        with pytest.raises(SyntaxError, match="截断") as exc_info:
            AbaqusScriptGenerator._validate_script(code, "test")
        assert "语句体缺失" in str(exc_info.value)

    def test_unmatched_parens(self):
        """截断特征: 括号不匹配"""
        code = "mdb.Model(name='Model-1'\nprint('done')"
        with pytest.raises(SyntaxError, match="截断") as exc_info:
            AbaqusScriptGenerator._validate_script(code, "test")
        assert "括号不匹配" in str(exc_info.value)
