"""测试结果呈现器 — 覆盖 Presenter 的输出格式"""
import sys
sys.path.insert(0, '.')

from myagent.presenter import Presenter
from myagent.abaqus.result import SimulationResult, ResultReader


def test_presenter_init():
    """测试 Presenter 初始化"""
    p = Presenter(auto_open_images=False)
    assert p.auto_open_images is False

    p2 = Presenter(auto_open_images=True)
    assert p2.auto_open_images is True
    print('✅ test_presenter_init: 初始化参数正确')


def test_present_successful_result():
    """测试成功结果的呈现输出"""
    r = SimulationResult('/tmp/myagent_job')
    r.success = True
    r.results_json = {
        "summary": {
            "max_stress_mises": 150.0,
            "max_displacement": 3.2,
            "safety_factor": 1.67,
        },
        "images": [],
    }
    r.images = ["stress_contour.png", "displacement_contour.png"]

    exec_info = {
        "success": True,
        "duration": 45.3,
        "job_dir": "/tmp/myagent_job",
    }

    p = Presenter(auto_open_images=False)
    output = p.present(r, exec_info)

    # 验证输出包含关键信息
    assert '[result] 仿真结果' in output
    assert '45.3' in output
    assert '150.00' in output
    assert '3.20' in output
    assert '1.67' in output
    assert 'stress_contour.png' in output
    assert 'displacement_contour.png' in output
    print('✅ test_present_successful_result: 输出包含所有关键数据')


def test_present_failed_result():
    """测试失败结果的呈现输出"""
    r = SimulationResult('/tmp/myagent_job')
    r.success = False
    r.error = "求解器收敛失败"

    exec_info = {
        "success": False,
        "duration": 12.0,
        "job_dir": "/tmp/myagent_job",
        "error": "Abaqus Error: Too many attempts",
    }

    p = Presenter()
    output = p.present(r, exec_info)

    assert '[X] 仿真失败' in output
    assert '求解器收敛失败' in output
    assert 'Too many attempts' in output
    print('✅ test_present_failed_result: 正确呈现失败信息')


def test_show_progress():
    """测试进度显示（验证各阶段不报错）"""
    stages = ['generate', 'execute', 'extract', 'analyze']
    for stage in stages:
        Presenter.show_progress(stage)

    # 测试自定义消息
    Presenter.show_progress('execute', '正在运行...')

    # 测试未知阶段（不应报错，应显示 stage 名）
    Presenter.show_progress('unknown_stage')
    print('✅ test_show_progress: 所有阶段消息正常')


def test_show_welcome():
    """测试欢迎信息显示"""
    Presenter.show_welcome()
    print('✅ test_show_welcome: 欢迎信息正常')


def test_show_help():
    """测试帮助信息显示"""
    Presenter.show_help()
    print('✅ test_show_help: 帮助信息正常')


def test_present_minimal_result():
    """测试最小化结果（无图片、最小数据）"""
    r = SimulationResult('/tmp/minimal')
    r.success = True
    r.results_json = {
        "summary": {
            "max_stress_mises": 50.0,
        },
    }
    r.images = []

    exec_info = {
        "success": True,
        "duration": 0.5,
        "job_dir": "/tmp/minimal",
    }

    p = Presenter()
    output = p.present(r, exec_info)

    assert '[result] 仿真结果' in output
    assert '50.00' in output
    print('✅ test_present_minimal_result: 最小化结果正常呈现')


def test_text_summary_from_presenter():
    """通过 Presenter 间接测试文本摘要集成"""
    r = SimulationResult('/tmp/integration')
    r.success = True
    r.results_json = {
        "summary": {
            "max_stress_mises": 200.0,
            "max_displacement": 5.0,
            "total_force": 10000.0,
        },
        "images": [],
    }
    r.images = ["contour.png"]

    text_summary = r.get_text_summary()
    assert '200.00' in text_summary
    assert '5.00' in text_summary
    assert 'contour.png' in text_summary
    print('✅ test_text_summary_from_presenter: 集成文本摘要正确')


if __name__ == '__main__':
    test_presenter_init()
    test_present_successful_result()
    test_present_failed_result()
    test_show_progress()
    test_show_welcome()
    test_show_help()
    test_present_minimal_result()
    test_text_summary_from_presenter()
    print('\n🎉 全部呈现器测试通过！')
