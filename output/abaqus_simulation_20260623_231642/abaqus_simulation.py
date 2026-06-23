from abaqus import *
from abaqusConstants import *
from caeModules import *
import regionToolset

# -------------------------------------------------------------------
# 1. 创建模型
# -------------------------------------------------------------------
model = mdb.Model(name='Model-1')

# -------------------------------------------------------------------
# 2. 几何参数（单位：mm）
# -------------------------------------------------------------------
L       = 1000.0     # 圆筒长度
D       = 500.0      # 外径
t       = 5.0        # 壁厚
r_mid   = (D - t) / 2.0   # 中面半径 = 247.5 mm

# -------------------------------------------------------------------
# 3. 材料定义
#    密度换算：7800 kg/m^3 = 7.8e-9 ton/mm^3
# -------------------------------------------------------------------
mat = model.Material(name='Steel')
mat.Density(table=((7.8e-9, ), ))
mat.Elastic(table=((210000.0, 0.3), ))   # E = 210 GPa = 210000 MPa

# -------------------------------------------------------------------
# 4. 草图：XY 平面上的圆截线（圆心在原点，中面半径）
# -------------------------------------------------------------------
sketch = model.ConstrainedSketch(name='Sketch', sheetSize=2.0 * L)
sketch.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(r_mid, 0.0))

# -------------------------------------------------------------------
# 5. 部件：壳拉伸（沿 Z 轴）
# -------------------------------------------------------------------
part = model.Part(name='Tube', dimensionality=THREE_D, type=DEFORMABLE_BODY)
part.BaseShellExtrude(sketch=sketch, depth=L)

# -------------------------------------------------------------------
# 6. 截面属性（均质壳，厚度 = 壁厚）
# -------------------------------------------------------------------
model.HomogeneousShellSection(name='ShellSection', material='Steel', thickness=t)
part.SectionAssignment(
    region=regionToolset.Region(faces=part.faces),
    sectionName='ShellSection'
)

# -------------------------------------------------------------------
# 7. 装配
# -------------------------------------------------------------------
assembly = model.rootAssembly
instance = assembly.Instance(name='Tube-1', part=part, dependent=ON)

# -------------------------------------------------------------------
# 8. 分析步：频率提取（前 10 阶）
# -------------------------------------------------------------------
model.FrequencyStep(name='Step-1', previous='Initial', numEigen=10)
# 确保输出位移（振型）
model.fieldOutputRequests['F-Output-1'].setValues(variables=('U', ))

# -------------------------------------------------------------------
# 9. 边界条件：一端固定（Z = 0 的底边）
#    findAt 点在边缘上（中面上）
# -------------------------------------------------------------------
fixed_edge = instance.edges.findAt(((r_mid, 0.0, 0.0), ))
model.EncastreBC(
    name='Fixed',
    createStepName='Initial',
    region=regionToolset.Region(edges=fixed_edge)
)

# -------------------------------------------------------------------
# 10. 网格划分（S4R 壳单元）
# -------------------------------------------------------------------
elem_type = mesh.ElemType(elemCode=S4R, elemLibrary=STANDARD)
part.setElementType(regions=(part.faces, ), elemTypes=(elem_type, ))
part.seedPart(size=20.0)     # 全局种子尺寸 20 mm
part.generateMesh()

# -------------------------------------------------------------------
# 11. 创建并提交作业
# -------------------------------------------------------------------
job = mdb.Job(name='SimJob', model='Model-1')
job.submit()
job.waitForCompletion()


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
