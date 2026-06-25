# fealpy CAE 后端接入设计

## 概述

为 MyAgent 接入 fealpy（Python 开源有限元库，https://github.com/weihuayi/fealpy）作为第三个 CAE 后端，并设为主推的默认后端。

fealpy 是纯 Python 有限元分析库，由湘潭大学魏华祎团队开发，支持三角/四面体/四边形/六面体网格、Lagrange 有限元空间、线弹性求解、模态分析等。

**核心原则**：MyAgent 的 LLM 生成 fealpy Python 脚本 → subprocess 执行 → 读取结果 → 生成标准可视化报告。完全遵循现有 Abaqus/NNW 后端模式。

## 初期范围

- **仿真类型**：线弹性静力分析 + 模态分析（固有频率和振型）
- **网格方式**：仅自动生成网格（`from_box`），不需要外部网格文件
- **分析类型**：`static` / `modal` / `static_modal`

## 架构

```
用户自然语言输入
    │
    ▼
┌─────────────────────────────────────────────────┐
│  LLM (DeepSeek/GLM/Claude)                      │
│  + fealpy 知识库 → 生成 fealpy Python 脚本       │
└─────────────────────────────────────────────────┘
    │ fealpy_simulation.py
    ▼
┌─────────────────────────────────────────────────┐
│  FealpyExecutor                                  │
│  subprocess.run("python fealpy_simulation.py")   │
│  在 conda ccuse 环境下执行                        │
└─────────────────────────────────────────────────┘
    │ results.json + PNG 图片
    ▼
┌─────────────────────────────────────────────────┐
│  FealpyResultReader                              │
│  读取 results.json → SimulationResult            │
│  生成应力/位移/振型图片（matplotlib）             │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  ReportGenerator (FEA 模式复用)                  │
│  + 模态分析扩展：固有频率表 + 振型图              │
└─────────────────────────────────────────────────┘
```

## 文件变更清单

### 🆕 新增文件

| 文件 | 说明 |
|------|------|
| `myagent/fealpy/__init__.py` | 注册 fealpy 后端到 CAE 工厂 |
| `myagent/fealpy/knowledge.py` | fealpy API 知识库（注入 LLM system prompt） |
| `myagent/fealpy/generator.py` | 脚本生成器（LLM 参数提取 + 脚本生成） |
| `myagent/fealpy/executor.py` | Python 子进程执行器 |
| `myagent/fealpy/result.py` | 结果读取器 + matplotlib 图片生成 |
| `tests/test_fealpy.py` | fealpy 后端测试 |

### ✏️ 修改文件

| 文件 | 变更 |
|------|------|
| `config.yaml` | 新增 `fealpy:` 配置段；`cae.backend` 默认值改为 `fealpy` |
| `config.py` | 新增 `fealpy_python_path`、`fealpy_work_dir`、`fealpy_timeout` 属性 |
| `myagent/report.py` | 新增模态分析检测：固有频率表 + 振型图 section |
| `PROGRESS.md` | 更新进度为 Phase 7 |
| `README.md` | 更新项目结构、添加 fealpy 说明 |
| `PROJECT.md` | 更新项目结构、外部依赖 |

## 组件设计

### knowledge.py — 知识库

注入 LLM system prompt 的核心内容：

- **网格生成 API**：`TetrahedronMesh.from_box()` 参数说明
- **有限元空间**：`LagrangeFESpace` + `TensorFunctionSpace`（3D 位移场）
- **线弹性求解流程**：组装刚度矩阵、施加载荷/约束、求解位移、计算应力
- **模态分析流程**：组装质量矩阵、`scipy.sparse.linalg.eigs` 特征值求解
- **材料库**：钢 (E=210GPa, ν=0.3, ρ=7850)、铝 (E=70GPa, ν=0.33, ρ=2700)、钛 (E=110GPa, ν=0.34, ρ=4500)
- **结果保存模板**：`results.json` 的完整 JSON 格式规范 + matplotlib 画图代码模板
- **单位制**：mm-N-s 制（与 Abaqus 一致）

### generator.py — 脚本生成器

完全复刻 Abaqus 的 `ScriptGenerator` 结构：

- `PARAM_EXTRACTION_PROMPT`：提取线弹性/模态分析参数（几何、材料、载荷、约束、模态阶数）
- `extract_parameters()`：LLM 调用解析 JSON
- `generate_script()`：LLM 生成完整 fealpy Python 脚本，注入结果保存代码
- `_extract_code()`：正则提取 Python 代码块
- `_validate_script()`：语法验证，截断检测
- 生成的脚本末尾注入 `FEALPY_RESULT_SAVER_CODE` 确保 `results.json` 必定输出

### executor.py — 执行器

最简实现，核心逻辑：

```
1. 创建时间戳作业目录 (output/fealpy_simulation_YYYYMMDD_HHMMSS/)
2. 复制脚本到作业目录
3. 预执行语法验证 (compile)
4. subprocess.run([python_path, script_name], cwd=job_dir, timeout=3600)
5. 捕获 stdout/stderr，写 execution.log
6. 返回 {success, job_dir, stdout, stderr, return_code, duration, error}
```

`python_path` 默认使用当前 conda `ccuse` 环境的 Python（`sys.executable`），确保 fealpy 可用。

### result.py — 结果读取器

实现 `AbstractResultReader.read(job_dir) -> SimulationResult`：

1. 读取 `results.json`（检查 error 字段）
2. 读取 `paths.json`（可选，路径采样数据）
3. 扫描目录中的 PNG 图片
4. 如果脚本没有生成图片，用 matplotlib 补生成：
   - **应力云图**（von Mises 应力分布）
   - **位移云图**（总位移分布）
   - **振型图**（前 N 阶，存为 `mode_1.png` 等）
5. 返回标准 `SimulationResult`

### __init__.py — 工厂注册

```python
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
```

## results.json 格式

```json
{
  "analysis_type": "static",
  "summary": {
    "max_stress_mises": 120.5,
    "max_displacement": 2.34,
    "max_principal_stress": 135.2,
    "min_principal_stress": -15.8,
    "total_force": 1000.0,
    "safety_factor": 2.08,
    "material_yield_strength": 250.0,
    "natural_frequencies": [145.3, 890.7, 1240.5]
  },
  "mesh_info": {
    "n_nodes": 1520,
    "n_elements": 680,
    "element_type": "Tetrahedron",
    "mesh_size_mm": 5.0
  },
  "images": ["stress_mises.png", "displacement.png"],
  "mode_shapes": ["mode_1.png", "mode_2.png", "mode_3.png"],
  "project_name": "cantilever_beam"
}
```

关键：summary 字段名与 Abaqus 对齐（`max_stress_mises`、`max_displacement`），确保 `ReportGenerator` FEA 模式零改动。

## report.py 变更

在 `_build_html_fea()` 和 `_detect_result_type()` 中新增模态检测：

- 检测 `summary` 中是否有 `natural_frequencies` 字段
- 若有，生成「模态分析」section：
  - 固有频率表格（阶次 | 频率 Hz）
  - 振型图 grid（`mode_1.png` ~ `mode_N.png`）
- FEA 样式完全复用，不新增第三种主题

## config 变更

### config.yaml

```yaml
cae:
  backend: fealpy    # 默认后端从 abaqus 切换为 fealpy

fealpy:
  python_path: ""    # 空 = 自动检测当前 conda 环境的 Python
  work_dir: output
  timeout: 3600
```

### config.py

新增三个只读属性：
- `fealpy_python_path` — Python 路径（空时自动 `sys.executable`）
- `fealpy_work_dir` — 输出目录
- `fealpy_timeout` — 超时时间（秒）

## 测试计划

`tests/test_fealpy.py`（预计 10-12 个测试）：

- 知识库内容验证（材料库、API 参考存在）
- 参数提取 prompt 格式验证
- 工厂注册验证（`fealpy` 在 `list_backends()` 中）
- 执行器创建和配置验证
- 结果读取器（有 `results.json` 场景）
- 结果读取器（无 `results.json` 场景）
- 结果读取器（模态分析场景）
- Config 新属性验证
- Web API 后端列表演练
- 语法验证（空脚本 / 正常脚本 / 截断脚本）

## 安装依赖

```bash
conda activate ccuse
pip install fealpy
```

fealpy 的依赖（numpy, scipy, matplotlib）在 `ccuse` 中已存在，只需安装 fealpy 本体。

## 风险与约束

1. **fealpy API 稳定性**：fealpy 处于活跃开发期，API 可能变动。通过知识库锁定当前 API 版本，后续可更新。
2. **求解器性能**：fealpy 使用 scipy 稀疏求解器，适合中小规模问题（< 10万自由度）。大规模问题建议用 Abaqus。
3. **模态分析依赖**：需要 scipy 的 `eigs`，已在依赖中。
4. **LLM 对 fealpy 的了解**：fealpy 不是广为人知的库，知识库质量决定生成脚本质量。需要提供完整的 API 参考和示例。
