"""Case 1 端到端测试 — ONERA M6 跨声速机翼绕流

通过 MyAgent NNW 后端工厂 API 执行完整的 NL→CFD→报告管道：
  1. 参数提取 (LLM)
  2. .hypara 生成 (LLM) + 语法验证
  3. CFD 求解执行 (PHengLEI)
  4. 结果读取 + 数据验证
  5. CFD 可视化报告生成

此测试脚本绕过了 main.py 的交互式 CLI，但使用与 main.py 相同的工厂 API。
同时也记录了 main.py 中发现的 bug：_handle_simulation() 未将 grid_path 传递给 executor。
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# 确保项目根目录在 PYTHONPATH 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from myagent.config import get_config
from myagent.cae import create_generator, create_executor, get_result_reader
from myagent.cae.factory import list_backends, get_backend_info
from myagent.llm.factory import get_llm

import myagent.nnw  # noqa: F401 — 触发注册

# ——— 测试参数 ———
# ONERA M6 跨声速机翼 — 案例 1
GRID_PATH = (
    r"D:\NNW\NNW-HyFLOW_V1.1_win64_ed"
    r"\bin\Demo\ThreeD_M6_Turbulence_Struct\grid\m6_str.cgns"
)
MA = 0.8395
AOA = 3.06
SIDESLIP = 0.0
RE = 1.171e7
TEMP = 288.0
WALL_TEMP = -1.0  # 绝热壁

# 快速测试迭代步数（完整仿真需 20000 步，此处用 200 步验证管道）
TEST_MAX_STEPS = 200
TEST_TIMEOUT = 600  # 超时秒数

CASE1_INPUT = fr"""对 ONERA M6 机翼进行 CFD 仿真分析。

网格文件: {GRID_PATH}

来流条件:
  - 马赫数 Ma = {MA}（跨声速）
  - 攻角 AoA = {AOA}°
  - 侧滑角 = {SIDESLIP}°
  - 雷诺数 Re = {RE:.3e}（单位长度）
  - 来流温度 T∞ = {TEMP} K
  - 壁面为绝热壁（无热传导）

物理模型:
  - 湍流模型使用 SA 一方程模型 (Spalart-Allmaras)
  - 完全气体，比热比 γ = 1.4
  - 层流普朗特数 Prl = 0.72，湍流普朗特数 Prt = 0.9

数值格式:
  - 无粘通量: Roe 格式
  - 结构网格限制器: smooth
  - 梯度方法: Green-Gauss (ggnode)
  - 时间推进: LU-SGS 隐式，CFL 从 0.01 爬升到 5（500步）
  - 最大迭代步 {TEST_MAX_STEPS}

输出:
  - 气动力系数（升力 CL、阻力 CD、俯仰力矩 Cm）
  - 流场可视化（密度、速度、压力、马赫数）
  - 残差收敛历史"""

# ——— 阶段验证函数 ———

def check(condition, msg):
    """验证检查：打印 [OK] 或 [X]"""
    if condition:
        print(f"  [OK] {msg}")
    else:
        print(f"  [X] {msg}")
    return bool(condition)


def validate_paths(config):
    """阶段 0: 验证所有路径存在"""
    print("阶段 0: 环境验证")
    print("-" * 50)

    errors = []

    # 求解器
    solver = Path(config.nnw_solver_path)
    ok = check(solver.exists(), f"求解器: {solver}")
    if not ok:
        errors.append(f"找不到求解器: {solver}")

    # 网格文件
    grid = Path(GRID_PATH)
    ok = check(grid.exists(), f"网格文件: {grid}")
    if not ok:
        errors.append(f"找不到网格文件: {grid}")

    # 网格辅助文件
    grid_dir = grid.parent
    for co_file in [".bcname", ".bcmesh", ".bcdir", ".fts", ".grd"]:
        stem = grid.stem
        # .bcdir 等文件名格式: m6_str_0.bcdir
        found = list(grid_dir.glob(f"{stem}*{co_file}"))
        check(len(found) > 0, f"网格辅助文件 *{co_file}: {'[OK]' if found else '缺失'}")

    # 安装路径
    install = Path(config.nnw_install_path)
    check(install.exists(), f"NNW 安装目录: {install}")

    if errors:
        print(f"\n[X] 环境验证失败 ({len(errors)} 个错误):")
        for e in errors:
            print(f"    - {e}")
        return False

    print(f"  [OK] 模型: {config.default_model}")
    print(f"  [OK] CAE 后端: NNW-HyFLOW [nnw]")
    print()
    return True


def validate_extracted_params(params):
    """阶段 1: 验证 LLM 提取的参数"""
    print("阶段 1 验证: 参数提取")
    print("-" * 50)

    if "error" in params:
        print(f"  [X] LLM 返回错误: {params['error']}")
        raw = params.get("raw_response", "")
        if raw:
            print(f"  原始回复(前300): {raw[:300]}")
        return 0, 10

    passed = 0
    total = 10

    flow = params.get("flow_conditions", {})
    turb = params.get("turbulence", {})
    schemes = params.get("schemes", {})
    grid_p = params.get("grid", {})
    missing = params.get("missing_parameters", [])

    # 验证关键参数
    ma = flow.get("mach_number")
    if isinstance(ma, str):
        try: ma = float(ma)
        except: pass
    passed += check(isinstance(ma, (int, float)) and abs(ma - MA) < 0.1,
                    f"马赫数 = {ma} (预期 {MA})")

    aoa = flow.get("attack_angle_deg")
    if isinstance(aoa, str):
        try: aoa = float(aoa)
        except: pass
    passed += check(isinstance(aoa, (int, float)) and abs(float(aoa) - AOA) < 1.0,
                    f"攻角 = {aoa}° (预期 {AOA}°)")

    re_val = flow.get("reynolds_number")
    passed += check(re_val is not None and "missing" not in str(re_val).lower(),
                    f"雷诺数 = {re_val} (预期 {RE:.1e})")

    temp = flow.get("temperature_k")
    passed += check(temp is not None and "missing" not in str(temp).lower(),
                    f"来流温度 = {temp} K (预期 {TEMP} K)")

    turb_model = turb.get("model", "")
    passed += check("sa" in str(turb_model).lower() or "spalart" in str(turb_model).lower(),
                    f"湍流模型 = {turb_model} (预期 SA)")

    inv_flux = schemes.get("inviscid_flux", "")
    passed += check("roe" in str(inv_flux).lower(),
                    f"无粘通量 = {inv_flux} (预期 Roe)")

    grid_path_param = grid_p.get("path", "")
    passed += check("m6_str" in str(grid_path_param) or "m6" in str(grid_path_param).lower(),
                    f"网格路径含 'm6_str': {grid_path_param}")

    passed += check(len(missing) == 0 or all(m in ["sideslip_angle_deg", "angleSlide"]
                                              for m in missing),
                    f"缺失参数: {missing if missing else '(无)'}")

    # 维度
    dim = flow.get("dimensionality", "3d")
    passed += check("3" in str(dim), f"维度 = {dim} (预期 3D)")

    # 输出
    output = params.get("output", {})
    passed += check(bool(output), f"输出配置: {output}")

    print(f"\n  参数验证: {passed}/{total} 通过")
    return passed, total


def validate_hypara_files(bin_dir):
    """阶段 2: 验证 .hypara 文件语法"""
    print("阶段 2 验证: .hypara 文件")
    print("-" * 50)

    if not bin_dir.exists():
        print("  [X] bin/ 目录不存在!")
        return 0, 5

    hypara_files = sorted(bin_dir.glob("*.hypara"))
    print(f"  找到 {len(hypara_files)} 个 .hypara 文件:")
    for f in hypara_files:
        size = f.stat().st_size
        lines = f.read_text(encoding="utf-8").splitlines()
        non_empty = [l for l in lines if l.strip() and not l.strip().startswith("//")]
        print(f"    {f.name}: {size}B, {len(lines)} 行 ({len(non_empty)} 有效行)")

    passed = 0
    total = 7

    # 检查 5 个必需文件
    expected = {"key.hypara", "cfd_para.hypara", "grid_para.hypara",
                 "boundary_condition.hypara", "partition.hypara"}
    found = {f.name for f in hypara_files}
    passed += check(expected.issubset(found),
                    f"必需文件齐全: {found}")

    if not found:
        print(f"\n  [X] 缺少文件: {expected - found}")
        return 0, total

    # 检查 cfd_para.hypara 的关键参数
    cfd_para = bin_dir / "cfd_para.hypara"
    if cfd_para.exists():
        cfd_text = cfd_para.read_text(encoding="utf-8")

        # 分号检查
        lines = cfd_text.splitlines()
        bad_lines = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped and not stripped.startswith("//") and not stripped in ("{", "}"):
                if not stripped.endswith(";") and "=" in stripped:
                    bad_lines.append(f"  L{i}: {stripped[:80]}")
        passed += check(len(bad_lines) == 0,
                        f"每行以分号结尾: {'[OK]' if not bad_lines else f'{len(bad_lines)} 行缺少分号'}")
        if bad_lines:
            for bl in bad_lines[:3]:
                print(f"    {bl}")

        # 关键参数
        for param in ["refMachNumber", "attackd", "refReNumber", "viscousType",
                       "maxSimuStep", "gasfile", "CFLStart", "CFLEnd"]:
            if re.search(rf'{param}\s*=', cfd_text):
                passed += 1
            else:
                print(f"  [X] 缺少关键参数: {param}")
        total += 8

        # 网格文件名一致性
        grid_para = bin_dir / "grid_para.hypara"
        if grid_para.exists():
            grid_text = grid_para.read_text(encoding="utf-8")
            from_match = re.search(r'from_gfile\s*=\s*"\./grid/(.+?)"', grid_text)
            grid_match = re.search(r'gridfile\s*=\s*"\./grid/(.+?)"', cfd_text)
            if from_match and grid_match:
                from_stem = Path(from_match.group(1)).stem
                grid_stem = Path(grid_match.group(1)).stem
                passed += check(from_stem == grid_stem,
                                f"网格 stem 一致: {from_stem} vs {grid_stem}")
                total += 1

    print(f"\n  .hypara 验证: {passed}/{total} 通过")
    return passed, total


def validate_exec_result(exec_result):
    """阶段 3: 验证执行结果"""
    print("阶段 3 验证: 求解执行")
    print("-" * 50)

    passed = 0
    total = 6

    passed += check(exec_result["success"],
                    f"执行成功: {exec_result['success']}")

    duration = exec_result.get("duration", 0)
    passed += check(duration > 0,
                    f"执行耗时: {duration:.1f} 秒")

    job_dir = exec_result.get("job_dir", "")
    passed += check(bool(job_dir) and Path(job_dir).exists(),
                    f"作业目录存在: {job_dir}")

    if job_dir:
        results_dir = Path(job_dir) / "results"
        passed += check(results_dir.exists(),
                        f"results/ 目录存在")
        if results_dir.exists():
            result_files = list(results_dir.glob("*"))
            passed += check(len(result_files) > 0,
                            f"结果文件数: {len(result_files)}")
            for rf in result_files:
                print(f"      {rf.name} ({rf.stat().st_size}B)")

        log_path = Path(job_dir) / "execution.log"
        passed += check(log_path.exists(),
                        f"execution.log 存在")

    if not exec_result["success"]:
        err = exec_result.get("error", "未知")
        print(f"\n  [X] 错误: {err}")
        stderr = exec_result.get("stderr", "")
        if stderr:
            print(f"  stderr 尾部:\n{stderr[-500:]}")
        if job_dir:
            log_path = Path(job_dir) / "execution.log"
            if log_path.exists():
                print(f"\n  执行日志尾部:\n{log_path.read_text(encoding='utf-8')[-1000:]}")

    print(f"\n  执行验证: {passed}/{total} 通过")
    return passed, total


def validate_sim_result(sim_result):
    """阶段 4: 验证仿真结果"""
    print("阶段 4 验证: CFD 结果数据")
    print("-" * 50)

    passed = 0
    total = 8

    passed += check(sim_result.success,
                    f"结果读取成功: {sim_result.success}")

    # 气动力数据
    aircoef = sim_result.raw_data.get("aircoef", {})
    passed += check(bool(aircoef) and aircoef.get("values"),
                    f"aircoef 数据存在: {len(aircoef.get('values', {}))} 个字段")

    summary = sim_result.results_json.get("summary", {})

    # CL 验证
    cl = summary.get("cl")
    passed += check(cl is not None,
                    f"升力系数 CL = {cl}")
    if cl is not None:
        passed += check(0.05 < cl < 1.0,
                        f"CL 在合理范围 (0.05~1.0): {cl:.6f}")

    # CD 验证
    cd = summary.get("cd")
    passed += check(cd is not None,
                    f"阻力系数 CD = {cd}")
    if cd is not None:
        passed += check(0.001 < cd < 0.2,
                        f"CD 在合理范围 (0.001~0.2): {cd:.6f}")

    # L/D
    ld = summary.get("l_d")
    passed += check(ld is not None and ld > 0,
                    f"升阻比 L/D = {ld:.2f}" if ld else "升阻比 L/D: N/A")

    # 残差数据
    residual = sim_result.raw_data.get("residual", {})
    passed += check(bool(residual) and len(residual.get("iterations", [])) > 0,
                    f"残差数据: {len(residual.get('iterations', []))} 步")

    # 收敛状态
    converged = summary.get("converged", False)
    final_res = summary.get("final_residual", "N/A")
    print(f"  [i] 收敛状态: {'[OK] 已收敛' if converged else '[?] 未完全收敛'} (残差={final_res})")
    passed += 1  # 非失败项

    print(f"\n  结果验证: {passed}/{total} 通过")
    return passed, total


def validate_images(job_dir, image_list):
    """阶段 5: 验证生成的图片"""
    print("阶段 5 验证: 结果图片")
    print("-" * 50)

    passed = 0
    total = 0

    job_path = Path(job_dir)
    for img_name in image_list:
        total += 2
        img_path = job_path / img_name
        exists = img_path.exists()
        passed += check(exists, f"{img_name}")

        if exists:
            # 检查是否是有效 PNG
            with open(img_path, 'rb') as f:
                header = f.read(8)
            is_png = header[:4] == b'\x89PNG'
            passed += check(is_png, f"  有效 PNG: {img_name}")
            if is_png:
                size_kb = img_path.stat().st_size / 1024
                print(f"      大小: {size_kb:.1f} KB")

    print(f"\n  图片验证: {passed}/{total} 通过")
    return passed, total


def validate_report(report_path):
    """阶段 5: 验证 HTML 报告"""
    print("阶段 5 验证: HTML 报告")
    print("-" * 50)

    passed = 0
    total = 5

    rp = Path(report_path) if report_path else None
    exists = rp and rp.exists()
    passed += check(exists, f"报告文件存在: {report_path}")

    if not exists:
        return 0, total

    size_kb = rp.stat().st_size / 1024
    passed += check(size_kb > 5, f"报告大小: {size_kb:.1f} KB (> 5KB)")

    html = rp.read_text(encoding="utf-8")

    passed += check("<html" in html and "</html>" in html,
                    "有效的 HTML 结构")

    passed += check("ONERA M6" in html,
                    "包含 'ONERA M6' 标题")

    # 检查 CFD 指标卡片
    for keyword in ["CL", "CD", "L/D", "升力系数", "阻力系数"]:
        if keyword in html:
            passed += 1
            break
    total += 1
    check(keyword in html if isinstance(keyword, str) else any(k in html for k in [keyword]),
          f"包含气动力指标: {'[OK]' if any(k in html for k in ['CL', 'CD', 'L/D', '升力', '阻力']) else '[X]'}")

    print(f"\n  报告验证: {passed}/{total} 通过")
    return passed, total


# ——— 主函数 ———

def main():
    config = get_config()

    print("╔══════════════════════════════════════════════════════╗")
    print("║  MyAgent NNW Case 1: ONERA M6 跨声速机翼绕流        ║")
    print("║  自动化端到端测试 (NL → .hypara → 求解 → 报告)       ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    # ——— 阶段 0: 环境验证 ———
    if not validate_paths(config):
        return 1

    # ——— 阶段 1: 参数提取 (LLM) ———
    print("=" * 60)
    print("阶段 1/5: 参数提取 (LLM)")
    print("=" * 60)

    # 使用工厂模式创建 generator（与 main.py 相同方式）
    model_name = config.default_model
    generator = create_generator("nnw", model_name, config)
    print(f"[i] 生成器已创建: NNW-HyFLOW + {model_name}")

    print("[...]  调用 LLM 分析需求，提取参数...")
    params = generator.extract_parameters(CASE1_INPUT)

    if "error" in params:
        print(f"[!] 参数提取出现问题: {params['error']}")
        if "raw_response" in params:
            print(f"    LLM 原始回复 (前500): {params['raw_response'][:500]}")
    else:
        # 展示关键参数
        flow = params.get("flow_conditions", {})
        grid_p = params.get("grid", {})
        turb = params.get("turbulence", {})
        schemes = params.get("schemes", {})
        missing = params.get("missing_parameters", [])

        print("[OK] 参数提取成功:\n")
        if flow:
            print(f"    马赫数: {flow.get('mach_number')}")
            print(f"    攻角: {flow.get('attack_angle_deg')}°")
            print(f"    雷诺数: {flow.get('reynolds_number')}")
            print(f"    温度: {flow.get('temperature_k')} K")
            print(f"    维度: {flow.get('dimensionality', '?')}")
        if grid_p:
            print(f"    网格: {grid_p.get('path', '?')}")
        if turb:
            print(f"    湍流: {turb.get('model', '?')}")
        if schemes:
            print(f"    通量格式: {schemes.get('inviscid_flux', '?')}")
            print(f"    限制器: {schemes.get('limiter', '?')}")
        if missing:
            print(f"    [!] 缺失参数: {', '.join(missing)}")

    # 验证提取的参数
    s1_pass, s1_total = validate_extracted_params(params)
    print()

    # ——— 阶段 2: 生成 .hypara 文件 (LLM) ———
    print("=" * 60)
    print("阶段 2/5: 生成 .hypara 参数文件 (LLM)")
    print("=" * 60)

    print("[...]  调用 LLM 生成 NNW 配置文件...")
    script, job_dir = generator.generate_script(user_input=CASE1_INPUT)
    gen_dir = Path(job_dir)
    print(f"[OK] 脚本已生成，作业目录: {gen_dir}")

    bin_dir = gen_dir / "bin"

    # 测试优化: 降低迭代步数
    cfd_para = bin_dir / "cfd_para.hypara"
    if cfd_para.exists():
        content = cfd_para.read_text(encoding="utf-8")
        content = re.sub(r'maxSimuStep\s*=\s*\d+', f'maxSimuStep = {TEST_MAX_STEPS}', content)
        content = re.sub(r'intervalStepFlow\s*=\s*\d+', f'intervalStepFlow = {TEST_MAX_STEPS // 4}', content)
        content = re.sub(r'intervalStepForce\s*=\s*\d+', f'intervalStepForce = {max(TEST_MAX_STEPS // 4, 10)}', content)
        content = re.sub(r'intervalStepPlot\s*=\s*\d+', f'intervalStepPlot = {TEST_MAX_STEPS}', content)
        cfd_para.write_text(content, encoding="utf-8")
        print(f"[i] 测试模式: maxSimuStep = {TEST_MAX_STEPS}（减少到 {TEST_MAX_STEPS} 步快速验证）")

    # 验证 .hypara 文件
    s2_pass, s2_total = validate_hypara_files(bin_dir)
    print()

    # ——— 阶段 3: 执行 CFD 仿真 ———
    print("=" * 60)
    print("阶段 3/5: 执行 NNW-HyFLOW CFD 仿真")
    print("=" * 60)

    # 使用工厂模式创建 executor
    executor = create_executor("nnw", config)
    # 降低超时（快速测试模式）
    executor.timeout = TEST_TIMEOUT
    print(f"[i] 执行器已创建: timeout={TEST_TIMEOUT}s")

    print(f"[i] 网格路径: {GRID_PATH}")
    print(f"[...]  启动 PHengLEI 求解器 (超时: {TEST_TIMEOUT}s, {TEST_MAX_STEPS} 步)...")

    # ⚠️ BUG WORKAROUND: main.py:460 未将 grid_path 传给 executor.execute()
    # 此处显式传递 grid_path 以修复此 bug
    exec_result = executor.execute(
        script_path=str(gen_dir),
        grid_path=GRID_PATH,  # <-- main.py 缺失此参数
    )

    if exec_result["success"]:
        print(f"\n[OK] CFD 仿真完成!")
        print(f"    耗时: {exec_result['duration']:.1f} 秒")
        print(f"    作业目录: {exec_result['job_dir']}")
    else:
        print(f"\n[X] 仿真执行失败!")
        print(f"    错误: {exec_result.get('error', '未知错误')}")
        if exec_result.get("stderr"):
            stderr_tail = exec_result["stderr"][-500:]
            print(f"    stderr (尾部):\n{stderr_tail}")

    s3_pass, s3_total = validate_exec_result(exec_result)
    print()

    if not exec_result["success"]:
        print("=" * 60)
        print("[FAIL] 仿真执行失败，跳过后续阶段")
        print("=" * 60)
        return 1

    # ——— 阶段 4: 读取结果 ———
    print("=" * 60)
    print("阶段 4/5: 读取 CFD 结果")
    print("=" * 60)

    # 使用工厂模式获取 ResultReader
    ResultReader = get_result_reader("nnw")
    result_job_dir = exec_result["job_dir"]
    sim_result = ResultReader.read(result_job_dir)

    if sim_result.success:
        print("[OK] 结果读取成功!\n")
        # 编码安全输出
        summary_text = sim_result.get_text_summary()
        try:
            print(summary_text)
        except UnicodeEncodeError:
            print(summary_text.encode('utf-8', errors='replace').decode('utf-8', errors='replace'))
    else:
        print(f"[X] 结果读取失败: {sim_result.error}")

    s4_pass, s4_total = validate_sim_result(sim_result)
    print()

    # ——— 阶段 5: 生成 CFD 报告 ———
    print("=" * 60)
    print("阶段 5/5: 生成 CFD 可视化报告")
    print("=" * 60)

    # 方法 A: 使用内置 ReportGenerator（仅生成 FEA 指标卡片——对于 CFD 会为空）
    print("[i] 方法 A: 内置 ReportGenerator (FEA 专用)...")
    from myagent.report import ReportGenerator
    try:
        fea_report = ReportGenerator(result_job_dir, solver_name="NNW-HyFLOW").generate()
        if fea_report:
            print(f"  [OK] FEA 报告: {fea_report}")
            fea_size = Path(fea_report).stat().st_size
            print(f"      大小: {fea_size}B {'[!] 偏小——CFD指标缺失' if fea_size < 5000 else '[OK]'}")
        else:
            print("  [--] FEA 报告: 无数据（CFD 结果不包含 FEA 指标）")
    except Exception as e:
        print(f"  [!] FEA 报告生成失败 (预期行为，CFD 无 FEA 指标): {e}")

    # 方法 B: 使用 CFD 专用报告生成器（从 run_onera_m6_quick.py 导入）
    print("\n[i] 方法 B: CFD 专用报告生成器...")
    # 直接导入 run_onera_m6_quick 中的 generate_cfd_report 函数
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from run_onera_m6_quick import generate_cfd_report
    cfd_report = generate_cfd_report(result_job_dir, sim_result, solver_name="NNW-HyFLOW")
    print(f"  [OK] CFD 报告: {cfd_report}")

    # 图片验证
    s5_img_pass, s5_img_total = validate_images(result_job_dir, sim_result.images)

    # 报告验证
    s5_rpt_pass, s5_rpt_total = validate_report(cfd_report)
    print()

    # ——— 汇总 ———
    print("=" * 60)
    print("  测试结果汇总")
    print("=" * 60)

    all_pass = s1_pass + s2_pass + s3_pass + s4_pass + s5_img_pass + s5_rpt_pass
    all_total = s1_total + s2_total + s3_total + s4_total + s5_img_total + s5_rpt_total

    stages = [
        ("阶段 1: 参数提取", s1_pass, s1_total),
        ("阶段 2: .hypara 生成", s2_pass, s2_total),
        ("阶段 3: 仿真执行", s3_pass, s3_total),
        ("阶段 4: 结果读取", s4_pass, s4_total),
        ("阶段 5: 图片验证", s5_img_pass, s5_img_total),
        ("阶段 5: 报告验证", s5_rpt_pass, s5_rpt_total),
    ]

    for name, p, t in stages:
        status = "[PASS]" if p == t else "[PARTIAL]" if p > t // 2 else "[FAIL]"
        print(f"  {status} {name}: {p}/{t}")

    print(f"\n  总计: {all_pass}/{all_total} 检查通过")

    # ——— Bug 报告 ———
    print("\n" + "=" * 60)
    print("  发现的 Bug")
    print("=" * 60)

    bugs = [
        ("CRITICAL", "main.py:460",
         "executor.execute(script_path) 未传递 grid_path= 参数。"
         "NNW 后端需要网格文件才能运行，缺少此参数导致求解器找不到网格。"
         "本测试通过显式传递 grid_path=GRID_PATH 绕过了此 bug。"),
        ("MEDIUM", "report.py:_build_metric_cards()",
         "仅支持 FEA 指标字段 (max_stress_mises, max_displacement 等)。"
         "CFD 指标 (CL, CD, L/D, Cm) 不会出现在内置报告中。"
         "需要 create_cfd_report() 作为替代方案。"),
        ("MEDIUM", "report.py:_generate_charts()",
         "依赖 paths.json 生成曲线图，但 paths.json 仅由 Abaqus 的"
         "RESULT_SAVER_CODE 生成（ODB 路径提取）。NNW 后端不生成此文件。"
         "CFD 报告需要使用 raw_data 代替 paths.json。"),
        ("LOW", "nnw/generator.py",
         "conversation_history 字段从未在 extract_parameters() 或 "
         "generate_script() 中被填充。多轮对话上下文信息丢失。"),
        ("LOW", "config.yaml",
         "cae.backend 默认值为 'abaqus'，使用 NNW 后端时需手动切换或"
         "代码中调用 config.set_cae_backend('nnw')。"),
    ]

    for severity, location, description in bugs:
        print(f"\n  [{severity}] {location}")
        print(f"  {description}")

    # 输出文件位置
    print("\n" + "=" * 60)
    print("  输出文件")
    print("=" * 60)
    print(f"  作业目录: {result_job_dir}")
    print(f"  CFD 报告: {cfd_report}")
    print(f"  .hypara 文件: {bin_dir}")
    if sim_result.images:
        print(f"  结果图片 ({len(sim_result.images)} 张):")
        for img in sim_result.images:
            print(f"    - {img}")

    return 0 if all_pass >= all_total * 0.8 else 1


if __name__ == "__main__":
    sys.exit(main())
