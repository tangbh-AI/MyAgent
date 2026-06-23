"""集成测试：悬臂梁仿真 — 完整 NL→Abaqus 流程

用法: conda activate ccuse && python tests/test_integration.py
"""
import sys
sys.path.insert(0, '.')

from myagent.config import Config, get_config
from myagent.llm.factory import get_llm
from myagent.abaqus.generator import ScriptGenerator
from myagent.abaqus.executor import AbaqusExecutor
from myagent.abaqus.result import ResultReader
from myagent.presenter import Presenter


def main():
    print("=" * 60)
    print("  MyAgent 集成测试 — 悬臂梁静力分析")
    print("=" * 60)

    # 1. 加载配置
    print("\n[1/6] 加载配置...")
    config = get_config()
    model_name = config.default_model
    print(f"  默认模型: {model_name}")

    # 检查 Key 是否配置
    if not config.is_model_configured(model_name):
        print(f"  [X] 模型 '{model_name}' 未配置 API Key，测试中止")
        return
    print(f"  [OK] 模型已配置")

    # 2. 初始化 LLM 和生成器
    print("\n[2/6] 初始化组件...")
    llm = get_llm(model_name, config)
    generator = ScriptGenerator(model_name=model_name)
    executor = AbaqusExecutor(
        abaqus_command=config.abaqus_command,
        work_dir=config.work_dir,
        timeout=config.timeout,
    )
    presenter = Presenter(auto_open_images=False)
    print(f"  [OK] LLM={llm}, WorkDir={config.work_dir}")

    # 3. 参数提取（LLM 调用）
    print("\n[3/6] 分析需求，提取参数...")
    user_input = "分析一个悬臂梁，长1米，矩形截面50mm宽100mm高，钢材料。一端完全固定，自由端受到向下1000N的集中力。做静力分析，网格尺寸10mm。"

    params = generator.extract_parameters(user_input)
    if "error" in params:
        print(f"  [!] 参数提取警告: {params['error']}")
        if "raw_response" in params:
            print(f"  Raw: {params['raw_response'][:300]}")
    else:
        analysis = params.get("analysis_type", "?")
        geo = params.get("geometry", {}).get("description", "?")
        mat = params.get("material", {}).get("name", "?")
        loads = params.get("loads", [])
        bcs = params.get("boundary_conditions", [])
        mesh = params.get("mesh", {}).get("size", "?")
        missing = params.get("missing_parameters", [])
        questions = params.get("questions", [])
        print(f"  分析类型: {analysis}")
        print(f"  几何: {geo}")
        print(f"  材料: {mat}")
        print(f"  载荷: {len(loads)} 个")
        print(f"  约束: {len(bcs)} 个")
        print(f"  网格尺寸: {mesh}mm")
        if missing:
            print(f"  [!] 缺失参数: {missing}")
        if questions:
            print(f"  [?] 追问: {questions}")

    # 4. 生成脚本（LLM 调用）
    print("\n[4/6] 生成 Abaqus 脚本...")
    script, script_path = generator.generate_script(
        user_input=user_input,
        clarified_params="网格尺寸10mm，无需追问，直接生成。",
    )
    print(f"  [OK] 脚本已保存: {script_path}")
    print(f"  脚本长度: {len(script)} 字符 / {len(script.splitlines())} 行")

    # 显示前5行
    for i, line in enumerate(script.splitlines()[:8], 1):
        print(f"  L{i}: {line[:100]}{'...' if len(line) > 100 else ''}")

    # 5. 执行仿真
    print(f"\n[5/6] 执行 Abaqus 仿真...")
    exec_result = executor.execute(script_path)

    if exec_result["success"]:
        print(f"  [OK] 仿真完成 (耗时 {exec_result['duration']} 秒)")
    else:
        print(f"  [X] 仿真失败!")
        print(f"  错误: {exec_result.get('error', '未知')}")
        if exec_result.get("stderr"):
            print(f"  stderr:\n{exec_result['stderr'][:500]}")
        if exec_result.get("stdout"):
            # 只显示尾部
            stdout_lines = exec_result["stdout"].splitlines()
            print(f"  stdout (最后10行):")
            for line in stdout_lines[-10:]:
                print(f"    {line[:150]}")

    # 6. 提取结果
    print(f"\n[6/6] 提取仿真结果...")
    result = ResultReader.read(exec_result["job_dir"])
    output = presenter.present(result, exec_result)
    print(output)

    # 6.5. 生成可视化报告
    from myagent.report import ReportGenerator
    from pathlib import Path
    job_path = Path(exec_result["job_dir"])

    # 检查 paths.json
    paths_file = job_path / "paths.json"
    if paths_file.exists():
        print(f"\n  [OK] paths.json 已生成 ({paths_file.stat().st_size} bytes)")
    else:
        print(f"\n  [!] paths.json 缺失")

    # 生成 HTML 报告
    report_path = ReportGenerator(exec_result["job_dir"]).generate()
    if report_path:
        print(f"  [OK] 分析报告已生成 ({Path(report_path).stat().st_size} bytes)")
    else:
        print(f"  [!] 报告生成失败")

    # 7. 总结
    print("\n" + "=" * 60)
    if exec_result["success"] and result.success:
        print("  [PASS] 集成测试通过！")
        print(f"  最大应力: {result.max_stress} MPa")
        print(f"  最大位移: {result.max_displacement} mm")
        print(f"  paths.json: {'OK' if paths_file.exists() else 'MISSING'}")
        print(f"  可视化报告: {'OK' if report_path else 'MISSING'}")
    else:
        print("  [FAIL] 集成测试失败")
        if result.error:
            print(f"  原因: {result.error}")
    print("=" * 60)


if __name__ == '__main__':
    main()
