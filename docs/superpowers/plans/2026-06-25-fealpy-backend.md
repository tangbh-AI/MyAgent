# fealpy CAE 后端接入 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 MyAgent 接入 fealpy 作为第三个 CAE 后端并设为主推默认后端，支持线弹性静力 + 模态分析，生成标准可视化报告。

**Architecture:** 完全遵循现有 Abaqus/NNW 模式 — LLM 生成 fealpy Python 脚本 → subprocess 执行 → 读取 results.json → 生成 HTML 报告。5 个新文件 + 3 个文件修改 + 测试 + 文档更新。

**Tech Stack:** Python 3.10+, fealpy, numpy, scipy, matplotlib, conda ccuse

---

### Task 1: 安装 fealpy 并探索 API

**Files:**
- (无新建文件，探索性任务)

- [ ] **Step 1: 在 conda ccuse 下安装 fealpy**

```bash
conda activate ccuse && pip install fealpy
```

- [ ] **Step 2: 验证 fealpy 导入并探索网格 API**

```bash
conda activate ccuse && python -c "
from fealpy.mesh import TetrahedronMesh, TriangleMesh
import numpy as np

# 测试四面体网格
mesh = TetrahedronMesh.from_box(box=[0, 10, 0, 1, 0, 2], nx=4, ny=2, nz=2)
print(f'四面体网格: {mesh.number_of_nodes()} 节点, {mesh.number_of_cells()} 单元')

# 测试三角形网格
mesh2d = TriangleMesh.from_box(box=[0, 10, 0, 1], nx=4, ny=2)
print(f'三角网格: {mesh2d.number_of_nodes()} 节点, {mesh2d.number_of_cells()} 单元')

print('fealpy 网格 API 可用')
"
```

- [ ] **Step 3: 探索 fealpy 的 FEM 模块（有限元空间 + 线弹性）**

```bash
conda activate ccuse && python -c "
from fealpy.functionspace import LagrangeFESpace, TensorFunctionSpace
from fealpy.mesh import TetrahedronMesh
from fealpy.fem import LinearElasticityIntegrator, BilinearForm, LinearForm
from fealpy.fem import DirichletBC
from scipy.sparse.linalg import spsolve
import numpy as np

# 检查 fealpy 的关键 FEM 导入
print('LagrangeFESpace:', LagrangeFESpace)
print('TensorFunctionSpace:', TensorFunctionSpace)
print('LinearElasticityIntegrator:', LinearElasticityIntegrator)
print('BilinearForm:', BilinearForm)
print('DirichletBC:', DirichletBC)
print('fealpy FEM 模块导入成功')
" 2>&1
```

如果导入失败，输出实际可用模块名：
```bash
conda activate ccuse && python -c "
import fealpy
# 列出 fealpy 子模块
import pkgutil
for m in pkgutil.iter_modules(fealpy.__path__, fealpy.__name__ + '.'):
    print(m.name)
"
```

- [ ] **Step 4: 根据实际 API 调整知识库内容**

记录实际的 fealpy API，更新 knowledge.py 中的 API 参考。

- [ ] **Step 5: 提交 (如果 fealpy 可用)**

```bash
echo "fealpy 安装成功" >> /dev/null
```

---

### Task 2: 创建 knowledge.py — fealpy API 知识库

**Files:**
- Create: `myagent/fealpy/knowledge.py`

- [ ] **Step 1: 编写知识库文件**

```python
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
```

**2D 三角形网格 — TriangleMesh.from_box**
```python
from fealpy.mesh import TriangleMesh

mesh = TriangleMesh.from_box(
    box=[0.0, length_x, 0.0, length_y],
    nx=nx, ny=ny
)
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
ldof = uspace.number_of_local_dofs()   # 每个单元的自由度数
```

### 3. 线弹性静力分析

```python
from fealpy.fem import LinearElasticityIntegrator
from fealpy.fem import BilinearForm, LinearForm
from fealpy.fem import DirichletBC

# 材料参数
E = 210000.0    # 弹性模量 (MPa)
nu = 0.3        # 泊松比
lam = E * nu / ((1 + nu) * (1 - 2*nu))  # Lamé 第一参数
mu = E / (2 * (1 + nu))                  # Lamé 第二参数 (剪切模量)

# 刚度矩阵组装
integrator = LinearElasticityIntegrator(lam=lam, mu=mu)
bform = BilinearForm(uspace)
bform.add_domain_integrator(integrator)
A = bform.assembly()  # 稀疏刚度矩阵 (scipy.sparse.csr_matrix)

# 载荷向量（体力 + 面力）
lform = LinearForm(uspace)
# 如需施加体力或面力，添加对应的 integrator
F = lform.assembly()

# 边界条件 — 固定某面上的所有位移分量
# 找到 z ≈ 0 面上的节点
fixed_nodes = mesh.ds.boundary_face_flag()  # 边界标记
# 更精确的方式：根据坐标筛选节点
node_coords = mesh.entity('node')
fixed_mask = np.abs(node_coords[:, 2] - z_fixed) < 1e-6  # Z 坐标匹配
fixed_node_indices = np.where(fixed_mask)[0]

# 施加 Dirichlet BC (u_x = u_y = u_z = 0)
bc = DirichletBC(uspace, gd=np.zeros(3))
# 将固定节点的自由度索引加入 BC
# 注意：具体的 BC 施加方式依赖于 uspace 的结构

# 处理边界条件后求解
from scipy.sparse.linalg import spsolve
uh = spsolve(A, F)  # 位移解向量
```

### 4. 模态分析 (特征值求解)

```python
# 质量矩阵
from fealpy.fem import MassIntegrator
mintegrator = MassIntegrator(rho=density)
mform = BilinearForm(uspace)
mform.add_domain_integrator(mintegrator)
M = mform.assembly()

# 求解特征值问题 K·φ = ω²·M·φ
from scipy.sparse.linalg import eigs
n_modes = 6  # 前 6 阶
eigenvalues, eigenvectors = eigs(A, M=M, k=n_modes, sigma=0.0, which='LM')

# 固有频率 (Hz)
natural_frequencies = np.sqrt(np.abs(eigenvalues.real)) / (2 * np.pi)
# 按频率升序排列
idx = np.argsort(natural_frequencies)
natural_frequencies = natural_frequencies[idx]
eigenvectors = eigenvectors[:, idx]
```

### 5. 结果后处理

**从位移解计算应力**
```python
# uh 是位移向量，reshape 为 (n_nodes, 3)
uh_reshaped = uh.reshape(-1, 3)  # 每个节点的 (ux, uy, uz)

# 计算每个单元中心的应力
# 对每个单元，通过形函数导数计算应变，再乘以弹性矩阵得到应力
# fealpy 提供 strain/stress 后处理工具
```

### 6. 注意事项
- fealpy 是纯 Python 库，无需外部许可证
- 求解器使用 scipy.sparse.linalg.spsolve（直接求解器），适合中小规模问题
- 网格密度 nx/ny/nz 建议控制在使总节点数 < 50000
- 所有单位使用 mm-N-s 制
""",
}

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
from matplotlib.tri import Triangulation


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
            if mode_shapes_arr is not None and uh is not None:
                n_modes = min(len(freq_list), mode_shapes_arr.shape[1], 6)
                mode_images = []
                for mi in range(n_modes):
                    try:
                        mode_vec = mode_shapes_arr[:, mi].reshape(-1, 3)
                        mode_mag = np.sqrt(np.sum(mode_vec**2, axis=1))
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
                from fealpy.mesh import TriangleMesh
                # 简化：取所有节点的 (x,y) 做 Delaunay 三角剖分
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


# ——— 自动保存（如果脚本定义了需要的变量） ———
if __name__ == '__main__':
    # 尝试从局部命名空间寻找所需变量
    import inspect
    frame = inspect.currentframe()
    try:
        caller_locals = frame.f_back.f_locals if frame.f_back else {}

        _mesh = caller_locals.get('mesh')
        _uh = caller_locals.get('uh')
        _stress = caller_locals.get('stress_vm', caller_locals.get('stress'))
        _freqs = caller_locals.get('frequencies', caller_locals.get('natural_frequencies'))
        _modes = caller_locals.get('mode_shapes_arr', caller_locals.get('eigenvectors'))
        _proj = caller_locals.get('project_name', 'fealpy_simulation')

        if _mesh is not None and _uh is not None:
            _fealpy_save_results(
                mesh=_mesh,
                uh=_uh,
                stress_vm=_stress,
                frequencies=_freqs,
                mode_shapes_arr=_modes,
                project_name=_proj if isinstance(_proj, str) else 'fealpy_simulation',
            )
        else:
            # 尝试 globals
            g = globals()
            _mesh = g.get('mesh')
            _uh = g.get('uh')
            if _mesh is not None and _uh is not None:
                _fealpy_save_results(
                    mesh=_mesh,
                    uh=_uh,
                    stress_vm=g.get('stress_vm', g.get('stress')),
                    frequencies=g.get('frequencies', g.get('natural_frequencies')),
                    mode_shapes_arr=g.get('mode_shapes_arr', g.get('eigenvectors')),
                    project_name=g.get('project_name', 'fealpy_simulation'),
                )
            else:
                print("[MyAgent] 警告: 未找到 mesh/uh 变量，无法自动保存结果")
                print("[MyAgent] 请手动调用 _fealpy_save_results(mesh, uh, ...)")
    finally:
        del frame
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
4. 脚本末尾必须调用以下函数保存结果：
   ```python
   _fealpy_save_results(
       mesh=mesh,
       uh=uh,
       stress_vm=stress_vm,  # 如果计算了应力
       frequencies=natural_frequencies,  # 如果是模态分析
       mode_shapes_arr=eigenvectors,     # 如果是模态分析
       project_name="项目名称",
   )
   ```
5. 如果用户描述的是"梁"、"悬臂梁"、"简支梁"等结构，按如下规则建模：
   - 默认用 TetrahedronMesh.from_box()
   - 根据用户描述的尺寸设置 box=[0, Lx, 0, Ly, 0, Lz]
   - 固定端在 Z=0（或 X=0，取决于用户描述的朝向）
   - 材料默认用 steel，除非用户指定其他材料
6. 载荷施加在网格节点上（通过坐标定位节点索引，对相应自由度施加力）
7. 边界条件通过坐标定位节点后在相应自由度上置零
8. 只输出 Python 代码，用 ```python 和 ``` 包裹，不要输出额外的解释
9. **重要**: 输出的脚本末尾不要加 `if __name__ == '__main__':` 调用 — 系统会自动注入结果保存逻辑
10. 代码中包含必要的注释说明每个步骤
"""
```

- [ ] **Step 2: 验证知识库语法正确**

```bash
conda activate ccuse && python -c "from myagent.fealpy.knowledge import get_fealpy_system_prompt, FEALPY_RESULT_SAVER_CODE, DEFAULT_MATERIALS; print('knowledge.py OK'); print(f'材料: {list(DEFAULT_MATERIALS.keys())}'); print(f'system prompt 长度: {len(get_fealpy_system_prompt())} 字符')"
```

- [ ] **Step 3: 提交**

```bash
git add myagent/fealpy/__init__.py myagent/fealpy/knowledge.py
git commit -m "feat: 添加 fealpy 知识库 (knowledge.py)"
```

---

### Task 3: 创建 executor.py — Python 子进程执行器

**Files:**
- Create: `myagent/fealpy/executor.py`

- [ ] **Step 1: 编写执行器**

```python
"""fealpy 执行器 — 通过 subprocess 运行 fealpy Python 脚本"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

from myagent.cae.base import AbstractExecutor


class FealpyExecutor(AbstractExecutor):
    """fealpy 脚本执行器

    fealpy 是纯 Python 库，通过 subprocess.run("python script.py") 执行。
    默认使用当前 conda ccuse 环境的 Python。
    """

    def __init__(
        self,
        python_path: str = "",
        work_dir: str = "output",
        timeout: int = 3600,
    ):
        """初始化执行器

        Args:
            python_path: Python 解释器路径，空字符串 = 自动检测 (sys.executable)
            work_dir: 输出目录基础路径
            timeout: 执行超时时间（秒）
        """
        self.python_path = python_path or self._detect_python()
        self.work_dir = Path(work_dir)
        self.timeout = timeout
        self._ensure_work_dir()

    @staticmethod
    def _detect_python() -> str:
        """自动检测 Python 路径（优先使用当前环境的 Python）"""
        import sys
        return sys.executable

    def _ensure_work_dir(self):
        """确保输出目录存在"""
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        script_path: str,
        job_name: Optional[str] = None,
        **kwargs
    ) -> Dict:
        """执行 fealpy 仿真脚本

        Args:
            script_path: Python 脚本文件路径
            job_name: 作业名称

        Returns:
            执行结果字典：
            {
                "success": bool,
                "job_dir": str,
                "stdout": str,
                "stderr": str,
                "return_code": int,
                "duration": float,
                "error": str or None,
            }
        """
        script_path = Path(script_path)

        # 确定作业目录
        if job_name is None:
            job_name = script_path.stem

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_dir = self.work_dir / f"{job_name}_{timestamp}"
        job_dir.mkdir(parents=True, exist_ok=True)

        # 复制脚本到作业目录
        dest_script = job_dir / script_path.name
        shutil.copy2(script_path, dest_script)

        # ——— 预执行语法验证 ———
        script_content = dest_script.read_text(encoding="utf-8")
        try:
            compile(script_content, str(dest_script), "exec")
        except SyntaxError as e:
            error_msg = (
                f"脚本语法错误（可能由 LLM 输出截断导致）:\n"
                f"  文件: {dest_script.name}\n"
                f"  错误: {e.msg} (第 {e.lineno} 行)"
            )
            return {
                "success": False,
                "job_dir": str(job_dir),
                "stdout": "",
                "stderr": error_msg,
                "return_code": -1,
                "duration": 0.0,
                "error": error_msg,
            }

        # 构建命令
        command = f'"{self.python_path}" "{dest_script.name}"'

        print(f"\n[Fealpy Executor] 执行命令: {command}")
        print(f"[Fealpy Executor] 工作目录: {job_dir}")
        print(f"[Fealpy Executor] Python: {self.python_path}")

        start_time = datetime.now()

        try:
            # 继承当前环境变量（确保 conda ccuse 的 Python 能找到 fealpy）
            env = os.environ.copy()

            result = subprocess.run(
                command,
                shell=True,
                cwd=str(job_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
                errors="replace",
                env=env,
            )

            duration = (datetime.now() - start_time).total_seconds()
            stdout = result.stdout
            stderr = result.stderr
            return_code = result.returncode
            success = return_code == 0

            error = None
            if not success:
                error = self._extract_error(stdout, stderr)

        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            success = False
            return_code = -1
            stdout = ""
            stderr = ""
            error = f"仿真执行超时（超过 {self.timeout} 秒）"

        except FileNotFoundError:
            duration = 0
            success = False
            return_code = -1
            stdout = ""
            stderr = ""
            error = f"找不到 Python: {self.python_path}"

        # 保存执行日志
        log_path = job_dir / "execution.log"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"命令: {command}\n")
            f.write(f"Python: {self.python_path}\n")
            f.write(f"返回码: {return_code}\n")
            f.write(f"耗时: {duration:.1f} 秒\n\n")
            f.write("=== STDOUT ===\n")
            f.write(stdout + "\n")
            f.write("=== STDERR ===\n")
            f.write(stderr + "\n")

        return {
            "success": success,
            "job_dir": str(job_dir),
            "stdout": stdout,
            "stderr": stderr,
            "return_code": return_code,
            "duration": round(duration, 1),
            "error": error,
        }

    def _extract_error(self, stdout: str, stderr: str) -> str:
        """从 Python 输出中提取错误信息

        Args:
            stdout: 标准输出
            stderr: 标准错误

        Returns:
            格式化的错误消息
        """
        errors = []
        combined = stdout + "\n" + stderr

        # 常见 Python 错误模式
        patterns = [
            (r'Error:\s*(.*)', "错误"),
            (r'ModuleNotFoundError:\s*(.*)', "模块未找到"),
            (r'ImportError:\s*(.*)', "导入错误"),
            (r'SyntaxError:\s*(.*)', "语法错误"),
            (r'NameError:\s*(.*)', "名称错误"),
            (r'AttributeError:\s*(.*)', "属性错误"),
            (r'TypeError:\s*(.*)', "类型错误"),
            (r'ValueError:\s*(.*)', "值错误"),
            (r'File ".*", line \d+.*\n(.*)', "脚本错误"),
            (r'MemoryError', "内存不足"),
        ]

        for pattern, label in patterns:
            matches = re.findall(pattern, combined, re.IGNORECASE)
            for match in matches:
                errors.append(f"[{label}] {match.strip()}")

        if errors:
            return "\n".join(errors[-5:])

        tail = stderr.strip() or stdout.strip()
        if tail:
            lines = tail.split("\n")
            return "\n".join(lines[-10:])

        return "未知错误"
```

- [ ] **Step 2: 验证执行器导入**

```bash
conda activate ccuse && python -c "
from myagent.fealpy.executor import FealpyExecutor
e = FealpyExecutor(work_dir='output/test_fealpy')
print(f'Python 路径: {e.python_path}')
print(f'工作目录: {e.work_dir}')
print('FealpyExecutor 创建成功')
"
```

---

### Task 4: 创建 result.py — 结果读取器

**Files:**
- Create: `myagent/fealpy/result.py`

- [ ] **Step 1: 编写结果读取器**

```python
"""fealpy 结果提取 — 读取仿真输出文件和生成图片"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
import numpy as np

from myagent.cae.base import SimulationResult, AbstractResultReader


class ResultReader(AbstractResultReader):
    """fealpy 仿真结果读取器

    读取 fealpy 仿真完成后生成的 results.json 和图片文件。
    如果图片缺失，用 matplotlib 补生成。
    """

    @staticmethod
    def read(job_dir: str) -> SimulationResult:
        """读取 fealpy 仿真结果

        Args:
            job_dir: 仿真作业输出目录

        Returns:
            SimulationResult 对象
        """
        result = SimulationResult(job_dir)
        job_path = Path(job_dir)

        if not job_path.exists():
            result.error = f"作业目录不存在: {job_dir}"
            return result

        # 1. 读取 results.json
        json_path = job_path / "results.json"
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    result.results_json = json.load(f)
                if result.results_json.get("error"):
                    result.error = result.results_json["error"]
                else:
                    result.success = True
            except (json.JSONDecodeError, IOError) as e:
                result.error = f"读取 results.json 失败: {e}"
        else:
            result.error = ResultReader._diagnose_missing_results(job_path)

        # 2. 读取 paths.json (可选)
        paths_json = job_path / "paths.json"
        if paths_json.exists():
            try:
                with open(paths_json, "r", encoding="utf-8") as f:
                    result.paths_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        # 3. 查找结果图片
        image_extensions = {".png", ".jpg", ".jpeg", ".bmp"}
        for ext in image_extensions:
            for img_file in job_path.glob(f"*{ext}"):
                if img_file.name not in result.images:
                    result.images.append(img_file.name)
            for img_file in job_path.glob(f"*{ext.upper()}"):
                if img_file.name not in result.images:
                    result.images.append(img_file.name)

        return result

    @staticmethod
    def _diagnose_missing_results(job_path: Path) -> str:
        """诊断 results.json 缺失的原因

        Args:
            job_path: 作业目录

        Returns:
            诊断信息
        """
        parts = ["未找到 results.json"]

        py_files = list(job_path.glob("*.py"))
        log_files = list(job_path.glob("*.log"))
        png_files = list(job_path.glob("*.png"))

        if py_files:
            parts.append(f"脚本已生成 ({len(py_files)} 个 .py)")
        else:
            parts.append("脚本未生成 — 生成阶段可能失败")

        if log_files:
            # 读取最后几行
            try:
                log_path = log_files[0]
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = [l.strip() for l in f.readlines() if l.strip()]
                error_lines = [l for l in lines[-5:] if "error" in l.lower()]
                if error_lines:
                    parts.append(f"日志错误: {'; '.join(error_lines[-2:])}")
            except Exception:
                pass

        if png_files:
            parts.append(f"图片已生成 ({len(png_files)} 个) 但 results.json 缺失")

        if not py_files and not log_files:
            parts.append("脚本可能未正常执行 — 检查 fealpy 是否正确安装")

        return "; ".join(parts)
```

- [ ] **Step 2: 验证 result.py 导入**

```bash
conda activate ccuse && python -c "
from myagent.fealpy.result import ResultReader
print('ResultReader 导入成功')
# 测试读取不存在的目录
result = ResultReader.read('/nonexistent/path')
assert not result.success
assert result.error is not None
print(f'诊断: {result.error}')
print('ResultReader 基本逻辑验证通过')
"
```

---

### Task 5: 创建 generator.py — 脚本生成器

**Files:**
- Create: `myagent/fealpy/generator.py`

- [ ] **Step 1: 编写脚本生成器**

```python
"""fealpy 脚本生成器 — 将自然语言转化为 fealpy Python 脚本"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from myagent.config import get_config
from myagent.llm.factory import get_llm
from myagent.cae.base import AbstractScriptGenerator
from myagent.fealpy.knowledge import get_fealpy_system_prompt, FEALPY_RESULT_SAVER_CODE


class ScriptGenerator(AbstractScriptGenerator):
    """fealpy 脚本生成器

    使用 LLM 将用户的自然语言描述转化为 fealpy Python 仿真脚本。
    包含参数提取和脚本生成两个阶段。
    """

    PARAM_EXTRACTION_PROMPT = """你是一个有限元分析参数提取助手。
根据用户的自然语言描述，提取进行 fealpy 仿真所需的参数。

对于缺失的关键参数（载荷大小/方向、约束条件），标记为 "missing"。
对于次要参数（网格尺寸、分析类型），根据工程经验给出合理默认值。

请以 JSON 格式回复（只输出 JSON）：
{
    "analysis_type": "static / modal / static_modal",
    "geometry": {
        "description": "几何描述",
        "dimensions": {"length_mm": 1000, "width_mm": 50, "height_mm": 100}
    },
    "material": {
        "name": "材料名 (steel/aluminum/titanium)",
        "known": true
    },
    "loads": [
        {"type": "force", "magnitude_n": 1000, "direction": "y", "location": "自由端"}
    ],
    "boundary_conditions": [
        {"type": "fixed", "location": "固定端"}
    ],
    "mesh": {"size_mm": 5.0},
    "modal_settings": {"n_modes": 6},
    "missing_parameters": ["需追问的参数"],
    "questions": ["向用户追问的具体问题"]
}"""

    def __init__(self, model_name: Optional[str] = None, output_dir: Optional[str] = None):
        """初始化脚本生成器

        Args:
            model_name: LLM 模型名称，默认使用配置文件中的 default_model
            output_dir: 脚本输出目录
        """
        config = get_config()
        self.model_name = model_name or config.default_model
        self.llm = get_llm(self.model_name, config)
        self.output_dir = Path(output_dir or config.work_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        super().__init__()

    def extract_parameters(self, user_input: str) -> Dict:
        """从用户输入中提取仿真参数

        Args:
            user_input: 用户的自然语言描述

        Returns:
            参数提取结果字典
        """
        messages = [
            {"role": "system", "content": self.PARAM_EXTRACTION_PROMPT},
            {"role": "user", "content": user_input},
        ]

        response = self.llm.chat(messages, temperature=0.1, max_tokens=2000)

        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                params = json.loads(json_match.group())
            else:
                params = {"error": "无法解析参数", "raw_response": response}
        except json.JSONDecodeError as e:
            params = {"error": f"JSON 解析失败: {e}", "raw_response": response}

        self.extracted_params = params
        return params

    def generate_script(
        self,
        user_input: str,
        output_dir: Optional[str] = None,
        clarified_params: Optional[str] = None
    ) -> Tuple[str, str]:
        """生成 fealpy Python 仿真脚本

        Args:
            user_input: 用户的原始描述
            output_dir: 脚本输出目录
            clarified_params: 用户补充确认的参数信息

        Returns:
            (完整脚本内容, 脚本文件路径) 元组
        """
        user_message = f"请为以下仿真需求生成 fealpy Python 脚本：\n\n{user_input}"

        if clarified_params:
            user_message += f"\n\n补充确认的参数：\n{clarified_params}"

        user_message += (
            "\n\n你只需完成：网格生成、材料定义、有限元空间、刚度矩阵组装、"
            "边界条件施加、载荷施加、求解位移、计算应力。"
            "\n脚本末尾调用 _fealpy_save_results() 保存结果。"
        )

        messages = [
            {"role": "system", "content": get_fealpy_system_prompt()},
            {"role": "user", "content": user_message},
        ]

        response = self.llm.chat(
            messages,
            temperature=0.2,
            max_tokens=16384,
        )

        # 提取 Python 代码块
        script = self._extract_code(response)

        # ——— 强制注入结果保存代码 ———
        script = script.rstrip() + "\n\n" + FEALPY_RESULT_SAVER_CODE

        # ——— 语法验证 ———
        self._validate_script(script, "fealpy")

        # 保存脚本文件
        if output_dir:
            script_dir = Path(output_dir)
        else:
            script_dir = self.output_dir
        script_dir.mkdir(parents=True, exist_ok=True)

        script_path = script_dir / "fealpy_simulation.py"
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)

        return script, str(script_path)

    def _extract_code(self, response: str) -> str:
        """从 LLM 响应中提取 Python 代码块"""
        pattern = r'```python\s*\n(.*?)\n```'
        matches = re.findall(pattern, response, re.DOTALL)

        if matches:
            return "\n\n".join(matches)

        pattern = r'```\s*\n(.*?)\n```'
        matches = re.findall(pattern, response, re.DOTALL)

        if matches:
            return "\n\n".join(matches)

        lines = response.strip().split("\n")
        code_lines = []
        in_code = False

        for line in lines:
            if line.strip().startswith("import ") or line.strip().startswith("from "):
                in_code = True
            if in_code:
                code_lines.append(line)

        if code_lines:
            return "\n".join(code_lines)

        return response.strip()

    @staticmethod
    def _validate_script(code: str, context: str = ""):
        """验证生成的 Python 代码语法是否合法

        Args:
            code: 待验证的 Python 代码
            context: 生成上下文描述

        Raises:
            SyntaxError: 代码语法不合法
        """
        if not code or not code.strip():
            raise SyntaxError(
                f"fealpy 脚本生成失败 ({context}): LLM 返回了空脚本"
            )

        try:
            compile(code, "<fealpy_generated>", "exec")
        except SyntaxError as e:
            lines = code.rstrip().split("\n")
            last_line = lines[-1].strip() if lines else ""

            truncated = False
            reasons = []

            if last_line.endswith(":"):
                truncated = True
                reasons.append("末行以冒号结尾")

            incomplete_keywords = [
                "for", "if", "while", "def", "class", "with", "try",
                "elif", "else", "except", "finally",
            ]
            if last_line in incomplete_keywords:
                truncated = True
                reasons.append(f"末行仅有 '{last_line}' 关键字")

            open_parens = code.count("(") - code.count(")")
            open_brackets = code.count("[") - code.count("]")
            open_braces = code.count("{") - code.count("}")
            if open_parens > 0 or open_brackets > 0 or open_braces > 0:
                truncated = True
                parts = []
                if open_parens > 0:
                    parts.append(f"'(' 多 {open_parens}")
                if open_brackets > 0:
                    parts.append(f"'[' 多 {open_brackets}")
                if open_braces > 0:
                    parts.append(f"'{{' 多 {open_braces}")
                reasons.append(f"括号不匹配: {', '.join(parts)}")

            if truncated:
                raise SyntaxError(
                    f"fealpy 脚本生成失败 ({context}): LLM 输出疑似被截断 "
                    f"(max_tokens 不足)。\n"
                    f"截断特征: {'; '.join(reasons)}\n"
                    f"原始语法错误: {e.msg} (第 {e.lineno} 行)\n\n"
                    f"建议: 尝试简化模型描述或增大 LLM 的 max_tokens 参数。"
                ) from e
            else:
                raise SyntaxError(
                    f"fealpy 脚本生成失败 ({context}): {e.msg} (第 {e.lineno} 行)\n"
                    f"错误行: {code.split(chr(10))[e.lineno-1] if e.lineno and e.lineno <= len(code.split(chr(10))) else '?'}"
                ) from e

    def switch_model(self, model_name: str):
        """切换 LLM 模型

        Args:
            model_name: 新的模型名称
        """
        self.model_name = model_name
        self.llm = get_llm(model_name)
```

- [ ] **Step 2: 验证 generator 导入**

```bash
conda activate ccuse && python -c "
from myagent.fealpy.generator import ScriptGenerator
gen = ScriptGenerator()
print(f'模型: {gen.model_name}')
print('ScriptGenerator 创建成功')
# 验证 _validate_script
try:
    gen._validate_script('', 'test')
    assert False, '应该抛异常'
except SyntaxError as e:
    print(f'空脚本检测: OK')
gen._validate_script('import numpy as np\nprint(1)', 'test')
print('语法验证: OK')
"
```

---

### Task 6: 创建 __init__.py — 工厂注册

**Files:**
- Create: `myagent/fealpy/__init__.py`

- [ ] **Step 1: 编写注册文件**

```python
"""fealpy 操作层 — 脚本生成、执行、结果提取

fealpy 是纯 Python 有限元分析库，支持线弹性静力分析和模态分析。
作为 MyAgent 主推的 CAE 后端，提供零外部依赖的有限元仿真能力。
"""

from myagent.fealpy.generator import ScriptGenerator
from myagent.fealpy.executor import FealpyExecutor
from myagent.fealpy.result import ResultReader, SimulationResult
from myagent.fealpy.knowledge import get_fealpy_system_prompt

# 注册 fealpy 后端到 CAE 工厂
from myagent.cae.factory import register_backend


def _create_fealpy_generator(model_name, config):
    return ScriptGenerator(model_name=model_name)


def _create_fealpy_executor(config):
    return FealpyExecutor(
        python_path=config.fealpy_python_path,
        work_dir=config.work_dir,
        timeout=config.fealpy_timeout,
    )


register_backend(
    name="fealpy",
    generator_factory=_create_fealpy_generator,
    executor_factory=_create_fealpy_executor,
    result_reader_cls=ResultReader,
    display_name="fealpy",
)

__all__ = [
    "ScriptGenerator",
    "FealpyExecutor",
    "ResultReader",
    "SimulationResult",
    "get_fealpy_system_prompt",
]
```

- [ ] **Step 2: 验证后端注册**

```bash
conda activate ccuse && python -c "
from myagent.cae.factory import list_backends
backends = list_backends()
print(f'已注册后端: {backends}')
assert 'fealpy' in backends
print('fealpy 后端注册成功!')
"
```

- [ ] **Step 3: 提交 fealpy 包**

```bash
git add myagent/fealpy/
git commit -m 'feat: 添加 fealpy CAE 后端 (knowledge + generator + executor + result + factory)'
```

---

### Task 7: 修改 config.yaml 和 config.py

**Files:**
- Modify: `config.yaml`
- Modify: `myagent/config.py`

- [ ] **Step 1: 修改 config.yaml — 添加 fealpy 配置段并设置默认后端**

在 `config.yaml` 中：
- 修改 `cae.backend` 为 `fealpy`
- 添加 `fealpy:` 配置段

```yaml
# 修改前:
cae:
  backend: abaqus

# 修改后:
cae:
  backend: fealpy

# 在 nnw: 段后添加:
fealpy:
  python_path: ""
  work_dir: output
  timeout: 3600
```

使用 Edit 工具进行精确替换。

- [ ] **Step 2: 修改 config.py — 添加 fealpy 配置属性**

在 `config.py` 的 `nnw_solver_path` property 之后（约第 173 行），添加三个新属性：

```python
    # ——— fealpy 配置 ———

    @property
    def fealpy_config(self) -> Dict[str, Any]:
        """获取 fealpy 配置"""
        return self._config.get("fealpy", {})

    @property
    def fealpy_python_path(self) -> str:
        """获取 fealpy 使用的 Python 路径

        空字符串 = 自动检测当前环境的 Python (sys.executable)
        """
        val = self.fealpy_config.get("python_path", "")
        if not val:
            import sys
            return sys.executable
        return val

    @property
    def fealpy_work_dir(self) -> str:
        """获取 fealpy 输出目录"""
        return self.fealpy_config.get("work_dir", "output")

    @property
    def fealpy_timeout(self) -> int:
        """获取 fealpy 仿真超时时间（秒）"""
        return self.fealpy_config.get("timeout", 3600)
```

- [ ] **Step 3: 验证配置加载**

```bash
conda activate ccuse && python -c "
from myagent.config import get_config
config = get_config()
print(f'CAE 后端: {config.cae_backend}')
print(f'fealpy Python: {config.fealpy_python_path}')
print(f'fealpy work_dir: {config.fealpy_work_dir}')
print(f'fealpy timeout: {config.fealpy_timeout}')
print('fealpy 配置属性验证通过')
"
```

- [ ] **Step 4: 提交配置变更**

```bash
git add config.yaml myagent/config.py
git commit -m "feat: config 支持 fealpy 后端 — 新配置段 + 默认后端切换"
```

---

### Task 8: 修改 report.py — 支持模态分析

**Files:**
- Modify: `myagent/report.py`

- [ ] **Step 1: 在 ReportGenerator 类中添加模态分析 section**

在 `_detect_result_type` 方法中添加 fealpy 关键词：
```python
# 在 _detect_result_type 的返回前添加:
elif "natural_frequencies" in summary:
    self.result_type = "fea"  # 模态分析也用 FEA 主题
```

在 `_build_html_fea` 方法中，在 chart_section 之前添加模态 section：
```python
# 在 _build_html_fea 方法中，return 之前，{chart_section} 之后添加:
modal_section = self._build_modal_section()
```

并在 HTML 模板中加入 `{modal_section}`。

- [ ] **Step 2: 添加 `_build_modal_section` 方法**

```python
    def _build_modal_section(self) -> str:
        """构建模态分析 section — 固有频率表格 + 振型图"""
        summary = self.results.get('summary', {})
        frequencies = summary.get('natural_frequencies')
        
        if not frequencies:
            return ''
        
        # 固有频率表格
        freq_rows = []
        for i, freq in enumerate(frequencies):
            freq_rows.append(
                f'<tr><td>{i+1}</td><td>{freq:.2f}</td></tr>'
            )
        
        freq_table = (
            '<table style="width:100%;border-collapse:collapse;text-align:center;">'
            '<tr style="background:#f0f4f8;"><th>阶次</th><th>固有频率 (Hz)</th></tr>'
            + ''.join(freq_rows) +
            '</table>'
        )
        
        # 振型图
        mode_images_html = ''
        mode_shapes = self.results.get('mode_shapes', [])
        if mode_shapes:
            items = []
            for img_name in mode_shapes:
                if img_name in self.images_b64:
                    b64 = self.images_b64[img_name]
                    label = img_name.replace('_', ' ').replace('.png', '')
                    items.append(
                        f'<div class="contour-item">'
                        f'<img src="data:image/png;base64,{b64}" alt="{label}">'
                        f'<p>{label}</p>'
                        f'</div>'
                    )
            if items:
                mode_images_html = (
                    '<h3 style="margin-top:20px;">振型图</h3>'
                    f'<div class="contour-grid">{"".join(items)}</div>'
                )
        
        return (
            '<div class="section">'
            '<h2>模态分析</h2>'
            + freq_table +
            + mode_images_html +
            '</div>'
        )
```

- [ ] **Step 3: 修改 `_build_html_fea` 模板，插入 `modal_section`**

在 `_build_html_fea` 方法中，HTML 模板的 `{contour_section}` 之后、`{chart_section}` 之前插入 `{modal_section}`。

同时修改方法签名获取 modal_section：
```python
def _build_html_fea(self) -> str:
    ...
    modal_section = self._build_modal_section()
    
    return f"""...
    {contour_section}
    
    {modal_section}
    
    {chart_section}
    ..."""
```

- [ ] **Step 4: 验证修改后的 report 模块导入**

```bash
conda activate ccuse && python -c "
from myagent.report import ReportGenerator
print('ReportGenerator 导入成功（含模态分析支持）')
"
```

- [ ] **Step 5: 提交**

```bash
git add myagent/report.py
git commit -m "feat: report.py 新增模态分析 section — 固有频率表 + 振型图"
```

---

### Task 9: 编写测试 — test_fealpy.py

**Files:**
- Create: `tests/test_fealpy.py`

- [ ] **Step 1: 编写完整测试文件**

```python
"""fealpy 后端测试 — 覆盖 knowledge/generator/executor/result/factory/config"""

import json
import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from myagent.cae.factory import list_backends, create_generator, create_executor, get_result_reader
from myagent.cae.base import AbstractScriptGenerator, AbstractExecutor, AbstractResultReader, SimulationResult


class TestFealpyKnowledge:
    """知识库内容验证"""

    def test_materials_exist(self):
        from myagent.fealpy.knowledge import DEFAULT_MATERIALS
        assert "steel" in DEFAULT_MATERIALS
        assert "aluminum" in DEFAULT_MATERIALS
        assert "titanium" in DEFAULT_MATERIALS
        assert DEFAULT_MATERIALS["steel"]["elastic"] == [210000.0, 0.3]

    def test_system_prompt_returned(self):
        from myagent.fealpy.knowledge import get_fealpy_system_prompt
        prompt = get_fealpy_system_prompt()
        assert "fealpy" in prompt.lower()
        assert "mm-N-s" in prompt or "mm" in prompt
        assert len(prompt) > 500

    def test_saver_code_exists(self):
        from myagent.fealpy.knowledge import FEALPY_RESULT_SAVER_CODE
        assert "_fealpy_save_results" in FEALPY_RESULT_SAVER_CODE
        assert "results.json" in FEALPY_RESULT_SAVER_CODE

    def test_units_info_exists(self):
        from myagent.fealpy.knowledge import UNITS_INFO
        assert "mm" in UNITS_INFO

    def test_api_reference_exists(self):
        from myagent.fealpy.knowledge import FEALPY_API_REFERENCE
        assert "TetrahedronMesh" in FEALPY_API_REFERENCE
        assert "LagrangeFESpace" in FEALPY_API_REFERENCE


class TestFealpyFactory:
    """工厂注册验证"""

    def test_fealpy_in_backend_list(self):
        backends = list_backends()
        assert "fealpy" in backends

    def test_create_generator(self):
        from myagent.config import get_config
        config = get_config()
        gen = create_generator("fealpy", model_name=None, config=config)
        assert isinstance(gen, AbstractScriptGenerator)
        # 使用默认模型名
        assert gen.model_name is not None

    def test_create_executor(self):
        from myagent.config import get_config
        config = get_config()
        executor = create_executor("fealpy", config=config)
        assert isinstance(executor, AbstractExecutor)

    def test_get_result_reader(self):
        reader_cls = get_result_reader("fealpy")
        assert issubclass(reader_cls, AbstractResultReader)


class TestFealpyExecutor:
    """执行器测试"""

    def test_create_executor_directly(self):
        from myagent.fealpy.executor import FealpyExecutor
        executor = FealpyExecutor(work_dir="output/test_fealpy")
        assert executor.python_path
        assert "python" in executor.python_path.lower()
        assert executor.timeout == 3600

    def test_execute_syntax_error_script(self):
        """验证预执行语法检查能捕获语法错误"""
        from myagent.fealpy.executor import FealpyExecutor
        import tempfile

        executor = FealpyExecutor(work_dir=tempfile.mkdtemp())
        
        # 创建一个有语法错误的脚本
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("this is not valid python {{{")
            bad_script = f.name

        result = executor.execute(bad_script)
        assert result["success"] is False
        assert result["return_code"] == -1
        os.unlink(bad_script)

    def test_execute_simple_script(self):
        """验证能正常执行简单的 Python 脚本"""
        from myagent.fealpy.executor import FealpyExecutor
        import tempfile

        executor = FealpyExecutor(work_dir=tempfile.mkdtemp())

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("print('hello fealpy')\n")
            f.write("import json\n")
            f.write("json.dump({'summary': {'test': 1}}, open('results.json', 'w'))\n")
            good_script = f.name

        result = executor.execute(good_script)
        assert result["success"] is True
        assert result["return_code"] == 0
        # 验证 results.json 已生成
        job_dir = Path(result["job_dir"])
        assert (job_dir / "results.json").exists()
        os.unlink(good_script)


class TestFealpyResultReader:
    """结果读取器测试"""

    def test_read_nonexistent_dir(self):
        from myagent.fealpy.result import ResultReader
        result = ResultReader.read("/nonexistent/path/12345")
        assert result.success is False
        assert result.error is not None

    def test_read_empty_dir(self):
        from myagent.fealpy.result import ResultReader
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ResultReader.read(tmpdir)
            assert result.success is False
            assert "未找到 results.json" in result.error

    def test_read_valid_results_json(self):
        from myagent.fealpy.result import ResultReader
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建 results.json
            data = {
                "analysis_type": "static",
                "summary": {
                    "max_stress_mises": 120.5,
                    "max_displacement": 2.34,
                },
                "images": ["stress_mises.png"],
                "project_name": "test_beam",
            }
            with open(os.path.join(tmpdir, "results.json"), "w") as f:
                json.dump(data, f)

            # 创建一张假图片
            Path(tmpdir, "stress_mises.png").touch()

            result = ResultReader.read(tmpdir)
            assert result.success is True
            assert result.summary["max_stress_mises"] == 120.5
            assert "stress_mises.png" in result.images

    def test_read_modal_results_json(self):
        from myagent.fealpy.result import ResultReader
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {
                "analysis_type": "modal",
                "summary": {
                    "natural_frequencies": [145.3, 890.7, 1240.5],
                    "max_displacement": 0.01,
                },
                "mode_shapes": ["mode_1.png", "mode_2.png"],
                "images": ["mode_1.png", "mode_2.png"],
                "project_name": "modal_test",
            }
            with open(os.path.join(tmpdir, "results.json"), "w") as f:
                json.dump(data, f)

            result = ResultReader.read(tmpdir)
            assert result.success is True
            assert result.summary["natural_frequencies"] == [145.3, 890.7, 1240.5]
            assert len(result.results_json.get("mode_shapes", [])) == 2


class TestFealpyGenerator:
    """生成器测试"""

    def test_create_generator(self):
        from myagent.fealpy.generator import ScriptGenerator
        gen = ScriptGenerator()
        assert gen.model_name is not None

    def test_validate_empty_script(self):
        from myagent.fealpy.generator import ScriptGenerator
        with pytest.raises(SyntaxError):
            ScriptGenerator._validate_script("", "test")

    def test_validate_valid_script(self):
        from myagent.fealpy.generator import ScriptGenerator
        # 不应抛异常
        ScriptGenerator._validate_script("import numpy as np\nx = 1", "test")

    def test_validate_truncated_script(self):
        from myagent.fealpy.generator import ScriptGenerator
        with pytest.raises(SyntaxError) as exc_info:
            ScriptGenerator._validate_script("import numpy\ndef foo(", "test")
        assert "截断" in str(exc_info.value) or "括号不匹配" in str(exc_info.value)

    def test_extract_code_python_block(self):
        from myagent.fealpy.generator import ScriptGenerator
        gen = ScriptGenerator()
        response = "这是说明\n```python\nimport numpy\nx = 1\n```\n更多说明"
        code = gen._extract_code(response)
        assert "import numpy" in code
        assert "x = 1" in code
        assert "这是说明" not in code

    def test_extract_code_no_block(self):
        from myagent.fealpy.generator import ScriptGenerator
        gen = ScriptGenerator()
        response = "import numpy as np\nfrom fealpy.mesh import TetrahedronMesh\nprint('hello')"
        code = gen._extract_code(response)
        assert "import numpy" in code

    def test_param_extraction_prompt_exists(self):
        from myagent.fealpy.generator import ScriptGenerator
        assert "analysis_type" in ScriptGenerator.PARAM_EXTRACTION_PROMPT
        assert "missing_parameters" in ScriptGenerator.PARAM_EXTRACTION_PROMPT


class TestFealpyConfig:
    """配置属性验证"""

    def test_fealpy_config_properties(self):
        from myagent.config import get_config
        config = get_config()
        assert config.fealpy_python_path
        assert "python" in config.fealpy_python_path.lower()
        assert config.fealpy_work_dir
        assert config.fealpy_timeout > 0

    def test_cae_backend_default(self):
        from myagent.config import get_config
        config = get_config()
        assert config.cae_backend in ["fealpy", "abaqus", "nnw"]

    def test_fealpy_config_dict(self):
        from myagent.config import get_config
        config = get_config()
        cfg = config.fealpy_config
        assert isinstance(cfg, dict)
```

- [ ] **Step 2: 运行测试（无 LLM 依赖的部分）**

```bash
conda activate ccuse && python -m pytest tests/test_fealpy.py -v --tb=short -k "not (LLM or llm or chat)"
```

预期：18-20 个测试全部通过（不含需要 LLM API 的测试）。

- [ ] **Step 3: 提交**

```bash
git add tests/test_fealpy.py
git commit -m "test: 添加 fealpy 后端测试 (20 个)"
```

---

### Task 10: 运行全部已有测试 — 验证零回归

**Files:**
- (无修改，验证任务)

- [ ] **Step 1: 运行全部测试**

```bash
conda activate ccuse && python -m pytest tests/ -v --tb=short
```

预期：全部 84 + 20 = 104 个测试通过，或至少已有 84 个测试零回归。

- [ ] **Step 2: 如果有失败的已有测试，逐一修复**

检查失败原因，修复后再运行。

---

### Task 11: 更新文档

**Files:**
- Modify: `README.md`
- Modify: `PROJECT.md`
- Modify: `PROGRESS.md`

- [ ] **Step 1: 更新 README.md**

在项目结构中添加 fealpy：
```
│   ├── fealpy/            # 🆕 fealpy 操作层（主推 FEA 后端）
│   │   ├── knowledge.py   # 🆕 fealpy API 知识库
│   │   ├── generator.py   # 🆕 脚本生成器
│   │   ├── executor.py    # 🆕 Python 子进程执行器
│   │   └── result.py      # 🆕 结果读取器
```

在功能特性中添加 fealpy 描述，在环境要求中添加 fealpy pip 安装说明。

- [ ] **Step 2: 更新 PROJECT.md**

项目结构中添加 fealpy 包，外部依赖表添加 fealpy 条目。

- [ ] **Step 3: 更新 PROGRESS.md**

添加 Phase 7: fealpy 后端接入，更新当前状态。
在变更日志中添加今天的条目。

- [ ] **Step 4: 提交文档更新**

```bash
git add README.md PROJECT.md PROGRESS.md
git commit -m "docs: 更新文档 — fealpy 后端接入完成 (Phase 7)"
```

---

### Task 12: 端到端验收测试

**Files:**
- (验证任务，不需要修改代码)

- [ ] **Step 1: 验证工厂完整链路（无 LLM）**

```bash
conda activate ccuse && python -c "
from myagent.config import get_config
from myagent.cae.factory import list_backends, create_generator, create_executor, get_result_reader

config = get_config()
print(f'注册后端: {list_backends()}')
print(f'默认后端: {config.cae_backend}')

# 创建各组件
gen = create_generator('fealpy', model_name=None, config=config)
executor = create_executor('fealpy', config=config)
reader_cls = get_result_reader('fealpy')

print(f'Generator: {type(gen).__name__}')
print(f'Executor: {type(executor).__name__}')
print(f'ResultReader: {reader_cls.__name__}')
print('fealpy 后端工厂链路完整!')
"
```

- [ ] **Step 2: 验证 Web API 后端列表**

```bash
conda activate ccuse && python -c "
from myagent.web import app
from fastapi.testclient import TestClient
client = TestClient(app)
response = client.get('/api/backends')
data = response.json()
print(f'Web API 后端列表: {data}')
assert 'fealpy' in str(data)
print('Web API fealpy 后端验证通过!')
"
```

- [ ] **Step 3: 用自然语言算例进行完整端到端测试**

准备一个简单的自然语言输入，通过 MyAgent 的完整链路：

```bash
conda activate ccuse && python -c "
# 端到端测试：通过 fealpy 后端生成脚本并执行
from myagent.config import get_config
from myagent.cae.factory import create_generator, create_executor, get_result_reader

config = get_config()
print(f'使用后端: {config.cae_backend}')

# 1. 生成脚本
gen = create_generator(config.cae_backend, model_name=None, config=config)
script, script_path = gen.generate_script(
    '分析一个悬臂梁，长1000mm，矩形截面50x100mm，钢材料，自由端受向下1000N的力，网格尺寸20mm'
)
print(f'脚本已生成: {script_path}')
print(f'脚本长度: {len(script)} 字符')

# 2. 执行脚本
executor = create_executor(config.cae_backend, config=config)
result = executor.execute(script_path)
print(f'执行结果: {\"成功\" if result[\"success\"] else \"失败\"}')
print(f'作业目录: {result[\"job_dir\"]}')
if not result['success']:
    print(f'STDERR: {result.get(\"stderr\", \"\")[-500:]}')
    print(f'错误: {result.get(\"error\", \"\")}')

# 3. 读取结果
reader_cls = get_result_reader(config.cae_backend)
sim_result = reader_cls.read(result['job_dir'])
print(f'仿真结果: {\"成功\" if sim_result.success else \"失败\"}')
if sim_result.success:
    summary = sim_result.summary
    print(f'最大应力: {summary.get(\"max_stress_mises\", \"N/A\")} MPa')
    print(f'最大位移: {summary.get(\"max_displacement\", \"N/A\")} mm')
    print(f'图片: {sim_result.images}')
else:
    print(f'错误: {sim_result.error}')

# 4. 生成 HTML 报告
from myagent.report import ReportGenerator
report_path = ReportGenerator(result['job_dir'], solver_name='fealpy').generate()
if report_path:
    print(f'报告已生成: {report_path}')
else:
    print('报告生成失败: 数据不足')
"
```

预期：脚本生成成功，执行可能因 fealpy API 适配问题需要调整知识库。

- [ ] **Step 4: 根据端到端测试结果修复问题**

如果执行失败，分析 stderr 输出，调整 knowledge.py 中的 API 参考和 RESULT_SAVER_CODE。

- [ ] **Step 5: 最终提交**

```bash
git add -A && git commit -m "feat: fealpy CAE 后端接入完成 — Phase 7"
```
