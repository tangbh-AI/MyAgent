"""测试结果读取器 — 覆盖 SimulationResult 和 ResultReader"""
import sys
import json
import tempfile
import os
from pathlib import Path

sys.path.insert(0, '.')

from myagent.abaqus.result import SimulationResult, ResultReader


def test_empty_result():
    """测试空结果对象"""
    r = SimulationResult('/tmp/test_job')
    assert r.success is False
    assert r.summary == {}
    assert r.max_stress is None
    assert r.max_displacement is None
    assert r.images == []
    print('✅ test_empty_result: 空结果初始状态正确')


def test_successful_result():
    """测试成功结果对象"""
    r = SimulationResult('/tmp/test_job')
    r.success = True
    r.results_json = {
        "summary": {
            "max_stress_mises": 120.5,
            "max_displacement": 2.3,
            "max_principal_stress": 145.0,
            "min_principal_stress": -15.0,
            "safety_factor": 2.08,
        },
        "images": ["stress_contour.png", "displacement_contour.png"],
    }
    r.images = ["stress_contour.png", "displacement_contour.png"]

    assert r.max_stress == 120.5
    assert r.max_displacement == 2.3
    assert r.summary.get("safety_factor") == 2.08
    print(f'✅ test_successful_result: stress={r.max_stress}, disp={r.max_displacement}, '
          f'safety={r.summary.get("safety_factor")}')


def test_read_missing_dir():
    """测试读取不存在的目录"""
    result = ResultReader.read('/tmp/nonexistent_myagent_dir_12345')
    assert result.success is False
    assert '不存在' in result.error
    print(f'✅ test_read_missing_dir: 正确报告目录不存在')


def test_read_with_results_json():
    """测试读取正常的 results.json"""
    # 创建临时目录和文件
    tmpdir = tempfile.mkdtemp(prefix='myagent_test_')
    try:
        # 创建 results.json
        data = {
            "summary": {
                "max_stress_mises": 250.0,
                "max_displacement": 1.5,
            },
            "images": [],
        }
        with open(os.path.join(tmpdir, 'results.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f)

        # 创建模拟图片
        Path(os.path.join(tmpdir, 'stress_contour.png')).touch()
        Path(os.path.join(tmpdir, 'displacement_contour.png')).touch()

        result = ResultReader.read(tmpdir)
        assert result.success is True
        assert result.max_stress == 250.0
        assert result.max_displacement == 1.5
        assert 'stress_contour.png' in result.images
        assert 'displacement_contour.png' in result.images
        print(f'✅ test_read_with_results_json: images={result.images}')
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_read_json_with_error():
    """测试 results.json 中包含错误标记"""
    tmpdir = tempfile.mkdtemp(prefix='myagent_test_')
    try:
        data = {
            "summary": {},
            "images": [],
            "error": "ODB 文件损坏，无法读取",
        }
        with open(os.path.join(tmpdir, 'results.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f)

        result = ResultReader.read(tmpdir)
        assert result.success is False
        assert 'ODB 文件损坏' in result.error
        print(f'✅ test_read_json_with_error: 正确检测到错误标记')
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_text_summary_success():
    """测试成功结果的文本摘要"""
    r = SimulationResult('/tmp/test')
    r.success = True
    r.results_json = {
        "summary": {
            "max_stress_mises": 310.5,
            "max_displacement": 4.2,
            "max_principal_stress": 380.0,
            "min_principal_stress": -50.0,
            "total_force": 5000.0,
            "safety_factor": 0.81,
            "additional": {
                "最大塑性应变": "0.0023",
                "屈曲模态": "1阶",
            },
        },
        "images": ["stress.png", "disp.png"],
    }
    r.images = ["stress.png", "disp.png"]

    text = r.get_text_summary()
    assert '310.50' in text
    assert '4.20' in text
    assert '0.81' in text
    assert '5000.00' in text
    assert 'stress.png' in text
    assert 'disp.png' in text
    assert '最大塑性应变' in text
    print(f'✅ test_text_summary_success: 摘要包含所有字段')


def test_text_summary_failure():
    """测试失败结果的文本摘要"""
    r = SimulationResult('/tmp/test')
    r.success = False
    r.error = "未找到 results.json; 无 ODB"

    text = r.get_text_summary()
    assert '失败' in text
    assert '未找到 results.json' in text
    print(f'✅ test_text_summary_failure: 正确显示失败信息')


def test_text_summary_empty():
    """测试空摘要的文本"""
    r = SimulationResult('/tmp/test')
    r.success = True
    r.results_json = {"summary": {}, "images": []}
    r.images = []

    text = r.get_text_summary()
    assert '暂无' in text
    print(f'✅ test_text_summary_empty: 正确显示空数据提示')


def test_diagnose_missing_results():
    """测试诊断信息生成"""
    tmpdir = tempfile.mkdtemp(prefix='myagent_test_')
    try:
        result = ResultReader.read(tmpdir)
        assert result.success is False
        assert '未找到 results.json' in result.error
        # 空目录应包含诊断信息
        assert '无 ODB' in result.error
        print(f'✅ test_diagnose_missing_results: 诊断={result.error}')
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_result_image_paths():
    """测试图片路径属性"""
    r = SimulationResult('/tmp/job_dir')
    r.images = ['a.png', 'b.png']
    paths = r.image_paths
    assert len(paths) == 2
    assert paths[0].endswith('a.png')
    assert paths[1].endswith('b.png')
    print(f'✅ test_result_image_paths: {paths}')


if __name__ == '__main__':
    test_empty_result()
    test_successful_result()
    test_read_missing_dir()
    test_read_with_results_json()
    test_read_json_with_error()
    test_text_summary_success()
    test_text_summary_failure()
    test_text_summary_empty()
    test_diagnose_missing_results()
    test_result_image_paths()
    print('\n🎉 全部结果读取器测试通过！')
