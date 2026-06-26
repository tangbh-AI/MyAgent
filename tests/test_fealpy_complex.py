"""复杂案例端到端测试 — 两端固支梁 + 均布压力 + 模态分析

模拟自然语言输入:
    "一根两端完全固定的梁，长600mm，矩形截面40x60mm，钢材料。
     上表面受均布压力0.2MPa（方向向下）。
     同时做静力分析和模态分析，网格可以粗一些加快速度。"

对比简单悬臂梁，这个案例更复杂：
  - 两端固定（更多约束 DOF）
  - 均布压力载荷（需定位上表面所有节点并施加等效节点力）
  - 固支梁模态特征与悬臂梁完全不同
  - 可验证对称性（位移/应力应对称于中点）
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import myagent.fealpy  # noqa: F401

# ——— 模拟 LLM 生成的 fealpy 脚本（两端固支梁 + 均布压力）———
CLAMPED_BEAM_SCRIPT = r'''
import numpy as np
from scipy.sparse.linalg import spsolve, eigs
from scipy.sparse import lil_matrix
from fealpy.mesh import TetrahedronMesh
from fealpy.functionspace import LagrangeFESpace, TensorFunctionSpace
from fealpy.material import LinearElasticMaterial
from fealpy.fem import LinearElasticityIntegrator, BilinearForm, MassIntegrator

# ——— 1. 几何与网格 ———
# 两端固支梁: X=长度 600mm, Y=高度 40mm (竖直方向), Z=宽度 60mm
# 固定端: X=0 和 X=600
# 载荷: 上表面 (Y=40) 受均布压力 0.2MPa 向下 (-Y)
Lx, Ly, Lz = 600.0, 40.0, 60.0
pressure = 0.2  # MPa = N/mm²
mesh = TetrahedronMesh.from_box(box=[0, Lx, 0, Ly, 0, Lz], nx=20, ny=3, nz=3)
n_nodes = mesh.number_of_nodes()
n_cells = mesh.number_of_cells()
node_coords = mesh.entity('node')
print(f"网格: {n_nodes} 节点, {n_cells} 单元")

# 诊断: 列出各面上的节点数
for axis, name in [(0, 'X'), (1, 'Y'), (2, 'Z')]:
    for val in [0.0, [Lx, Ly, Lz][axis-1] if axis > 0 else Lx]:
        n = np.sum(np.abs(node_coords[:, axis] - val) < 1e-6)
        if n > 0:
            val_str = f"{val:.0f}"
            print(f"  面 {name}={val_str}: {n} 节点")

# ——— 2. 有限元空间 ———
space = LagrangeFESpace(mesh, p=1, ctype='C')
uspace = TensorFunctionSpace(space, shape=(-1, 3))
gdof = uspace.number_of_global_dofs()
print(f"自由度: {gdof}")

# ——— 3. 材料（钢，mm-N-s）———
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

# ——— 5. 质量矩阵 ———
mintegrator = MassIntegrator(coef=density)
mform = BilinearForm(uspace)
mform.add_integrator(mintegrator)
M = mform.assembly().to_scipy()

# ——— 6. 边界条件: 两端固定 (X=0 和 X=Lx) ———
fixed_ends = [0.0, Lx]
fixed_dofs = []
for fixed_x in fixed_ends:
    fixed_nodes = np.where(np.abs(node_coords[:, 0] - fixed_x) < 1e-6)[0]
    for ni in fixed_nodes:
        fixed_dofs.extend([ni * 3, ni * 3 + 1, ni * 3 + 2])

# 去重（角节点可能同时属于两个面? 不会，X=0 和 X=600 互斥）
print(f"约束: {len(fixed_dofs)//3} 节点, {len(fixed_dofs)} DOF")

# ——— 7. 载荷: 上表面 (Y=Ly) 均布压力 0.2MPa 向下 ———
# 压力→节点力: 每个上表面节点承担的面积 ≈ 单元面积/节点数
# 简化：总压力 = pressure × 上表面积
# 上表面积 = Lx × Lz = 600 × 60 = 36000 mm²
# 总力 = 0.2 × 36000 = 7200 N
# 等效分配到上表面各节点
top_nodes = np.where(np.abs(node_coords[:, 1] - Ly) < 1e-6)[0]
top_area = Lx * Lz
total_force = pressure * top_area  # N
force_per_node = -total_force / len(top_nodes)  # 向下 (-Y)
print(f"载荷: 上表面 {len(top_nodes)} 节点, 总力 {total_force:.0f}N, "
      f"每节点 {force_per_node:.2f}N")

F = np.zeros(gdof)
for ni in top_nodes:
    F[ni * 3 + 1] = force_per_node  # Y 分量

# ——— 8. 施加约束 ———
A_bc = A.tolil()
for dof in fixed_dofs:
    A_bc[dof, :] = 0.0
    A_bc[dof, dof] = 1.0
    F[dof] = 0.0
A_bc = A_bc.tocsr()

# ——— 9. 静力求解 ———
uh = spsolve(A_bc, F)
uh_r = uh.reshape(-1, 3)
disp_mag = np.sqrt(np.sum(uh_r**2, axis=1))
max_disp = float(np.max(disp_mag))
max_disp_node = int(np.argmax(disp_mag))
print(f"\n静力结果:")
print(f"  最大位移: {max_disp:.4f} mm @节点 {max_disp_node}")
print(f"  节点坐标: ({node_coords[max_disp_node,0]:.0f}, "
      f"{node_coords[max_disp_node,1]:.0f}, {node_coords[max_disp_node,2]:.0f})")

# 对称性验证: 中点两侧位移应对称
mid = Lx / 2
left_half = node_coords[:, 0] < mid
right_half = node_coords[:, 0] > mid
left_max = float(np.max(disp_mag[left_half])) if np.any(left_half) else 0
right_max = float(np.max(disp_mag[right_half])) if np.any(right_half) else 0
sym_ratio = min(left_max, right_max) / max(left_max, right_max) if max(left_max, right_max) > 0 else 1
print(f"  对称性 (左半/右半最大位移比): {sym_ratio:.3f}")

# 理论值 (两端固支梁, 均布载荷):
# δ_max = q*L^4 / (384*E*I)
# q = pressure * width = 0.2 * 60 = 12 N/mm
# I = b*h^3/12 = 60*40^3/12 = 320000 mm^4
# δ_max = 12 * 600^4 / (384 * 210000 * 320000)
#       = 12 * 1.296e11 / (384 * 6.72e10)
#       = 1.555e12 / 2.58e13 = 0.0603 mm
q_line = pressure * Lz
I_theory = Lz * Ly**3 / 12
delta_theory = q_line * Lx**4 / (384 * E * I_theory)
print(f"  理论值: q={q_line:.1f} N/mm, I={I_theory:.0f} mm^4, "
      f"delta_max={delta_theory:.4f} mm")

# 应力检查: 最大应力应在固定端
# 简化: 用内置方法计算应力
from myagent.fealpy.knowledge import FEALPY_RESULT_SAVER_CODE
# (应力由注入的结果保存代码自动计算)

# ——— 10. 模态分析 ———
M_bc = M.tolil()
for dof in fixed_dofs:
    M_bc[dof, :] = 0.0
    M_bc[dof, dof] = 1e15
M_bc = M_bc.tocsr()

n_modes = 6
n_request = n_modes + 10
eigenvalues, eigenvectors = eigs(A_bc, k=n_request, M=M_bc, which='SM')

natural_frequencies = np.sqrt(np.abs(eigenvalues.real)) / (2 * np.pi)
idx = np.argsort(natural_frequencies)
natural_frequencies = natural_frequencies[idx].real
eigenvectors = eigenvectors[:, idx].real

valid_mask = natural_frequencies > 0.01
natural_frequencies = natural_frequencies[valid_mask][:n_modes]
eigenvectors = eigenvectors[:, valid_mask][:, :n_modes]

print(f"\n模态结果 (前 {len(natural_frequencies)} 阶):")
for i, f in enumerate(natural_frequencies):
    print(f"  f{i+1} = {f:.2f} Hz")

# 两端固支梁理论基频:
# f1 = (4.73^2)/(2π*L^2) * sqrt(EI/(ρA))
# = 22.37/(2*pi*360000) * sqrt(210000*320000/(7.85e-9*2400))
# A = 40*60 = 2400 mm^2, ρA = 1.884e-5 ton/mm
# sqrt(EI/ρA) = sqrt(6.72e10/1.884e-5) = sqrt(3.567e15) = 5.97e7
# f1 = 22.37/(2*pi*360000) * 5.97e7 = 9.89e-6 * 5.97e7 = 590 Hz
A_section = Ly * Lz
rho_A = density * A_section
EI = E * I_theory
f1_theory = (4.73**2) / (2 * np.pi * Lx**2) * np.sqrt(EI / rho_A)
print(f"  理论基频: {f1_theory:.1f} Hz")

# ——— 11. 变量导出（供自动注入的结果保存代码使用）———
project_name = "clamped_beam_pressure_modal"
stress_vm = None  # 自动计算
frequencies = natural_frequencies
mode_shapes_arr = eigenvectors
'''

from myagent.fealpy.knowledge import FEALPY_RESULT_SAVER_CODE
FULL_SCRIPT = CLAMPED_BEAM_SCRIPT.rstrip() + "\n\n" + FEALPY_RESULT_SAVER_CODE


def test_clamped_beam_e2e():
    """端到端: 两端固支梁 + 均布压力 + 模态"""
    print("=" * 70)
    print("MyAgent fealpy 复杂案例: 两端固支梁 + 均布压力 + 模态")
    print("=" * 70)
    print()
    print("自然语言输入:")
    print('  "一根两端完全固定的梁，长600mm，矩形截面40x60mm，钢材料。')
    print('   上表面受均布压力0.2MPa（方向向下）。')
    print('   同时做静力分析和模态分析。"')
    print()

    # [1] 保存脚本
    print("[1/5] 保存脚本...")
    script_dir = Path(tempfile.mkdtemp(prefix="fealpy_clamped_"))
    script_path = script_dir / "clamped_beam.py"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(FULL_SCRIPT)
    print(f"  脚本: {len(FULL_SCRIPT)} 字符, {len(FULL_SCRIPT.splitlines())} 行")
    try:
        compile(FULL_SCRIPT, str(script_path), "exec")
        print("  语法: OK")
    except SyntaxError as e:
        print(f"  语法: FAIL - {e}")
        return False

    # [2] 执行
    print("\n[2/5] 执行仿真...")
    from myagent.fealpy.executor import FealpyExecutor
    executor = FealpyExecutor(work_dir=tempfile.mkdtemp(prefix="fealpy_out_"))
    exec_result = executor.execute(str(script_path), job_name="clamped_beam")
    print(f"  成功: {exec_result['success']}, 耗时: {exec_result['duration']}s")
    if not exec_result["success"]:
        print(f"  错误: {exec_result.get('error', '?')}")
        print(f"  STDERR: {exec_result.get('stderr', '')[:500]}")
        return False

    # [3] 读取结果
    print("\n[3/5] 读取结果...")
    from myagent.fealpy.result import ResultReader
    result = ResultReader.read(exec_result["job_dir"])
    if not result.success:
        print(f"  失败: {result.error}")
        return False

    s = result.summary
    print(f"  最大位移: {s.get('max_displacement', '?'):.4f} mm")
    print(f"  最大应力: {s.get('max_stress_mises', '?'):.1f} MPa")
    print(f"  安全系数: {s.get('safety_factor', '?'):.2f}")
    print(f"  固有频率: {[round(f,1) for f in s.get('natural_frequencies', [])]} Hz")
    print(f"  图片: {len(result.images)} 张")

    # 验证
    assert "max_displacement" in s, "缺位移"
    assert "max_stress_mises" in s, "缺应力"
    assert "natural_frequencies" in s, "缺频率"
    freqs = s["natural_frequencies"]
    assert len(freqs) >= 3, f"模态不足: {len(freqs)}"
    for f in freqs:
        assert f > 0.1, f"伪模态: {f} Hz"
    mode_imgs = [x for x in result.images if "mode_" in x]
    assert len(mode_imgs) >= 3, f"振型图不足: {len(mode_imgs)}"

    # [4] 生成报告
    print("\n[4/5] 生成 HTML 报告...")
    from myagent.report import ReportGenerator
    report_path = ReportGenerator(
        exec_result["job_dir"], solver_name="fealpy"
    ).generate()
    assert report_path and os.path.exists(report_path), "报告生成失败"
    with open(report_path, "r", encoding="utf-8") as f:
        html = f.read()
    print(f"  报告: {len(html)} 字节")

    # [5] 验证
    print("\n[5/5] 验证报告...")
    checks = {
        "HTML结构": "<!DOCTYPE html>" in html and "</html>" in html,
        "模态section": "模态分析" in html,
        "频率表格": "固有频率 (Hz)" in html and "阶次" in html,
        "振型图": "振型图" in html,
        "应力云图": "stress" in html.lower() and "base64" in html,
        "关键结果": "关键结果" in html,
    }
    all_ok = True
    for name, passed in checks.items():
        s_flag = "OK" if passed else "FAIL"
        if not passed:
            all_ok = False
        print(f"  [{s_flag}] {name}")

    # 验证频率数值在报告中
    for f in freqs:
        if f"{f:.1f}" in html or f"{f:.2f}" in html:
            print(f"  [OK] {f:.1f} Hz 在报告中")
        else:
            print(f"  [WARN] {f:.2f} Hz 未在报告中找到")

    # 保存到 output/
    out_dir = Path("output/e2e_clamped_beam")
    out_dir.mkdir(parents=True, exist_ok=True)
    import shutil, glob as gmod
    shutil.copy2(report_path, out_dir / "analysis_report.html")
    for img in gmod.glob(os.path.join(exec_result["job_dir"], "*.png")):
        shutil.copy2(img, out_dir / os.path.basename(img))
    results_json = os.path.join(exec_result["job_dir"], "results.json")
    if os.path.exists(results_json):
        shutil.copy2(results_json, out_dir / "results.json")
    print(f"\n  输出目录: {out_dir.absolute()}")

    print("\n" + "=" * 70)
    print("复杂案例测试" + ("通过!" if all_ok else "有失败项"))
    print("=" * 70)
    assert all_ok, "检查失败"


if __name__ == "__main__":
    test_clamped_beam_e2e()
