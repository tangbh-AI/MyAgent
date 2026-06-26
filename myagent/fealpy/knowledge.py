"""fealpy API 知识库 — 注入 LLM system prompt 的 FEM 参考

提供 fealpy 的常用 API 参考文档和完整示例脚本，
帮助 LLM 生成正确的 fealpy 有限元仿真脚本。

fealpy 是纯 Python 有限元分析库，支持线弹性静力分析和模态分析。
"""

# ——— 默认材料属性（和 Abaqus 保持一致，mm-N-s 单位制） ———

DEFAULT_MATERIALS = {
    "steel": {
        "name": "Steel",
        "density": 7.85e-9,       # ton/mm³
        "elastic": [210000.0, 0.3],  # E(MPa), ν
        "yield_stress": 250.0,    # MPa
    },
    "aluminum": {
        "name": "Aluminum",
        "density": 2.7e-9,
        "elastic": [70000.0, 0.33],
        "yield_stress": 270.0,
    },
    "titanium": {
        "name": "Titanium",
        "density": 4.5e-9,
        "elastic": [110000.0, 0.31],
        "yield_stress": 880.0,
    },
}

# ——— 单位制说明 ———

UNITS_INFO = """
fealpy 使用 mm-N-s 单位制（与 Abaqus 一致）：
- 长度: mm
- 力: N
- 质量: ton (10³ kg)
- 应力: MPa (N/mm²)
- 密度: ton/mm³ (钢材 ≈ 7.85e-9)
- 弹性模量: MPa (钢材 E = 210000)
"""

# ——— fealpy API 参考 ———

FEALPY_API_REFERENCE = """
## fealpy Python API 参考

fealpy 是纯 Python 有限元库，所有 API 通过标准 Python import 使用。

### 基础导入
```python
import numpy as np
from scipy.sparse.linalg import spsolve
from scipy.sparse.linalg import eigs as sparse_eigs
from scipy.sparse import lil_matrix
```

### 1. 网格生成 (Mesh)

**3D 四面体网格 — TetrahedronMesh.from_box**
```python
from fealpy.mesh import TetrahedronMesh

# box = [xmin, xmax, ymin, ymax, zmin, zmax]  单位: mm
# nx, ny, nz: 各方向分段数（控制网格密度）
mesh = TetrahedronMesh.from_box(
    box=[0.0, length_x, 0.0, length_y, 0.0, length_z],
    nx=nx, ny=ny, nz=nz
)
# mesh.number_of_nodes() — 节点数
# mesh.number_of_cells() — 单元数
# mesh.entity('node') — 节点坐标数组 (n_nodes, 3)
```

### 2. 有限元空间

```python
from fealpy.functionspace import LagrangeFESpace, TensorFunctionSpace

# 标量空间（温度、压力等）
space = LagrangeFESpace(mesh, p=1, ctype='C')

# 向量空间（位移 — 3D 每个节点 3 个自由度）
uspace = TensorFunctionSpace(space, shape=(-1, 3))
# shape=(-1, 3) 表示每个节点 3 个分量 (u_x, u_y, u_z)，-1 由 space 自动推导

# 获取自由度信息
gdof = uspace.number_of_global_dofs()  # 总自由度数
```

### 3. 材料定义

```python
from fealpy.material import LinearElasticMaterial

material = LinearElasticMaterial(
    name='Steel',
    elastic_modulus=210000.0,  # E (MPa)
    poisson_ratio=0.3,         # ν
    density=7.85e-9,           # 密度 (ton/mm³)，模态分析必需
)
```

### 4. 线弹性静力分析

```python
from fealpy.fem import LinearElasticityIntegrator
from fealpy.fem import BilinearForm, LinearForm

# 刚度矩阵组装
integrator = LinearElasticityIntegrator(material=material)
bform = BilinearForm(uspace)
bform.add_integrator(integrator)
A = bform.assembly().to_scipy()  # → scipy.sparse.csr_matrix
```

### 5. 载荷向量

```python
import numpy as np

# 创建零载荷向量
F = np.zeros(gdof)

# 方式1: 在指定坐标范围的节点上施加载荷
node_coords = mesh.entity('node')  # (n_nodes, 3)

# 找到加载面上的节点（如 z ≈ length_z）
load_z = length_z  # 加载面 Z 坐标
load_nodes = np.where(np.abs(node_coords[:, 2] - load_z) < 1e-6)[0]

# 分配力到节点
force_per_node = total_force / len(load_nodes)
for node in load_nodes:
    dof = node * 3 + direction_index  # 0=X, 1=Y, 2=Z
    F[dof] = force_per_node
```

### 6. 边界条件 — ⚠️ 必须手动施加（不推荐 DirichletBC）

**fealpy 3.4.0 的 DirichletBC 对 TensorFunctionSpace 存在已知 bug，
必须通过手动修改稀疏矩阵行/列实现固定约束。**

```python
from scipy.sparse import lil_matrix

# 找到固定面上的节点（如 z ≈ 0）
node_coords = mesh.entity('node')
fixed_nodes = np.where(np.abs(node_coords[:, 2] - 0.0) < 1e-6)[0]

# 收集所有需要固定的自由度（每个固定节点固定 ux, uy, uz）
fixed_dofs = []
for node in fixed_nodes:
    fixed_dofs.extend([node * 3, node * 3 + 1, node * 3 + 2])

# 修改刚度矩阵：固定自由度所在行清零、对角置 1
A_bc = A.tolil()  # 转为可高效修改的 LIL 格式
for dof in fixed_dofs:
    A_bc[dof, :] = 0
    A_bc[dof, dof] = 1.0
    F[dof] = 0.0  # 载荷向量对应位置也清零
A_bc = A_bc.tocsr()  # 转回 CSR 格式用于求解
```

### 7. 求解位移

```python
from scipy.sparse.linalg import spsolve

# 求解线性系统 K·u = F
uh = spsolve(A_bc, F)  # 位移向量 (gdof,)

# 计算位移幅值
uh_reshaped = uh.reshape(-1, 3)  # (n_nodes, 3)
disp_mag = np.sqrt(np.sum(uh_reshaped**2, axis=1))  # (n_nodes,)
max_disp = np.max(disp_mag)
```

### 8. 模态分析 (特征值求解)

```python
from fealpy.fem import MassIntegrator

# 质量矩阵
mintegrator = MassIntegrator(coef=density)  # coef = 材料密度
mform = BilinearForm(uspace)
mform.add_integrator(mintegrator)
M = mform.assembly().to_scipy()  # → scipy.sparse.csr_matrix

# ⚠️ 关键: 质量矩阵的 BC 处理与刚度矩阵不同！
# 不能用 M[dof, dof]=1.0 — 这会引入 1 rad/s ≈ 0.159 Hz 的虚假模态
# 正确做法: 设对角为极大值 (1e15)，将约束自由度推到极高频率
M_bc = M.tolil()
for dof in fixed_dofs:
    M_bc[dof, :] = 0.0
    M_bc[dof, dof] = 1e15  # 极大质量 → 约束 DOF 不出现在低频模态中
M_bc = M_bc.tocsr()

# 求解特征值问题 K·φ = ω²·M·φ
from scipy.sparse.linalg import eigs
n_modes = 6  # 前 6 阶

# ⚠️ 关键: 使用 which='SM' (Smallest Magnitude)，不要用 sigma=0.0！
# sigma=0.0 + which='LM' 在大多数实际网格上不收敛 (ARPACK No convergence)
# which='SM' 直接找最小幅值特征值，鲁棒且收敛快
# 约束 DOF 产生近零特征值 (< 0.01 Hz)，需额外请求更多模态后过滤
n_request = n_modes + 10  # 多请求一些，过滤掉近零伪模态
eigenvalues, eigenvectors = eigs(A_bc, k=n_request, M=M_bc, which='SM')

# 固有频率 (Hz)
natural_frequencies = np.sqrt(np.abs(eigenvalues.real)) / (2 * np.pi)
# 按频率升序排列
idx = np.argsort(natural_frequencies)
natural_frequencies = natural_frequencies[idx].real
eigenvectors = eigenvectors[:, idx].real

# 过滤近零伪模态（来自约束 DOF 的数值零）
valid_mask = natural_frequencies > 0.01
natural_frequencies = natural_frequencies[valid_mask][:n_modes]
eigenvectors = eigenvectors[:, valid_mask][:, :n_modes]
```

### 9. 应力后处理

**推荐方案：利用 fealpy 自带的应力恢复功能**

fealpy 已内置从位移解恢复应力的功能，
LLM 生成的脚本中调用 fealpy API 而非手写 B 矩阵可避免数学错误。

```python
# 使用 fealpy 的应变/应力后处理——在积分点计算，再外推到节点
# fealpy.fem 模块提供了 LinearElasticityIntegrator，可以直接在
# 积分点计算应力，简化后处理代码

# 简化方法：直接用材料矩阵 + 应变近似计算节点应力
# 对每个单元，在单元中心用 B 矩阵近似
# （更稳定的做法是使用 LinearElasticityIntegrator 内置的 stress 方法）
```

**备用方案：手动计算（仅当 fealpy 内置方法不可用时）**

见模板脚本中的简化节点应力估计方法（利用 Lamé 常数 + 应变近似）。

### 10. 注意事项
- fealpy 是纯 Python 库，无需外部许可证
- `assembly()` 返回 fealpy 的 CSRTensor，需调用 `.to_scipy()` 转为 scipy CSR
- **DirichletBC 有 bug，必须手动修改稀疏矩阵行/列施加 BC**
- **质量矩阵 BC 必须设对角为 1e15（极大值），不是 1.0！否则会引入 0.159Hz 虚假模态**
- 网格密度 nx/ny/nz 建议控制在使总节点数 < 50000
- 所有单位使用 mm-N-s 制
- 对于模态分析，sigma=0.0 用于寻找接近 0 的特征值（低频模态）
- 应力计算建议用 fealpy 内置后处理函数，避免手写 B 矩阵
"""


# ——— 结果保存代码（注入每个生成脚本的末尾） ———

FEALPY_RESULT_SAVER_CODE = r'''
# ============================================================
# 以下为 MyAgent 自动注入的 fealpy 结果保存代码
# 请确保在调用此代码前，以下变量已定义：
#   mesh         — fealpy 网格对象
#   uh           — 位移解向量 (gdof,) numpy 数组
#   stress_vm    — (可选) von Mises 应力，shape (n_nodes,) 或 (n_cells,)
#   frequencies  — (可选) 固有频率列表 (Hz)，shape (n_modes,)
#   mode_shapes_arr — (可选) 振型矩阵，shape (gdof, n_modes)
#   project_name — (可选) 项目名称字符串
# ============================================================
import json
import os
import sys
import numpy as np

# 设置 matplotlib 非 GUI 后端
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False


def _fealpy_save_results(
    mesh,
    uh,
    stress_vm=None,
    frequencies=None,
    mode_shapes_arr=None,
    project_name="fealpy_simulation"
):
    """保存 fealpy 仿真结果到 results.json + 生成 PNG 图片

    此函数由 MyAgent 自动注入脚本末尾。
    脚本应调用此函数来输出标准格式结果。
    """
    output_dir = os.getcwd()
    results = {
        "analysis_type": "static",
        "summary": {},
        "mesh_info": {},
        "images": [],
        "project_name": project_name,
    }
    images = []

    try:
        # ——— 1. 网格信息 ———
        n_nodes = mesh.number_of_nodes()
        n_cells = mesh.number_of_cells()
        results["mesh_info"] = {
            "n_nodes": n_nodes,
            "n_elements": n_cells,
            "element_type": str(type(mesh).__name__).replace('Mesh', ''),
        }
        print(f"[MyAgent] 网格: {n_nodes} 节点, {n_cells} 单元")

        # ——— 2. 提取节点坐标 ———
        node_coords = mesh.entity('node')  # (n_nodes, 3)

        # ——— 3. 位移结果 ———
        if uh is not None:
            uh_reshaped = uh.reshape(-1, 3)
            disp_mag = np.sqrt(np.sum(uh_reshaped**2, axis=1))  # (n_nodes,)
            max_disp = float(np.max(disp_mag))
            results["summary"]["max_displacement"] = round(max_disp, 4)
            print(f"[MyAgent] 最大位移: {max_disp:.4f} mm")

            # ——— 位移云图 ———
            try:
                _fealpy_contour_plot(
                    mesh, node_coords, disp_mag,
                    filename="displacement.png",
                    title="位移分布 (mm)",
                    cmap="jet",
                    output_dir=output_dir,
                )
                images.append("displacement.png")
            except Exception as e:
                print(f"[MyAgent] 位移云图失败: {e}")

        # ——— 4. 应力结果 ———
        if stress_vm is not None:
            max_s = float(np.max(stress_vm))
            results["summary"]["max_stress_mises"] = round(max_s, 2)
            print(f"[MyAgent] 最大 von Mises 应力: {max_s:.2f} MPa")

            # ——— 应力云图 ———
            try:
                # 如果 stress 是单元中心值，映射到节点
                if len(stress_vm) == n_cells:
                    # 简单平均到节点
                    cell = mesh.entity('cell')
                    node_stress = np.zeros(n_nodes)
                    node_count = np.zeros(n_nodes)
                    for ci, cell_nodes in enumerate(cell):
                        for ni in cell_nodes:
                            node_stress[ni] += stress_vm[ci]
                            node_count[ni] += 1
                    node_count[node_count == 0] = 1
                    stress_plot = node_stress / node_count
                else:
                    stress_plot = stress_vm

                _fealpy_contour_plot(
                    mesh, node_coords, stress_plot,
                    filename="stress_mises.png",
                    title="von Mises 应力分布 (MPa)",
                    cmap="hot",
                    output_dir=output_dir,
                )
                images.append("stress_mises.png")
            except Exception as e:
                print(f"[MyAgent] 应力云图失败: {e}")

            # 安全系数
            mat_yield = 250.0  # 默认 Q235 钢
            results["summary"]["material_yield_strength"] = mat_yield
            if max_s > 0:
                results["summary"]["safety_factor"] = round(mat_yield / max_s, 2)

        # ——— 5. 模态结果 ———
        if frequencies is not None:
            results["analysis_type"] = "modal" if uh is None else "static_modal"
            freq_list = [round(float(f), 2) for f in frequencies]
            results["summary"]["natural_frequencies"] = freq_list
            print(f"[MyAgent] 固有频率: {freq_list} Hz")

            # ——— 振型云图 ———
            if mode_shapes_arr is not None:
                n_modes = min(len(freq_list), mode_shapes_arr.shape[1], 6)
                mode_images = []
                for mi in range(n_modes):
                    try:
                        mode_vec = mode_shapes_arr[:, mi].reshape(-1, 3)
                        mode_mag = np.sqrt(np.sum(mode_vec**2, axis=1))
                        # 归一化
                        if np.max(mode_mag) > 0:
                            mode_mag = mode_mag / np.max(mode_mag)
                        fname = f"mode_{mi+1}.png"
                        _fealpy_contour_plot(
                            mesh, node_coords, mode_mag,
                            filename=fname,
                            title=f"第 {mi+1} 阶振型 ({freq_list[mi]:.1f} Hz)",
                            cmap="coolwarm",
                            output_dir=output_dir,
                        )
                        mode_images.append(fname)
                    except Exception as e:
                        print(f"[MyAgent] 振型 {mi+1} 云图失败: {e}")
                if mode_images:
                    results["mode_shapes"] = mode_images
                    images.extend(mode_images)

        # ——— 6. 汇总 ———
        results["images"] = images

        # 检查是否有实质结果
        if not results["summary"]:
            results["error"] = "未生成有效的仿真结果"
            print("[MyAgent] 警告: results.json 无有效数值结果")

    except Exception as e:
        print(f"[MyAgent] 结果保存出错: {e}")
        import traceback
        traceback.print_exc()
        results["error"] = str(e)

    # ——— 7. 写入 results.json ———
    _fealpy_write_json(results, output_dir)


def _fealpy_contour_plot(mesh, node_coords, scalar, filename, title, cmap, output_dir):
    """生成填充云图 PNG

    Args:
        mesh: fealpy 网格对象
        node_coords: 节点坐标 (n_nodes, 2) 或 (n_nodes, 3)
        scalar: 标量场 (n_nodes,)
        filename: 输出文件名
        title: 图标题
        cmap: 色图名
        output_dir: 输出目录
    """
    dim = node_coords.shape[1]

    fig, ax = plt.subplots(figsize=(10, 8))
    if dim == 2 or (dim == 3 and np.allclose(node_coords[:, 2], 0)):
        # 2D 或平面 3D
        x, y = node_coords[:, 0], node_coords[:, 1]
        tri = mesh.entity('cell')
        tcf = ax.tripcolor(x, y, tri, scalar, shading='gouraud', cmap=cmap)
    else:
        # 3D：在 XY 平面上做投影
        x, y = node_coords[:, 0], node_coords[:, 1]
        try:
            tri = mesh.entity('cell')
            if tri.shape[1] == 4:
                # 四面体 → 三角剖分需要提取表面
                from scipy.spatial import Delaunay
                tri_2d = Delaunay(node_coords[:, :2])
                tcf = ax.tripcolor(x, y, tri_2d.simplices, scalar, shading='gouraud', cmap=cmap)
            else:
                tcf = ax.tripcolor(x, y, tri, scalar, shading='gouraud', cmap=cmap)
        except Exception:
            # 回退：散点图
            tcf = ax.scatter(x, y, c=scalar, cmap=cmap, s=1)

    cbar = fig.colorbar(tcf, ax=ax, shrink=0.8)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.2, linestyle='--')

    filepath = os.path.join(output_dir, filename)
    fig.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"[MyAgent] 已保存: {filename}")


def _fealpy_write_json(results, output_dir):
    """写入 results.json"""
    filepath = os.path.join(output_dir, 'results.json')
    try:
        # 处理 numpy 类型
        def convert(obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            elif isinstance(obj, (np.floating,)):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=convert)
        print(f"[MyAgent] 已保存: results.json")
    except Exception as e:
        print(f"[MyAgent] 写入 results.json 失败: {e}")


def _fealpy_compute_stress(mesh, uh, E=210000.0, nu=0.3):
    """从位移解计算单元 von Mises 应力（内置固定算法）

    对每个四面体单元，基于线性形函数计算常应变，
    再通过弹性矩阵得到应力，最后求 von Mises。

    Args:
        mesh: TetrahedronMesh
        uh: 位移向量 (gdof,)
        E: 弹性模量 (MPa)
        nu: 泊松比

    Returns:
        von_mises: (n_cells,) 单元中心 von Mises 应力
    """
    n_nodes = mesh.number_of_nodes()
    n_cells = mesh.number_of_cells()
    node = mesh.entity('node')  # (n_nodes, 3)
    cell = mesh.entity('cell')  # (n_cells, 4)
    u = uh.reshape(-1, 3)  # (n_nodes, 3)

    # 弹性矩阵 (Voigt 记法, 6x6)
    lam = E * nu / ((1 + nu) * (1 - 2 * nu))
    mu = E / (2 * (1 + nu))
    D = np.array([
        [lam + 2*mu, lam,       lam,       0,  0,  0],
        [lam,       lam + 2*mu, lam,       0,  0,  0],
        [lam,       lam,       lam + 2*mu, 0,  0,  0],
        [0,         0,         0,         mu, 0,  0],
        [0,         0,         0,         0,  mu, 0],
        [0,         0,         0,         0,  0,  mu],
    ])

    # 参考单元形函数对 ξ 的梯度 (4 节点 × 3 方向)
    dN_dxi = np.array([
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
        [-1, -1, -1],
    ])  # (4, 3)

    von_mises = np.zeros(n_cells)

    for ci in range(n_cells):
        nidx = cell[ci]          # 4 个节点局部索引
        coord = node[nidx]       # (4, 3) 物理坐标
        ue = u[nidx].flatten()   # (12,) 单元位移

        # Jacobian: J_{ij} = ∂x_j/∂ξ_i  (3x3)，用节点 4 作为参考
        # x(ξ) = N1*x1 + N2*x2 + N3*x3 + N4*x4
        # dx/dξ_i = sum_k (dNk/dξ_i) * xk
        # = 1*x1 + 0*x2 + 0*x3 + (-1)*x4  (for ξ1 direction)
        J = np.zeros((3, 3))
        for a in range(3):  # ξ direction
            for k in range(4):
                J[a, :] += dN_dxi[k, a] * coord[k, :]

        # 用 J^T 来求物理梯度: ∇_x Ni = J^(-T) · ∇_ξ Ni
        try:
            invJT = np.linalg.inv(J).T  # (3, 3)
        except np.linalg.LinAlgError:
            continue

        # 物理梯度 (4, 3): 每行是 [dNi/dx, dNi/dy, dNi/dz]
        grads = np.zeros((4, 3))
        for k in range(4):
            grads[k, :] = invJT @ dN_dxi[k, :]  # J^(-T) · ∇_ξ Nk

        # B 矩阵 (6, 12)
        B = np.zeros((6, 12))
        for k in range(4):
            dNdx, dNdy, dNdz = grads[k]
            col = k * 3
            B[0, col] = dNdx
            B[1, col+1] = dNdy
            B[2, col+2] = dNdz
            B[3, col] = dNdy
            B[3, col+1] = dNdx
            B[4, col+1] = dNdz
            B[4, col+2] = dNdy
            B[5, col] = dNdz
            B[5, col+2] = dNdx

        # 应变 (6,) → 应力 (6,)
        epsilon = B @ ue
        sigma = D @ epsilon

        # von Mises
        sxx, syy, szz, sxy, syz, szx = sigma
        vm = np.sqrt(0.5 * ((sxx-syy)**2 + (syy-szz)**2 + (szz-sxx)**2 +
                            6*(sxy**2 + syz**2 + szx**2)))
        von_mises[ci] = vm

    return von_mises


# ——— 自动保存（如果脚本定义了需要的变量） ———
# 尝试从全局命名空间寻找所需变量
g = globals()
_mesh = g.get('mesh')
_uh = g.get('uh')
if _mesh is not None and _uh is not None:
    _stress = g.get('stress_vm', g.get('stress'))
    if _stress is None:
        # 自动计算应力（使用内置可靠算法，避免 LLM 手写 B 矩阵错误）
        try:
            _E = g.get('E', 210000.0)
            _nu_val = g.get('nu', 0.3)
            _stress = _fealpy_compute_stress(_mesh, _uh, E=_E, nu=_nu_val)
            print("[MyAgent] 自动计算单元应力完成")
        except Exception as e:
            print(f"[MyAgent] 自动应力计算失败: {e}")

    _fealpy_save_results(
        mesh=_mesh,
        uh=_uh,
        stress_vm=_stress,
        frequencies=g.get('frequencies', g.get('natural_frequencies')),
        mode_shapes_arr=g.get('mode_shapes_arr', g.get('eigenvectors')),
        project_name=g.get('project_name', 'fealpy_simulation'),
    )
else:
    print("[MyAgent] 警告: 未找到 mesh/uh 变量，请手动调用 _fealpy_save_results(mesh, uh, ...)")
'''


# ——— System Prompt ———

def get_fealpy_system_prompt() -> str:
    """获取用于 LLM 的 fealpy 系统提示词

    包含单位制说明、材料库、API 参考和脚本生成规则。

    Returns:
        系统提示词字符串
    """
    materials_info = "\n".join(
        f"  - {name}: E={props['elastic'][0]}MPa, ν={props['elastic'][1]}, "
        f"σy={props['yield_stress']}MPa, ρ={props['density']}"
        for name, props in DEFAULT_MATERIALS.items()
    )

    return f"""你是一个 fealpy 有限元仿真专家。fealpy 是纯 Python 有限元分析库。
根据用户的自然语言描述，生成可以在 Python 中运行的 fealpy 仿真脚本。

{UNITS_INFO}

## 预定义材料库（可直接使用）
{materials_info}

{FEALPY_API_REFERENCE}

## 脚本生成规则
1. 生成的脚本必须是可独立运行的 Python 脚本（`python script.py`）
2. 使用 mm-N-s 单位制（与 Abaqus 一致）
3. 脚本开头导入必要的模块：numpy, scipy, fealpy
4. 脚本末尾不要写结果保存代码，系统会自动注入 _fealpy_save_results()
5. 如果用户描述的是"梁"、"悬臂梁"、"简支梁"等结构，按如下规则建模：
   - 默认用 TetrahedronMesh.from_box()
   - 根据用户描述的尺寸设置 box=[0, Lx, 0, Ly, 0, Lz]
   - Lx=长度方向, Ly=高度方向, Lz=宽度方向
   - 固定端在 X=0 面
   - 材料默认用 steel，除非用户指定其他材料
6. 载荷施加在网格节点上（通过坐标定位节点索引，对相应自由度施加力）
7. **边界条件必须手动施加**：通过坐标定位节点，然后修改稀疏矩阵行/列实现 Dirichlet BC。
   固定面上的每个节点固定相应自由度 (ux/uy/uz)。
8. **重要**: assembly() 返回 fealpy 的 CSRTensor，需要用 .to_scipy() 转为 scipy CSR 矩阵
9. **重要**: 手动 BC 时，A.tolil() → 修改行 → A.tocsr()
10. **🔴 模态分析关键规则**:
    a) 质量矩阵 M 的 BC 处理必须设对角为 1e15（极大值），**绝对不能设 1.0**！
       设 1.0 会产生 1 rad/s ≈ 0.159 Hz 的虚假特征值，污染前 6 阶模态结果。
    b) 使用 `eigs(A_bc, k=n_request, M=M_bc, which="SM")` 求解特征值，
       **不要使用 sigma=0.0 + which="LM"**（ARPACK 不收敛）！
       多请求 10 个模态 (n_modes+10)，然后过滤掉 f < 0.01 Hz 的近零伪模态。
11. **应力计算**: 优先使用 fealpy 自带的后处理方法，避免手写复杂的 B 矩阵组装。
    如果必须手动计算，确保四面体单元的节点顺序与 fealpy 一致。
12. 只输出 Python 代码，用 ```python 和 ``` 包裹，不要输出额外的解释
13. 代码中包含必要的注释说明每个步骤
"""
