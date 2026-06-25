# Phase 7 fealpy 后端 — 待完成任务

> 从任务 2 开始（任务 1 已完成：fealpy 已安装到 `D:/anaconda/envs/ccuse/`）

## 创建文件（按依赖顺序）

### 2. `myagent/fealpy/knowledge.py`
- 材料库 DEFAULT_MATERIALS (steel/aluminum/titanium, mm-N-s 单位制)
- UNITS_INFO 单位制说明
- FEALPY_API_REFERENCE: TetrahedronMesh.from_box / LagrangeFESpace / TensorFunctionSpace / LinearElasticityIntegrator / MassIntegrator
- FEALPY_RESULT_SAVER_CODE: 注入脚本末尾的结果保存代码
- get_fealpy_system_prompt(): 组装完整 system prompt
- ⚠️ BC 方案: DirichletBC 有 bug，引导 LLM 手动修改稀疏矩阵行/列

### 3. `myagent/fealpy/executor.py`
- FealpyExecutor(python_path, work_dir, timeout)
- python_path 默认 = `sys.executable`
- subprocess.run 执行 fealpy 脚本

### 4. `myagent/fealpy/result.py`
- ResultReader.read(job_dir) -> SimulationResult
- 读取 results.json / paths.json / PNG

### 5. `myagent/fealpy/generator.py`
- 完全复刻 Abaqus ScriptGenerator
- PARAM_EXTRACTION_PROMPT + generate_script() + _validate_script()

### 6. `myagent/fealpy/__init__.py`
- 注册 fealpy 后端到工厂

## 修改文件

### 7. config.yaml + config.py
- cae.backend: abaqus → fealpy
- 新增 fealpy 配置段 + 3 个属性

### 8. myagent/report.py
- _build_modal_section(): 固有频率表 + 振型图

### 9. tests/test_fealpy.py (~20 测试)

### 10. 运行全部测试 + 更新 README/PROJECT/PROGRESS

### 11. 端到端验收：自然语言悬臂梁算例

## 环境
- Python: `D:/anaconda/envs/ccuse/python.exe`
- fealpy: 3.4.0 已安装
- 项目: `D:/MyAgent`

## 关键参考
- 设计文档: `docs/superpowers/specs/2026-06-25-fealpy-backend-design.md`
- 实现计划: `docs/superpowers/plans/2026-06-25-fealpy-backend.md`
- 现有后端参考: `myagent/abaqus/` (generator / executor / result / knowledge)
