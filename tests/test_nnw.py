"""NNW-HyFLOW 后端测试

测试 NNW 后端的注册、工厂创建、参数提取、结果读取等功能。
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 确保项目路径在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

# 触发 CAE 后端注册（必须在工厂调用之前导入）
import myagent.abaqus  # noqa: F401
import myagent.nnw     # noqa: F401

from myagent.cae import (
    list_backends,
    create_generator,
    create_executor,
    get_result_reader,
    get_backend_info,
)


class TestNNWBackendRegistration:
    """测试 NNW 后端注册"""

    def test_nnw_registered(self):
        """验证 NNW 后端已注册到工厂"""
        backends = list_backends()
        assert "nnw" in backends, f"NNW 未注册，可用后端: {backends}"

    def test_nnw_backend_info(self):
        """验证 NNW 后端信息"""
        info = get_backend_info("nnw")
        assert "name" in info
        assert info["name"] == "NNW-HyFLOW"

    def test_nnw_generator_factory(self):
        """验证可以创建 NNW 生成器"""
        from myagent.config import get_config
        config = get_config()
        model_name = config.default_model
        if not config.is_model_configured(model_name):
            pytest.skip(f"模型 '{model_name}' 未配置 API Key")

        gen = create_generator("nnw", model_name, config)
        assert gen is not None
        assert hasattr(gen, "extract_parameters")
        assert hasattr(gen, "generate_script")

    def test_nnw_executor_factory(self):
        """验证可以创建 NNW 执行器"""
        from myagent.config import get_config
        config = get_config()

        exe = create_executor("nnw", config)
        assert exe is not None
        assert hasattr(exe, "execute")

    def test_nnw_result_reader(self):
        """验证可以获取 NNW 结果读取器"""
        reader_cls = get_result_reader("nnw")
        assert reader_cls is not None
        assert hasattr(reader_cls, "read")


class TestNNWResultReader:
    """测试 NNW 结果读取器 — 解析 aircoef.dat 和 res.dat"""

    @staticmethod
    def _create_mock_aircoef(output_dir: str) -> str:
        """创建模拟的 aircoef.dat 文件"""
        content = """TITLE = "PHengLEI Air Coefficients"
VARIABLES = "iter" "CL" "CD" "CZ" "Cm"
1 0.1234 0.0123 0.0001 0.0012
2 0.2345 0.0234 0.0002 0.0023
3 0.3456 0.0345 0.0003 0.0034
4 0.4012 0.0401 0.0004 0.0040
5 0.4234 0.0423 0.0004 0.0042
6 0.4356 0.0436 0.0005 0.0044
7 0.4423 0.0443 0.0005 0.0045
8 0.4467 0.0447 0.0005 0.0046
9 0.4490 0.0450 0.0005 0.0046
10 0.4504 0.0451 0.0005 0.0047
"""
        filepath = Path(output_dir) / "results" / "aircoef.dat"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        return str(filepath.parent.parent)

    @staticmethod
    def _create_mock_residual(output_dir: str) -> str:
        """创建模拟的 res.dat 文件"""
        content = """1 1.0e+0
2 5.0e-1
3 2.5e-1
4 1.0e-1
5 5.0e-2
6 2.5e-2
7 1.0e-2
8 5.0e-3
9 2.5e-3
10 1.0e-3
"""
        results_dir = Path(output_dir) / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        filepath = results_dir / "res.dat"
        filepath.write_text(content, encoding="utf-8")
        return str(results_dir.parent)

    def test_read_empty_dir(self):
        """测试读取空目录"""
        from myagent.nnw.result import ResultReader, SimulationResult

        with tempfile.TemporaryDirectory() as tmpdir:
            result = ResultReader.read(tmpdir)
            assert not result.success
            assert result.error is not None

    def test_read_aircoef(self):
        """测试读取 aircoef.dat"""
        from myagent.nnw.result import ResultReader

        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = self._create_mock_aircoef(tmpdir)
            result = ResultReader.read(job_dir)

            assert result.success
            assert "aircoef" in result.raw_data
            aircoef = result.raw_data["aircoef"]
            assert aircoef["nrows"] == 10
            assert "CL" in aircoef["values"]
            # CL 最终值约 0.45
            assert 0.44 < aircoef["values"]["CL"][-1] < 0.46

    def test_read_residual(self):
        """测试读取 res.dat"""
        from myagent.nnw.result import ResultReader

        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = self._create_mock_residual(tmpdir)
            result = ResultReader.read(job_dir)

            # 有 res.dat 但没有 aircoef.dat 时也会标记 success
            # (因为有输出文件且 res.dat 被成功解析)
            assert "residual" in result.raw_data or result.success

    def test_text_summary(self):
        """测试 CFD 文本摘要生成"""
        from myagent.nnw.result import ResultReader, SimulationResult

        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = self._create_mock_aircoef(tmpdir)
            result = ResultReader.read(job_dir)

            summary_text = result.get_text_summary()
            assert "升力系数 CL" in summary_text or "cl" in summary_text.lower()
            assert "阻力系数 CD" in summary_text or "cd" in summary_text.lower()

    def test_aircoef_parsing_format(self):
        """测试 aircoef.dat 多列格式解析"""
        from myagent.nnw.result import ResultReader

        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir) / "results"
            results_dir.mkdir(parents=True, exist_ok=True)

            # 模拟 NNW 的完整输出格式 (iter, CL, CD)
            content = "\n".join(
                f"{i} {0.1*i:.4f} {0.01*i:.4f}"
                for i in range(1, 21)
            )
            (results_dir / "aircoef.dat").write_text(content, encoding="utf-8")

            result = ResultReader.read(str(Path(tmpdir)))
            assert result.success
            aircoef = result.raw_data["aircoef"]
            assert aircoef["nrows"] == 20


class TestNNWKnowledge:
    """测试 NNW 知识库"""

    def test_system_prompt_not_empty(self):
        """验证 system prompt 非空"""
        from myagent.nnw.knowledge import get_nnw_system_prompt
        prompt = get_nnw_system_prompt()
        assert len(prompt) > 1000
        assert "NNW-HyFLOW" in prompt
        assert "hypara" in prompt.lower()

    def test_scenario_templates(self):
        """验证工况模板存在"""
        from myagent.nnw.knowledge import SCENARIO_TEMPLATES
        assert "subsonic" in SCENARIO_TEMPLATES
        assert "supersonic" in SCENARIO_TEMPLATES
        assert "hypersonic" in SCENARIO_TEMPLATES


class TestNNWConfig:
    """测试 NNW 配置属性"""

    def test_nnw_config_exists(self):
        """验证 config.yaml 包含 nnw 配置段"""
        from myagent.config import get_config
        config = get_config()
        nnw_cfg = config.nnw_config
        assert "install_path" in nnw_cfg, f"nnw 配置中缺少 install_path: {nnw_cfg}"
        assert "solver" in nnw_cfg, "nnw 配置中缺少 solver"

    def test_nnw_solver_path(self):
        """验证 nnw_solver_path 拼接正确"""
        from myagent.config import get_config
        config = get_config()
        path = config.nnw_solver_path
        assert "PHengLEIv3d0" in path, f"求解器路径不包含 PHengLEIv3d0: {path}"
        assert path.endswith(".exe"), f"求解器路径不是 .exe: {path}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
