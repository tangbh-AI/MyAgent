# MyAgent 接入 PKPM-CAE 实现计划

> **状态**: 📋 待执行（等待 PKPM-CAE 桌面端安装）  
> **创建日期**: 2026-06-24  
> **前置条件**: 用户安装 PKPM-CAE 桌面端后确认 API 接口

---

## 背景

MyAgent 当前仅支持 Abaqus 作为唯一的 CAE 后端。目标是新增 PKPM-CAE（国产 Web/桌面端有限元仿真平台，https://cae.pkpm.cn/）作为第二个后端。

PKPM-CAE 核心能力：
- 纯 Web 端/桌面端，云端计算，浏览器即用
- 支持 Python 脚本参数化建模
- 静力/模态/屈曲/动力学/谐响应等多种分析类型
- 支持导入 Abaqus/ANSYS 模型
- 有官方 pkpm-api PyPI 包

---

## 核心策略：参照 LLM 层建立 CAE 后端抽象

MyAgent 的 LLM 层（`myagent/llm/`）已有一个成熟的插件架构：`AbstractLLM` 抽象基类 + `_PROVIDER_REGISTRY` 注册表 + 工厂函数。CAE 后端层将采用完全相同的模式。

### 当前架构 vs 目标架构

```
当前 (仅 Abaqus)                    目标 (多后端)
─────────────────                  ────────────────
ScriptGenerator                    AbstractScriptGenerator (ABC)
    ↓                                  ├─ ScriptGenerator (Abaqus)
AbaqusExecutor                         └─ PkpmScriptGenerator (PKPM)
    ↓                              AbstractExecutor (ABC)
ResultReader                            ├─ AbaqusExecutor
    ↓                                   └─ PkpmExecutor
ReportGenerator                     AbstractResultReader (ABC)
                                        ├─ ResultReader (Abaqus)
                                        └─ PkpmResultReader (PKPM)
                                    ReportGenerator (后端无关)
```

---

## 文件变更清单

### 新增文件（9 个）

| 文件 | 职责 |
|------|------|
| `myagent/cae/__init__.py` | 导出核心 API |
| `myagent/cae/base.py` | `SimulationResult` 数据类 + 3 个抽象基类 |
| `myagent/cae/factory.py` | 后端注册表 + 工厂函数 |
| `myagent/pkpm/__init__.py` | PKPM-CAE 后端注册 |
| `myagent/pkpm/generator.py` | PKPM 脚本生成器（存根 → 待填实） |
| `myagent/pkpm/executor.py` | PKPM 远程/本地执行器（存根 → 待填实） |
| `myagent/pkpm/result.py` | PKPM 结果读取器（存根 → 待填实） |
| `myagent/pkpm/knowledge.py` | PKPM Python API 知识库（存根 → 待填实） |
| `tests/test_cae_factory.py` | 工厂 + 注册测试 |

### 修改文件（10 个）

| 文件 | 改动内容 | 改动量 |
|------|----------|--------|
| `myagent/abaqus/result.py` | `SimulationResult` 改为从 `cae.base` 导入（保留重导出） | ~5 行 |
| `myagent/abaqus/generator.py` | 继承 `AbstractScriptGenerator` | ~5 行 |
| `myagent/abaqus/executor.py` | 继承 `AbstractExecutor` | ~3 行 |
| `myagent/abaqus/__init__.py` | 添加 `register_backend("abaqus", ...)` | ~10 行 |
| `myagent/config.py` | 新增 `cae_backend`、`pkpm_*` 属性 | ~35 行 |
| `config.yaml` | 新增 `cae:` 和 `pkpm:` 配置段 | ~12 行 |
| `myagent/main.py` | 替换硬编码 Abaqus → 工厂调用 | ~30 行 |
| `myagent/web.py` | 替换硬编码 Abaqus → 工厂调用 | ~25 行 |
| `myagent/presenter.py` | "Abaqus" 文字参数化 | ~10 行 |
| `myagent/report.py` | 求解器名称参数化 | ~5 行 |
| `tests/test_result_reader.py` | 更新导入路径 | ~3 行 |

**不修改的文件**（保持原样）：
- `myagent/abaqus/knowledge.py` — Abaqus 专属，无需抽象
- `myagent/llm/` — 完全后端无关，零耦合
- `myagent/static/` — Web 前端，只通过 API 通信

---

## 实施步骤

### 步骤 1：创建 CAE 抽象层 `myagent/cae/`

**`myagent/cae/base.py`** 包含：

- `SimulationResult` 数据类 — 从 `abaqus/result.py` 移入，所有 CAE 后端共用。保留全部现有属性：`job_dir`、`success`、`results_json`、`images`、`raw_data`、`paths_data`、`error`，以及 `summary`、`max_stress`、`max_displacement`、`image_paths` 等 property。新增实例方法 `get_text_summary()`。

- `AbstractScriptGenerator(ABC)` — 抽象方法：
  - `extract_parameters(user_input) -> Dict`
  - `generate_script(user_input, clarified_params=None) -> Tuple[str, str]`
  - `switch_model(model_name)`
  - 具体方法：`has_missing_params()`、`get_clarification_questions()`

- `AbstractExecutor(ABC)` — 抽象方法：
  - `execute(script_path, **kwargs) -> Dict`（返回标准化的 `{"success", "job_dir", "stdout", "stderr", "return_code", "duration", "error"}`）

- `AbstractResultReader(ABC)` — 抽象静态方法：
  - `read(job_dir) -> SimulationResult`

**`myagent/cae/factory.py`** 包含：
```python
_BACKEND_REGISTRY: Dict[str, dict] = {}

def register_backend(name, generator_factory, executor_factory, result_reader_cls): ...
def create_generator(backend, model_name, config) -> AbstractScriptGenerator: ...
def create_executor(backend, config) -> AbstractExecutor: ...
def get_result_reader(backend) -> Type[AbstractResultReader]: ...
def list_backends() -> List[str]: ...
```

参考模板：`myagent/llm/base.py` + `myagent/llm/factory.py`

### 步骤 2：适配 Abaqus 模块（保持 100% 向后兼容）

- `abaqus/result.py`：`SimulationResult` 改为 `from myagent.cae.base import SimulationResult` 重导出；`ResultReader` 继承 `AbstractResultReader`
- `abaqus/generator.py`：`ScriptGenerator` 继承 `AbstractScriptGenerator`
- `abaqus/executor.py`：`AbaqusExecutor` 继承 `AbstractExecutor`
- `abaqus/__init__.py`：调用 `register_backend("abaqus", ...)` 注册

### 步骤 3：创建 PKPM-CAE 后端存根

创建 `myagent/pkpm/` 目录，5 个文件全部为存根：
- 完整实现抽象接口
- 内部逻辑返回占位值
- 代码注释标注 `# TODO: PKPM-CAE API 确认后填充`

**这是关键设计**：存根让架构现在就位，等 PKPM-CAE API 确认后，只需填充存根文件即可工作，不需要再动其他任何文件。

### 步骤 4：扩展配置

`config.yaml` 新增：
```yaml
cae:
  backend: abaqus  # abaqus | pkpm

pkpm:
  base_url: https://cae.pkpm.cn
  username: ${PKPM_USERNAME}
  password: ${PKPM_PASSWORD}
  work_dir: output
  timeout: 7200
```

`config.py` 新增属性（全部有安全默认值，旧配置完全兼容）：
- `cae_backend` → 默认 `"abaqus"`
- `pkpm_base_url`、`pkpm_username`、`pkpm_password`、`pkpm_work_dir`、`pkpm_timeout`

### 步骤 5：重构 main.py 和 web.py

`MyAgent._init_components()` 核心改动：
```python
# 旧：硬编码 Abaqus 类
self.generator = ScriptGenerator(model_name=self.model_name)
self.executor = AbaqusExecutor(abaqus_command=..., work_dir=..., timeout=...)

# 新：工厂创建
backend = self.config.cae_backend
self.generator = create_generator(backend, self.model_name, self.config)
self.executor = create_executor(backend, self.config)
self._result_reader_cls = get_result_reader(backend)
```

`web.py` 的 `run_simulation_pipeline()` 同样替换。

`presenter.py` 和 `report.py`：硬编码的 "Abaqus" 文本改为参数化（从后端名称获取）。

### 步骤 6：测试验证

1. 运行现有 50 个测试，确保 Abaqus 零回归
2. 新建 `test_cae_factory.py`：测试注册/创建
3. 验证 `list_backends()` 返回 `["abaqus", "pkpm"]`
4. 验证 CLI `myagent` 和 Web `myagent-web` 行为不变

---

## 向后兼容保证

| 保证项 | 方式 |
|--------|------|
| `from myagent.abaqus.result import SimulationResult` 仍可用 | `abaqus/result.py` 保留重导出 |
| 旧 `config.yaml`（无 `cae:`/`pkpm:` 段）兼容 | `cae_backend` 默认 `"abaqus"` |
| 现有 50 个测试无需修改 | 只改 factory 调用，不改 Abaqus 模块逻辑 |
| CLI/Web 入口行为不变 | 默认后端 abaqus，用户零感知 |
| Abaqus 功能零改动 | 只添加父类，不修改内部实现 |

---

## 接入 PKPM-CAE 桌面端时需要做的事

安装好 PKPM-CAE 桌面端后，需要确认以下信息才能填充存根：

1. **Python API 接口** — PKPM-CAE 的 Python 脚本 API 文档。脚本如何创建模型、定义材料、施加载荷、提交作业？
2. **命令行调用方式** — 本地执行脚本的命令是什么？（类似 `abaqus cae noGUI=script.py`）
3. **结果文件格式** — 仿真完成后生成什么格式的结果文件？如何读取应力/位移数据？
4. **鉴权方式** — 桌面端是否需要许可证/Token？

确认后，只需填充 `myagent/pkpm/` 下的 4 个存根文件即可完成接入。

---

## 参考

- LLM 抽象层模板：`myagent/llm/base.py` + `myagent/llm/factory.py`
- Abaqus 实现模板：`myagent/abaqus/generator.py` + `executor.py` + `result.py` + `knowledge.py`
- PKPM-CAE 官网：https://cae.pkpm.cn
- PKPM 在线文档：https://doc.pkpm.cn
