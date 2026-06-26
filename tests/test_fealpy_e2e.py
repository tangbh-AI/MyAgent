"""端到端集成测试 — 完整 fealpy 管线: 自然语言→脚本→执行→报告（含模态 section）

模拟一个 LLM 生成的 fealpy 悬臂梁脚本，通过 executor、result reader、
report generator 完成全流程，验证 HTML 报告含模态分析 section。

用法:
    conda activate ccuse
    python tests/test_fealpy_e2e.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

# 注册 fealpy 后端
import myagent.fealpy  # noqa: F401


# ——— 模拟 LLM 生成的 fealpy 脚本 ———
# 这是 LLM 根据"悬臂梁静力+模态分析"生成的核心代码（结果保存代码由系统自动注入）
FEALPY_CANTILEVER_SCRIPT = r'''
import numpy as np
from scipy.sparse.linalg import spsolve, eigs
from scipy.sparse import lil_matrix
from fealpy.mesh import TetrahedronMesh
from fealpy.functionspace import LagrangeFESpace, TensorFunctionSpace
from fealpy.material import LinearElasticMaterial
from fealpy.fem import LinearElasticityIntegrator, BilinearForm, MassIntegrator

# ——— 1. 几何与网格 ———
# 悬臂梁: X=长度方向 1000mm, Y=高度 100mm, Z=宽度 50mm
Lx, Ly, Lz = 1000.0, 100.0, 50.0
mesh = TetrahedronMesh.from_box(box=[0, Lx, 0, Ly, 0, Lz], nx=30, ny=4, nz=3)
n_nodes = mesh.number_of_nodes()
n_cells = mesh.number_of_cells()
node_coords = mesh.entity('node')
print(f"网格: {n_nodes} 节点, {n_cells} 单元")

# ——— 2. 有限元空间 ———
space = LagrangeFESpace(mesh, p=1, ctype='C')
uspace = TensorFunctionSpace(space, shape=(-1, 3))
gdof = uspace.number_of_global_dofs()
print(f"自由度: {gdof}")

# ——— 3. 材料（钢，mm-N-s 单位制） ———
E = 210000.0
nu = 0.3
density = 7.85e-9
material = LinearElasticMaterial(
    name='Steel', elastic_modulus=E, poisson_ratio=nu, density=density
)

# ——— 4. 刚度矩阵 ———
integrator = LinearElasticityIntegrator(material=material)
bform = BilinearForm(uspace)
bform.add_integrator(integrator)
A = bform.assembly().to_scipy()

# ——— 5. 质量矩阵（模态分析用） ———
mintegrator = MassIntegrator(coef=density)
mform = BilinearForm(uspace)
mform.add_integrator(mintegrator)
M = mform.assembly().to_scipy()

# ——— 6. 边界条件 ———
# 固定端: X=0 面所有节点全约束
fixed_nodes = np.where(np.abs(node_coords[:, 0] - 0.0) < 1e-6)[0]
fixed_dofs = []
for ni in fixed_nodes:
    fixed_dofs.extend([ni * 3, ni * 3 + 1, ni * 3 + 2])
print(f"约束: {len(fixed_nodes)} 节点, {len(fixed_dofs)} DOF")

# ——— 7. 载荷 ———
# 自由端 X=Lx 面施加 Y 方向 -1000N
F = np.zeros(gdof)
load_nodes = np.where(np.abs(node_coords[:, 0] - Lx) < 1e-6)[0]
force_per_node = -1000.0 / len(load_nodes)
for ni in load_nodes:
    F[ni * 3 + 1] = force_per_node
print(f"载荷: {len(load_nodes)} 节点, 每节点 {force_per_node:.2f} N")

# ——— 8. 施加约束到刚度矩阵 ———
A_bc = A.tolil()
for dof in fixed_dofs:
    A_bc[dof, :] = 0.0
    A_bc[dof, dof] = 1.0
    F[dof] = 0.0
A_bc = A_bc.tocsr()

# ——— 9. 静力求解 ———
uh = spsolve(A_bc, F)
uh_reshaped = uh.reshape(-1, 3)
disp_mag = np.sqrt(np.sum(uh_reshaped**2, axis=1))
max_disp = float(np.max(disp_mag))
max_disp_node = int(np.argmax(disp_mag))
print(f"静力: 最大位移 {max_disp:.4f} mm @节点 {max_disp_node}")

# ——— 10. 模态分析 ———
M_bc = M.tolil()
for dof in fixed_dofs:
    M_bc[dof, :] = 0.0
    M_bc[dof, dof] = 1e15  # 极大质量 → 推高约束 DOF 频率
M_bc = M_bc.tocsr()

n_modes = 6
n_request = n_modes + 10  # 多请求以过滤伪模态
eigenvalues, eigenvectors = eigs(A_bc, k=n_request, M=M_bc, which='SM')

# 固有频率 (Hz)
natural_frequencies = np.sqrt(np.abs(eigenvalues.real)) / (2 * np.pi)
idx = np.argsort(natural_frequencies)
natural_frequencies = natural_frequencies[idx].real
eigenvectors = eigenvectors[:, idx].real

# 过滤近零伪模态
valid_mask = natural_frequencies > 0.01
natural_frequencies = natural_frequencies[valid_mask][:n_modes]
eigenvectors = eigenvectors[:, valid_mask][:, :n_modes]

print(f"模态: 前 {len(natural_frequencies)} 阶固有频率 (Hz):")
for i, f in enumerate(natural_frequencies):
    print(f"  f{i+1} = {f:.2f} Hz")

# ——— 11. 设置变量供自动注入的结果保存代码使用 ———
project_name = "cantilever_beam_static_modal"
stress_vm = None  # 专注模态结果，应力从略
frequencies = natural_frequencies
mode_shapes_arr = eigenvectors
'''

# 组合完整脚本（模拟 generator.generate_script 的注入逻辑）
from myagent.fealpy.knowledge import FEALPY_RESULT_SAVER_CODE
FULL_SCRIPT = FEALPY_CANTILEVER_SCRIPT.rstrip() + "\n\n" + FEALPY_RESULT_SAVER_CODE


def test_end_to_end_static_modal():
    """端到端测试: 悬臂梁静力+模态 → 脚本执行 → 结果读取 → 报告生成（含模态 section）"""
    print("=" * 70)
    print("MyAgent fealpy 端到端集成测试")
    print("自然语言 → 脚本 → 执行 → 报告（含模态 section）")
    print("=" * 70)

    # ————————————————————————————————————————————————
    # Step 1: 保存脚本
    # ————————————————————————————————————————————————
    print("\n[1/5] 保存 fealpy 仿真脚本...")
    script_dir = Path(tempfile.mkdtemp(prefix="fealpy_e2e_"))
    script_path = script_dir / "fealpy_simulation.py"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(FULL_SCRIPT)
    print(f"  脚本: {script_path} ({len(FULL_SCRIPT)} 字符, {len(FULL_SCRIPT.splitlines())} 行)")

    # 验证脚本语法
    try:
        compile(FULL_SCRIPT, str(script_path), "exec")
        print("  语法检查: OK")
    except SyntaxError as e:
        print(f"  语法检查: FAIL - {e}")
        return False

    # ————————————————————————————————————————————————
    # Step 2: 执行脚本
    # ————————————————————————————————————————————————
    print("\n[2/5] 执行 fealpy 仿真...")
    from myagent.fealpy.executor import FealpyExecutor
    executor = FealpyExecutor(work_dir=tempfile.mkdtemp(prefix="fealpy_out_"))
    exec_result = executor.execute(str(script_path), job_name="cantilever_beam")

    print(f"  成功: {exec_result['success']}")
    print(f"  耗时: {exec_result['duration']} 秒")
    print(f"  作业目录: {exec_result['job_dir']}")

    if not exec_result["success"]:
        print(f"  STDERR: {exec_result.get('stderr', '')[:500]}")
        print(f"  ERROR: {exec_result.get('error', '未知错误')}")
        return False

    # ————————————————————————————————————————————————
    # Step 3: 读取结果
    # ————————————————————————————————————————————————
    print("\n[3/5] 读取仿真结果...")
    from myagent.fealpy.result import ResultReader
    result = ResultReader.read(exec_result["job_dir"])

    print(f"  成功: {result.success}")
    if result.error:
        print(f"  错误: {result.error}")
        return False

    summary = result.summary
    print(f"  摘要键: {list(summary.keys())}")
    print(f"  结果图片: {result.images}")

    # 验证关键结果字段
    assert "max_displacement" in summary, "缺少 max_displacement"
    assert "natural_frequencies" in summary, "缺少 natural_frequencies"
    assert result.images, "没有生成任何图片"

    max_disp = summary["max_displacement"]
    frequencies = summary["natural_frequencies"]
    print(f"  最大位移: {max_disp:.4f} mm")
    print(f"  固有频率: {frequencies}")

    # 验证物理合理性
    assert max_disp > 0.01, f"位移过小 ({max_disp} mm)"
    assert max_disp < 100.0, f"位移过大 ({max_disp} mm)"
    assert len(frequencies) >= 1, f"没有有效模态频率"
    for f in frequencies:
        assert f > 0.1, f"模态频率 {f} Hz 过小（疑似伪模态）"

    # 验证振型图
    mode_shapes = result.results_json.get("mode_shapes", [])
    mode_images = [img for img in result.images if "mode_" in img]
    print(f"  振型图: {len(mode_shapes)} 张 (mode_shapes 列表)")
    print(f"  模态图片: {len(mode_images)} 张 (images 中 mode_* 文件)")
    assert len(mode_images) >= 1, "没有生成振型图"

    # ————————————————————————————————————————————————
    # Step 4: 生成 HTML 报告
    # ————————————————————————————————————————————————
    print("\n[4/5] 生成可视化分析报告...")
    from myagent.report import ReportGenerator
    report_gen = ReportGenerator(
        exec_result["job_dir"],
        solver_name="fealpy"
    )
    report_path = report_gen.generate()

    if not report_path:
        print("  报告生成失败: 无数据")
        return False

    print(f"  报告路径: {report_path}")
    assert os.path.exists(report_path), "报告文件不存在"

    # 读取报告内容
    with open(report_path, "r", encoding="utf-8") as f:
        report_html = f.read()

    report_size = len(report_html)
    print(f"  报告大小: {report_size} 字节")

    # ————————————————————————————————————————————————
    # Step 5: 验证报告内容
    # ————————————————————————————————————————————————
    print("\n[5/5] 验证报告内容...")

    checks = {
        "HTML 结构": "<!DOCTYPE html>" in report_html and "</html>" in report_html,
        "报告标题": "MyAgent" in report_html and "仿真分析报告" in report_html,
        "求解器名称": "fealpy" in report_html,
        "模态分析 section": "模态分析" in report_html,
        "固有频率表格": "<th>阶次</th>" in report_html and "<th>固有频率 (Hz)</th>" in report_html,
        "振型图 section": "振型图" in report_html,
        "模态图片嵌入": ('mode 1' in report_html or 'mode_1' in report_html) and 'base64' in report_html,
        "位移云图": 'displacement' in report_html.lower() and 'base64' in report_html,
        "关键结果卡片": "关键结果" in report_html,
        "结果云图 section": "结果云图" in report_html,
    }

    all_ok = True
    for check_name, passed in checks.items():
        status = "OK" if passed else "FAIL"
        if not passed:
            all_ok = False
        print(f"  [{status}] {check_name}")

    # 额外验证：报告中有实际的频率数值
    for freq in frequencies:
        freq_str = f"{freq:.2f}"
        if freq_str in report_html:
            print(f"  [OK] 频率 {freq_str} Hz 出现在报告中")
        else:
            # 格式化可能略有不同
            found = False
            for line in report_html.split('\n'):
                if f"{freq:.1f}" in line or f"{freq:.2f}" in line:
                    found = True
                    break
            if found:
                print(f"  [OK] 频率 ~{freq:.1f} Hz 出现在报告中")
            else:
                print(f"  [WARN] 频率 {freq:.2f} Hz 未在报告中找到")

    # 验证分析类型标注
    if "static_modal" in report_html or "static" in report_html:
        print(f"  [OK] 分析类型标注存在")

    print("\n" + "=" * 70)
    if all_ok:
        print("端到端测试通过: 自然语言→脚本→执行→报告（含模态 section）")
    else:
        print("端到端测试有失败项，请检查上述 [FAIL] 项")
    print(f"报告路径: {report_path}")
    print("=" * 70)

    assert all_ok, "端到端测试有失败项"


if __name__ == "__main__":
    success = test_end_to_end_static_modal()
    sys.exit(0 if success else 1)
