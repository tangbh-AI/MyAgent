"""Abaqus API 知识库 — 注入 LLM system prompt 的 API 参考

提供常用 Abaqus Python API 的简洁参考文档，
帮助 LLM 生成正确的 Abaqus 仿真脚本。
"""

# 默认材料属性（常用工程材料）
DEFAULT_MATERIALS = {
    "steel": {
        "name": "Steel",
        "density": 7.85e-9,      # ton/mm³
        "elastic": [210000.0, 0.3],  # E(MPa), ν
        "plastic": None,
        "yield_stress": 250.0,   # MPa
    },
    "aluminum": {
        "name": "Aluminum",
        "density": 2.7e-9,
        "elastic": [70000.0, 0.33],
        "plastic": None,
        "yield_stress": 270.0,
    },
    "titanium": {
        "name": "Titanium",
        "density": 4.5e-9,
        "elastic": [110000.0, 0.31],
        "plastic": None,
        "yield_stress": 880.0,
    },
}

# 常用单位制 (mm 制)
UNITS_INFO = """
Abaqus 默认使用 mm 单位制：
- 长度: mm
- 力: N
- 质量: ton (10³ kg)
- 应力: MPa (N/mm²)
- 密度: ton/mm³ (钢材 ≈ 7.85e-9)
- 弹性模量: MPa (钢材 E = 210000)
"""

# Abaqus Python API 参考（注入 system prompt）
ABAQUS_API_REFERENCE = """
## Abaqus Python API 参考（Abaqus 2024）

### 基础导入（必须放在脚本最开头）
```python
from abaqus import *
from abaqusConstants import *
from caeModules import *
import regionToolset
```

### 1. 创建模型
```python
# 创建新模型
model = mdb.Model(name='Model-1')

# 创建草图（默认 XY 平面）
# **注意**: ConstrainedSketch 没有 gridPlane 参数！不要传入 gridPlane！
sketch = model.ConstrainedSketch(name='Sketch', sheetSize=200.0)
# sketch.setPrimaryObject(option=SUPERIMPOSE)  # 可选
```

### 2. 创建部件 (Part)
```python
# 创建三维可变形实体部件
part = model.Part(name='Part-1', dimensionality=THREE_D, type=DEFORMABLE_BODY)

# 从草图拉伸创建
part.BaseSolidExtrude(sketch=sketch, depth=100.0)
```

### 2.5 薄壁圆筒/管壳创建（壳单元 Shell）

**中面半径计算**: `r_mid = (外径 - 壁厚) / 2.0`

**方法一（推荐）：圆截面拉伸成圆柱壳 `BaseShellExtrude`**
```python
# 中面半径
r_mid = (outer_diameter - thickness) / 2.0

# 草图：圆截面（圆心在原点，便于后续定位）
sketch = model.ConstrainedSketch(name='TubeProfile', sheetSize=2.0 * length)
sketch.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(r_mid, 0.0))

# 创建壳部件 + 拉伸（沿 Z 轴，深度 = 圆筒长度）
part = model.Part(name='Tube', dimensionality=THREE_D, type=DEFORMABLE_BODY)
part.BaseShellExtrude(sketch=sketch, depth=length)
```

**坐标约定**:
- 圆柱轴线沿 Z 轴，Z=0 为底端，Z=length 为顶端
- 固定端边界定位点：`instance.edges.findAt(((r_mid, 0.0, 0.0), ))`（底端圆周上一点）
- 加载端定位点：`instance.edges.findAt(((r_mid, 0.0, length), ))`（顶端圆周上一点）

**方法二（备选）：实体圆柱 + 抽壳**
```python
# 创建实体圆柱
sketch = model.ConstrainedSketch(name='SolidProfile', sheetSize=2.0 * outer_r)
sketch.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(outer_r, 0.0))
part = model.Part(name='Tube', dimensionality=THREE_D, type=DEFORMABLE_BODY)
part.BaseSolidExtrude(sketch=sketch, depth=length)

# 抽壳（移除顶面和底面，保留壁厚）
top_face = part.faces.findAt(((0.0, 0.0, length), ))
bottom_face = part.faces.findAt(((0.0, 0.0, 0.0), ))
part.Shell(thickness=thickness, faces=(top_face, bottom_face))
```

### 3. 材料定义 (Material)
```python
material = model.Material(name='Steel')
material.Density(table=((7.85e-9, ), ))
material.Elastic(table=((210000.0, 0.3), ))
```

### 4. 截面属性 (Section)
```python
# 创建截面并赋予部件
model.HomogeneousSolidSection(name='Section-1', material='Steel')
part.SectionAssignment(region=regionToolset.Region(cells=part.cells), sectionName='Section-1')
```

### 5. 装配 (Assembly)
```python
assembly = model.rootAssembly
instance = assembly.Instance(name='Instance-1', part=part, dependent=ON)
```

### 6. 分析步 (Step)

**静力分析步 (StaticStep)**
```python
model.StaticStep(name='Step-1', previous='Initial', nlgeom=OFF,
                 initialInc=0.1, maxInc=0.1, minInc=1e-08, maxNumInc=100)
```
**有效参数**: name, previous, nlgeom, initialInc, maxInc, minInc, maxNumInc, stabilizationMethod, adiabatic, timePeriod, timeIncrementation

**频率提取步 (FrequencyStep) — 模态分析**
```python
# 前 10 阶模态，Lanczos 求解器
model.FrequencyStep(name='Step-1', previous='Initial', numEigen=10,
                    eigensolver=LANCZOS, maxIterations=60,
                    shiftPoint=None, minEigen=None, maxEigen=None,
                    projectDamping=OFF, useBoundaryDamping=OFF)
```
**有效参数**: name, previous, numEigen, eigensolver, maxIterations, shiftPoint, minEigen, maxEigen, projectDamping, useBoundaryDamping
- `eigensolver`: LANCZOS（默认）, SUBSPACE, AMS
- `numEigen`: 提取的模态阶数
- **禁止使用 `acousticRange`、`acousticCoupling` 等声学参数**（FrequencyStep 不接受这些参数）

**场输出请求**
```python
model.fieldOutputRequests['F-Output-1'].setValues(
    variables=('S', 'U', 'RF', 'CF', 'E'))
```

### 7. 载荷与边界条件 (Load & BC)

**边界条件 — 固定约束 (ENCASTRE)**
```python
# findAt 坐标必须在目标面上（取面中心点）
fixed_face = instance.faces.findAt(((0.0, 0.0, 0.0), ))
model.EncastreBC(name='Fixed', createStepName='Initial',
                 region=regionToolset.Region(faces=fixed_face))
```

**集中力 — 必须用参考点 + 耦合约束（不要用 vertices.findAt）**
```python
# vertices.findAt() 极易因坐标不精确而失败
# 正确方式：在加载面形心创建参考点 → 创建 Set → 运动耦合整个面 → 在参考点上施力

# 1) 在加载面形心创建参考点（用 .id 获取ID，然后从仓库取对象）
rp_id = assembly.ReferencePoint(point=(center_x, center_y, center_z)).id
rp = assembly.referencePoints[rp_id]
# 将参考点放入集合（Coupling 的 controlPoint 需要 Set）
assembly.Set(name='RP', referencePoints=(rp, ))

# 2) 选取加载面并创建 Surface
load_face = instance.faces.findAt(((center_x, center_y, center_z), ))
assembly.Surface(name='LoadSurf', side1Faces=load_face)

# 3) 运动耦合（参考点驱动整个加载面）
model.Coupling(name='LoadCoupling', controlPoint=assembly.sets['RP'],
               surface=assembly.surfaces['LoadSurf'],
               influenceRadius=WHOLE_SURFACE, couplingType=KINEMATIC,
               localCsys=None,
               u1=ON, u2=ON, u3=ON, ur1=ON, ur2=ON, ur3=ON)

# 4) 在参考点上施加集中力
load_region = regionToolset.Region(referencePoints=(rp, ))
model.ConcentratedForce(name='Force', createStepName='Step-1',
    region=load_region, cf2=-1000.0)  # cf1=X, cf2=Y, cf3=Z
```

**压力载荷（直接作用在面上）**
```python
face_region = regionToolset.Region(faces=load_face)
model.Pressure(name='Pressure', createStepName='Step-1',
    region=face_region, magnitude=1.0)
```

### 8. 网格 (Mesh)
```python
# 设置单元类型
elemType = mesh.ElemType(elemCode=C3D8R, elemLibrary=STANDARD)
part.setElementType(regions=(part.cells, ), elemTypes=(elemType, ))

# 全局种子 + 划分网格
part.seedPart(size=5.0)
part.generateMesh()
```

### 9. 作业与求解 (Job)
```python
job = mdb.Job(name='SimJob', model='Model-1')
job.submit()
job.waitForCompletion()
```

### 注意事项
- **重要**: `ConstrainedSketch` 没有 `gridPlane` 参数！不要传入 `gridPlane=...`（这会导致 TypeError）
- **重要**: 草图默认在 XY 平面，Extrude 沿 Z 方向拉伸。如需其他方向，调整草图中的坐标即可
- **重要**: 脚本开头必须显式导入以下模块（cae noGUI 环境不会自动提供常量定义）：
  ```python
  from abaqus import *
  from abaqusConstants import *
  from caeModules import *
  ```
- **重要**: 施加集中力必须用参考点 + Kinematic Coupling 方式，禁止使用 `vertices.findAt()`（坐标极易不匹配）
- **重要**: `faces.findAt()` 坐标取该面的形心点即可
- `findAt()` 传入坐标元组格式: `((x, y, z), )`（双层括号）
- Region 用 `regionToolset.Region(faces=...)` / `regionToolset.Region(cells=...)` / `regionToolset.Region(referencePoints=...)` 构建
- 力的方向: cf1=X, cf2=Y, cf3=Z
- **重要**: **`FrequencyStep` 不接受 `acousticRange` 参数**！LLM 经常幻觉此参数。模态分析只用上面列出的有效参数
- **重要**: **禁止使用 `BaseShellRevolve` 创建圆柱壳**！在 cae noGUI 模式下，用平行于旋转轴的直线做 360° 旋转会几何创建失败。圆柱壳/管结构请使用 `BaseShellExtrude`（圆截面拉伸），见上文 2.5 节
- **壳结构坐标定位**: 壳的 faces/edges 用 `findAt()` 时，坐标点必须在壳中面上。圆柱壳中面半径 r_mid = (外径 - 壁厚) / 2
"""


def get_abaqus_system_prompt() -> str:
    """获取用于 LLM 的 Abaqus 系统提示词

    包含单位制说明和常用 API 参考，帮助 LLM 生成正确的 Abaqus 脚本。

    Returns:
        系统提示词字符串
    """
    materials_info = "\n".join(
        f"  - {name}: E={props['elastic'][0]}MPa, ν={props['elastic'][1]}, "
        f"σy={props['yield_stress']}MPa, ρ={props['density']}"
        for name, props in DEFAULT_MATERIALS.items()
    )

    return f"""你是一个 Abaqus 有限元仿真专家。根据用户的自然语言描述，
生成可以在 Abaqus 2024 中运行的 Python 脚本。

{UNITS_INFO}

## 预定义材料库（可直接使用）
{materials_info}

{ABAQUS_API_REFERENCE}

## 脚本生成规则
1. 生成的脚本必须能在 `abaqus cae noGUI=script.py` 环境下运行
2. **必须在脚本开头添加以下导入语句**（cae noGUI 模式下这些模块不会自动提供）：
   ```python
   from abaqus import *
   from abaqusConstants import *
   from caeModules import *
   import regionToolset
   ```
3. **集中力必须用参考点 + Kinematic Coupling 方式施加**，禁止使用 `vertices.findAt()`：
   - 用 `assembly.ReferencePoint(point=...).id` 创建参考点，用 `assembly.referencePoints[id]` 获取对象
   - 用 `assembly.Set(name='RP', referencePoints=(rp,))` 创建集合
   - 用 `assembly.Surface(name='...', side1Faces=...)` 创建加载面
   - Coupling 的 `controlPoint` 参数用 `assembly.sets['RP']`（Set 类型）
   - ConcentratedForce 的 region 用 `regionToolset.Region(referencePoints=(rp,))`
4. **不要**写结果提取代码——系统会自动在脚本末尾注入结果保存逻辑
5. **ConstrainedSketch 没有 gridPlane 参数**！不要使用 `gridPlane=...`，草图默认在 XY 平面即可
6. 你只需完成：建模 → 材料 → 截面 → 装配 → 分析步 → 载荷/边界 → 网格 → 作业提交
7. 作业命名使用 'SimJob'，模型命名使用 'Model-1'
8. 只输出 Python 代码，用 ```python 和 ``` 包裹，不要输出额外的解释
9. 代码中包含必要的注释说明每个步骤
10. **壳结构（薄壁圆筒/管）**必须用 `BaseShellExtrude` 方法
11. **`FrequencyStep` 只接受以下参数**：name, previous, numEigen, eigensolver, maxIterations, shiftPoint, minEigen, maxEigen, projectDamping, useBoundaryDamping。**严禁**使用 acousticRange、acousticCoupling 等参数——画圆截面再拉伸成圆柱壳，
   禁止使用 `BaseShellRevolve`（在 cae noGUI 下会失败）。
   中面半径 = (外径 - 壁厚) / 2。草图圆心在原点 (0,0)，拉伸沿 Z 轴，深度 = 圆筒长度。
   壳截面用 `HomogeneousShellSection`，厚度为壁厚。
"""

# ——— 内嵌结果保存代码（强制注入每个生成脚本的末尾） ———

RESULT_SAVER_CODE = r'''
# ============================================================
# 以下为 MyAgent 自动注入的结果保存代码
# ============================================================
import json
import os
import sys

def _myagent_save_results():
    """自动保存仿真结果：图片 + results.json

    此函数由 MyAgent 自动注入，确保每次仿真都有结果输出。
    """
    output_dir = os.getcwd()
    results = {"summary": {}, "images": []}
    odb = None

    try:
        # ---- 1. 打开 ODB ----
        odb_path = None
        for f in os.listdir(output_dir):
            if f.endswith('.odb'):
                odb_path = os.path.join(output_dir, f)
                break

        if odb_path is None:
            print("[MyAgent] 警告: 未找到 .odb 文件")
            results["error"] = "未找到 ODB 文件"
            _myagent_write_results(results, output_dir)
            return

        from odbAccess import openOdb
        odb = openOdb(odb_path)
        print(f"[MyAgent] 已打开 ODB: {odb_path}")

        # ---- 2. 提取数值结果 ----
        last_step = odb.steps.values()[-1]
        last_frame = last_step.frames[-1]
        summary = {}

        # von Mises 应力
        if 'S' in last_frame.fieldOutputs:
            stress_field = last_frame.fieldOutputs['S']
            mises_values = []
            for v in stress_field.values:
                if hasattr(v, 'mises') and v.mises is not None:
                    mises_values.append(v.mises)
            if mises_values:
                summary['max_stress_mises'] = round(max(mises_values), 2)
                summary['min_stress_mises'] = round(min(mises_values), 2)

        # 位移
        if 'U' in last_frame.fieldOutputs:
            disp_field = last_frame.fieldOutputs['U']
            disp_values = [v.magnitude for v in disp_field.values if v.magnitude is not None]
            if disp_values:
                summary['max_displacement'] = round(max(disp_values), 4)

        # 主应力
        if 'S' in last_frame.fieldOutputs:
            stress_field = last_frame.fieldOutputs['S']
            max_princ_values = []
            min_princ_values = []
            for v in stress_field.values:
                if hasattr(v, 'maxPrincipal') and v.maxPrincipal is not None:
                    max_princ_values.append(v.maxPrincipal)
                if hasattr(v, 'minPrincipal') and v.minPrincipal is not None:
                    min_princ_values.append(v.minPrincipal)
            if max_princ_values:
                summary['max_principal_stress'] = round(max(max_princ_values), 2)
            if min_princ_values:
                summary['min_principal_stress'] = round(min(min_princ_values), 2)

        results["summary"] = summary
        print(f"[MyAgent] 提取数值结果: {summary}")

        # ---- 3. 保存云图 ----
        from abaqusConstants import PNG, CONTOURS_ON_DEF, INVARIANT, INTEGRATION_POINT, NODAL, OFF

        viewport = session.viewports['Viewport: 1']
        viewport.setValues(displayedObject=odb)
        viewport.viewportAnnotationOptions.setValues(triad=OFF, legend=OFF, title=OFF, state=OFF)

        # 应力云图 (积分点)
        try:
            viewport.odbDisplay.setPrimaryVariable(
                variableLabel='S', outputPosition=INTEGRATION_POINT,
                refinement=(INVARIANT, 'Mises'))
            viewport.odbDisplay.display.setValues(plotState=CONTOURS_ON_DEF)
            stress_img = os.path.join(output_dir, 'stress_contour.png')
            session.printToFile(fileName='stress_contour', format=PNG,
                               canvasObjects=(viewport,))
            if os.path.exists(stress_img):
                results["images"].append('stress_contour.png')
                print("[MyAgent] 已保存: stress_contour.png")
        except Exception as e:
            print(f"[MyAgent] 应力云图失败: {e}")

        # 位移云图 (节点 — 位移是节点变量，不是积分点变量)
        try:
            viewport.odbDisplay.setPrimaryVariable(
                variableLabel='U', outputPosition=NODAL,
                refinement=(INVARIANT, 'Magnitude'))
            viewport.odbDisplay.display.setValues(plotState=CONTOURS_ON_DEF)
            disp_img = os.path.join(output_dir, 'displacement_contour.png')
            session.printToFile(fileName='displacement_contour', format=PNG,
                               canvasObjects=(viewport,))
            if os.path.exists(disp_img):
                results["images"].append('displacement_contour.png')
                print("[MyAgent] 已保存: displacement_contour.png")
        except Exception as e:
            print(f"[MyAgent] 位移云图失败: {e}")

        # ---- 4. 提取路径数据（用于外部 matplotlib 生成曲线图） ----
        _myagent_extract_paths(odb, output_dir, results)

    except Exception as e:
        print(f"[MyAgent] 结果保存出错: {e}")
        import traceback
        traceback.print_exc()
        results["error"] = str(e)

    finally:
        if odb is not None:
            try:
                odb.close()
            except:
                pass

    _myagent_write_results(results, output_dir)


def _myagent_write_results(results, output_dir):
    """写入 results.json"""
    result_path = os.path.join(output_dir, 'results.json')
    try:
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"[MyAgent] 已保存: results.json")
    except Exception as e:
        print(f"[MyAgent] 写入 results.json 失败: {e}")


def _myagent_extract_paths(odb, output_dir, results):
    """沿模型主轴采样节点数据，保存为 paths.json

    供外部 matplotlib 生成应力分布曲线、位移曲线、主应力曲线。
    非致命：失败时仅打印警告，不影响主流程。
    """
    try:
        last_step = odb.steps.values()[-1]
        last_frame = last_step.frames[-1]

        # ——— 1. 获取节点坐标 ———
        if 'U' not in last_frame.fieldOutputs:
            print("[MyAgent] 路径跳过: 无位移场")
            return
        disp_field = last_frame.fieldOutputs['U']

        # 从位移场值中收集所有节点标签
        node_labels = set()
        for v in disp_field.values:
            node_labels.add(v.nodeLabel)

        # 从 ODB assembly 所有实例收集节点坐标
        nodes = {}
        try:
            instances = list(odb.rootAssembly.instances.values())
            if not instances:
                return
            node_coords = {}
            for inst in instances:
                node_coords.update({n.label: n.coordinates for n in inst.nodes})
            for nl in node_labels:
                if nl in node_coords:
                    nodes[nl] = node_coords[nl]
        except Exception:
            pass

        if len(nodes) < 3:
            return

        # ——— 2. 计算包围盒，确定主轴 ———
        # 确保所有坐标为 Python 原生 float
        nodes_native = {nl: tuple(float(v) for v in c) for nl, c in nodes.items()}
        coords_items = list(nodes_native.items())
        xs = [c[0] for _, c in coords_items]
        ys = [c[1] for _, c in coords_items]
        zs = [c[2] for _, c in coords_items]
        ranges = {'X': max(xs)-min(xs), 'Y': max(ys)-min(ys), 'Z': max(zs)-min(zs)}
        main_dir = max(ranges, key=ranges.get)
        dir_idx = {'X': 0, 'Y': 1, 'Z': 2}[main_dir]
        # main_dir already set

        # ——— 3. 获取场数据 ———
        stress_field = last_frame.fieldOutputs['S'] if 'S' in last_frame.fieldOutputs else None
        stress_mises = {}
        max_princ = {}
        min_princ = {}
        if stress_field:
            for v in stress_field.values:
                if hasattr(v, 'mises') and v.mises is not None:
                    stress_mises[v.nodeLabel] = v.mises
                if hasattr(v, 'maxPrincipal') and v.maxPrincipal is not None:
                    max_princ[v.nodeLabel] = v.maxPrincipal
                if hasattr(v, 'minPrincipal') and v.minPrincipal is not None:
                    min_princ[v.nodeLabel] = v.minPrincipal

        disp_mag = {}
        for v in disp_field.values:
            if v.magnitude is not None:
                disp_mag[v.nodeLabel] = v.magnitude

        # ——— 4. 沿主轴采样 ———
        n_samples = 50
        c_min = min(c[dir_idx] for _, c in coords_items)
        c_max = max(c[dir_idx] for _, c in coords_items)

        stress_curve = []
        disp_curve = []
        max_princ_curve = []
        min_princ_curve = []

        for i in range(n_samples + 1):
            sample_pos = c_min + (c_max - c_min) * i / n_samples
            # 找最近的节点
            nearest = None
            nearest_dist = float('inf')
            for nl, c in coords_items:
                d = abs(float(c[dir_idx]) - sample_pos)
                if d < nearest_dist:
                    nearest_dist = d
                    nearest = nl
            if nearest is None:
                continue
            xv = float(round(sample_pos, 2))
            if nearest in stress_mises:
                stress_curve.append({'x': xv, 'y': float(round(float(stress_mises[nearest]), 2))})
            if nearest in disp_mag:
                disp_curve.append({'x': xv, 'y': float(round(float(disp_mag[nearest]), 4))})
            if nearest in max_princ:
                max_princ_curve.append({'x': xv, 'y': float(round(float(max_princ[nearest]), 2))})
                min_princ_curve.append({'x': xv, 'y': float(round(float(min_princ[nearest]), 2))})

        paths = {
            'main_axis': {'direction': main_dir, 'range': [float(round(c_min, 2)), float(round(c_max, 2))], 'unit': 'mm'},
            'curves': {}
        }
        if stress_curve:
            paths['curves']['stress_mises'] = stress_curve
        if disp_curve:
            paths['curves']['displacement'] = disp_curve
        if max_princ_curve:
            paths['curves']['max_principal_stress'] = max_princ_curve
            paths['curves']['min_principal_stress'] = min_princ_curve

        paths_path = os.path.join(output_dir, 'paths.json')
        with open(paths_path, 'w', encoding='utf-8') as f:
            json.dump(paths, f, ensure_ascii=False, indent=2)
        print(f"[MyAgent] 已保存 paths.json ({len(stress_curve)} 采样点, {len(paths['curves'])} 条曲线)")

    except Exception as e:
        print(f"[MyAgent] 路径提取失败 (非致命): {e}")


# 自动执行
_myagent_save_results()
'''
