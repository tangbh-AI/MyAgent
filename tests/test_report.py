"""测试报告生成器 — paths.json 解析、图表生成、HTML 报告"""
import sys
import json
import os
import tempfile
from pathlib import Path

sys.path.insert(0, '.')

from myagent.report import ReportGenerator


def test_empty_report():
    """测试空目录 — 应返回 None"""
    tmpdir = tempfile.mkdtemp(prefix='myagent_report_')
    rg = ReportGenerator(tmpdir)
    result = rg.generate()
    assert result is None, "空目录应返回 None"
    print(f'[OK] test_empty_report')
    import shutil
    shutil.rmtree(tmpdir)


def test_report_with_data():
    """测试有完整数据的报告生成"""
    tmpdir = tempfile.mkdtemp(prefix='myagent_report_')

    with open(os.path.join(tmpdir, 'results.json'), 'w', encoding='utf-8') as f:
        json.dump({
            "summary": {
                "max_stress_mises": 10.97,
                "max_displacement": 0.39,
                "max_principal_stress": 12.15,
                "min_principal_stress": -12.15,
            },
            "images": [],
        }, f)

    with open(os.path.join(tmpdir, 'paths.json'), 'w', encoding='utf-8') as f:
        json.dump({
            "main_axis": {"direction": "Z", "range": [0.0, 1000.0], "unit": "mm"},
            "curves": {
                "stress_mises": [
                    {"x": 0, "y": 0}, {"x": 100, "y": 2.5},
                    {"x": 500, "y": 6.0}, {"x": 1000, "y": 10.97},
                ],
                "displacement": [
                    {"x": 0, "y": 0}, {"x": 500, "y": 0.1},
                    {"x": 1000, "y": 0.39},
                ],
            }
        }, f)

    rg = ReportGenerator(tmpdir)
    report_path = rg.generate()

    assert report_path is not None
    assert os.path.exists(report_path)
    size = os.path.getsize(report_path)
    assert size > 1000, f"报告应 > 1KB，实际: {size} bytes"

    with open(report_path, 'r', encoding='utf-8') as f:
        content = f.read()

    assert '10.97' in content
    assert '0.39' in content
    assert '<!DOCTYPE html>' in content
    assert 'MyAgent' in content

    print(f'[OK] test_report_with_data: {size} bytes, 包含关键指标和曲线')

    import shutil
    shutil.rmtree(tmpdir)


def test_chart_generation():
    """测试图表 base64 生成"""
    tmpdir = tempfile.mkdtemp(prefix='myagent_report_')

    with open(os.path.join(tmpdir, 'results.json'), 'w', encoding='utf-8') as f:
        json.dump({"summary": {"max_stress_mises": 5.0}, "images": []}, f)

    with open(os.path.join(tmpdir, 'paths.json'), 'w', encoding='utf-8') as f:
        json.dump({
            "main_axis": {"direction": "X", "range": [0, 100], "unit": "mm"},
            "curves": {
                "stress_mises": [{"x": i, "y": float(i)} for i in range(10)],
            }
        }, f)

    rg = ReportGenerator(tmpdir)
    rg._read_data()
    rg._generate_charts()

    assert 'stress_curve' in rg._chart_b64
    b64 = rg._chart_b64['stress_curve']
    assert len(b64) > 100, f"base64 图表应 >100 chars, 实际: {len(b64)}"
    print(f'[OK] test_chart_generation: stress_curve base64 = {len(b64)} chars')

    import shutil
    shutil.rmtree(tmpdir)


def test_metric_cards():
    """测试指标卡片 HTML 生成"""
    rg = ReportGenerator('.')
    summary = {
        "max_stress_mises": 10.97,
        "max_displacement": 0.39,
        "safety_factor": 2.08,
    }
    html = rg._build_metric_cards(summary)
    assert '10.97' in html
    assert 'MPa' in html
    assert '0.39' in html
    assert 'mm' in html
    assert '2.08' in html
    print('[OK] test_metric_cards: 指标卡片 HTML 正确')


if __name__ == '__main__':
    test_empty_report()
    test_report_with_data()
    test_chart_generation()
    test_metric_cards()
    print('\n[PASS] 全部报告模块测试通过！')
