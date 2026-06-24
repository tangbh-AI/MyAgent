# PKPM-CAE 全自动仿真方案设计

> 状态: 设计中 | 日期: 2026-06-24

## 目标

用户打开 PKPM-CAE 桌面端（后台运行，设备已激活），在 MyAgent CLI/Web 中输入仿真需求，MyAgent 自动完成 PKPM-CAE 仿真并保存结果。**用户无需手动点击 PKPM-CAE GUI 的任何按钮。**

## 核心原则

- **仿真计算 100% 由 PKPM-CAE 官方可执行文件完成**，MyAgent 只做编排调度
- **稳定可靠优先**：多层 fallback，不因单一环节失败导致整体不可用
- **遵循官方约定**：组件路径从 app.conf 解析，I/O 约定遵循 prpc.json

## 求解链路对比

```
当前流程 (需要 GUI 点击):
  PyPCAE 脚本 → fe_modelSource.json → DB 注入 t_task
  → 用户打开 PKPM-CAE GUI → 点击"提交计算"
  → pserver → GenFea → result-processor → record.json

目标流程 (全自动):
  PyPCAE 脚本 → fe_modelSource.json
  → 梯队1: pserver REST API (认证增强)
  → 梯队2: 预留 WebSocket
  → 梯队3: 直接调用 GenFea → result-processor (稳定兜底)
  → record.json ✅
```

## 架构

```
myagent/pkpm/
├── api_client.py      # [修改] 增强认证探测 (4 种策略)
├── executor.py        # [修改] 三梯队 fallback 逻辑
├── solver_chain.py    # [新建] 直接求解器链编排器
├── generator.py       # [不变]
├── result.py          # [增强] 二进制格式解析 (已有研究)
└── knowledge.py       # [不变]
```

## 模块设计

### 1. solver_chain.py — 直接求解器链 (新建, ~200 行)

**职责**: 绕过 pserver, 直接调用 PKPM 官方可执行文件完成求解。

**调用链**:

```
fe_modelSource.json
    │
    ▼
GenFea.exe          ← PKPM 有限元求解器
    │ 工作目录: job_dir
    │ 输入: fe_modelSource.json
    │ 输出: Out*/ 目录 (二进制结果)
    │
    ▼
result-processor.exe ← PKPM 结果提取器
    │ 工作目录: job_dir
    │ 输入: Out*/ + fe_modelSource.json
    │ 输出: record.json (结构化结果)
    │
    ▼
record.json         ← 由 PkpmResultReader 解析
```

**类接口**:

```python
class SolverChain:
    def __init__(self, resources_dir: Path)
        # 从 app.conf 解析组件路径 (不硬编码)
    def run(self, job_dir: Path) -> ChainResult
        # 执行 GenFea → result-processor
    def _run_genfea(self, job_dir: Path) -> StageResult
        # 多策略尝试 GenFea 命令行参数
    def _run_result_processor(self, job_dir: Path) -> StageResult
        # 调用 result-processor.exe
    def _monitor(self, proc, job_dir) -> None
        # 轮询进度, 超时控制
```

**待逆向项 (实现阶段)**:
- GenFea.exe 命令行参数格式 → 从 pserver.log / pserver.db t_command 表提取
- 备选: 尝试无参调用 (工作目录 = job_dir, 自动查找模型文件)

**错误处理**: 每阶段收集 stdout/stderr/log.out, 封装为 `SolverError` 异常。

**超时**: GenFea 3600s, result-processor 120s, 均可配置。

### 2. api_client.py — 认证增强 (修改, ~80 行新增)

**职责**: 增强 pserver 认证探测能力, 利用 PKPM-CAE 已运行且设备已激活的前提。

**四种认证策略 (按优先级)**:

```
1. pserver.db t_token 表
   ├── 已有逻辑: SELECT token FROM t_token
   └── 🆕 增强: 尝试 t_record 表, token/value 字段变体

2. Electron 应用数据目录
   └── 🆕 搜索 %APPDATA%/PkpmCAE/, resources/data/
       匹配 auth/token/session/cookie 文件

3. 本地回环免认证
   └── 🆕 直接调用 /task/list 测试是否需要认证

4. 降级不认证
   └── 已有逻辑: 标记 _authenticated=False, 走后续 fallback
```

**新增方法**:

```python
class PkpmApiClient:
    def authenticate(self) -> bool
        # 🆕 依次尝试 4 种策略, 第一个成功即返回
    def _try_db_token(self) -> Optional[str]
        # 🔧 增强: 多表多字段探测
    def _try_electron_session(self) -> Optional[str]
        # 🆕 扫描 Electron 用户数据目录
    def _try_local_auth(self) -> bool
        # 🆕 测试本地回环是否免认证
```

### 3. executor.py — 三梯队 Fallback (修改, ~60 行改动)

**职责**: 编排执行策略, 自动从高到低降级。

```python
class PkpmExecutor:
    def _submit_with_fallback(self, job_dir, scene) -> Result:
        """三梯队自动 fallback"""

        # 梯队 1: pserver REST API (认证增强)
        if self.api.ensure_running() and self.api.authenticate():
            try:
                return self._api_submit(job_dir, scene)
            except Exception:
                pass  # → 梯队 3

        # 梯队 2: WebSocket 模拟 (预留, 本期不实现)
        # try: return self._ws_submit(job_dir, scene)
        # except: pass

        # 梯队 3: 直接求解器链 (稳定兜底)
        chain = SolverChain(self.install_path / "resources")
        return chain.run(job_dir)
```

## 数据流

```
用户输入: "悬臂梁 50x10x10mm 钢 100N"
    │
    ▼
PkpmScriptGenerator.extract_parameters()   # LLM 提取参数
    │
    ▼
PkpmScriptGenerator.generate_script()      # LLM 生成 PyPCAE 脚本
    │
    ▼
PkpmExecutor._run_python_script()          # 嵌入 Python 执行脚本
    │ → fe_modelSource.json
    │
    ▼
PkpmExecutor._submit_with_fallback()       # 🆕 三梯队提交
    │
    ├─[梯队1] pserver REST API /create + /start
    │   └─ wait_for_task() → Out*/ + record.json
    │
    └─[梯队3] SolverChain.run()
        ├─ GenFea.exe (job_dir) → Out*/
        └─ result-processor.exe (job_dir) → record.json
    │
    ▼
PkpmResultReader.read(job_dir)             # 读取 record.json + 二进制结果
    │
    ▼
Presenter.present()                        # 终端/Web 展示
ReportGenerator.generate()                 # HTML 报告
```

## 实现范围

### 本期实现
- [ ] `solver_chain.py` 新建 — GenFea + result-processor 编排
- [ ] `api_client.py` 认证增强 — 4 种策略
- [ ] `executor.py` 三梯队 fallback — 梯队 1 → 梯队 3

### 预留 (下期)
- [ ] 梯队 2: WebSocket 模拟 (需抓包逆向)
- [ ] `PkpmResultReader` 二进制格式解析增强

### 不在此范围
- PKPM-CAE 设备激活 (需要有效的许可证)
- 求解器链之外的 PKPM 功能 (如交互式建模 GUI 操作)

## 测试策略

| 层级 | 测试内容 | 方式 |
|------|---------|------|
| 单元测试 | SolverChain 路径解析、app.conf 解析 | 无需 PKPM 安装 |
| 集成测试 | GenFea.exe 无参调用验证 | 需 PKPM 安装 + fe_modelSource.json |
| 端到端 | 悬臂梁案例: NL → 脚本 → 求解 → 结果 | MyAgent 完整流水线 |
| 回归 | 现有 85 测试零回归 | CI |

## 风险与缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| GenFea 命令行参数未知 | 中 | 从 pserver.log / DB 提取历史命令；尝试无参调用 |
| pserver API 认证无法突破 | 高 | 梯队 3 直接链作为稳定兜底 |
| PKPM 版本更新改变组件路径 | 低 | 从 app.conf 动态解析，不硬编码 |
| 嵌入 Python 生成的 fe_modelSource.json 不兼容 GenFea | 低 | 端到端已验证通过 (Phase 7) |
