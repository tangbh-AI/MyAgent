# 挑战赛提交准备 — 任务清单

> 给新对话的快速指引：阅读此文件了解接下来要做什么。

## 背景

为 "仿真软件 Agent 接入挑战赛" 准备提交文件夹 `D:\MyAgent\MyAgent-CAE_唐彬涵\`。
- **截止时间**: 2026年6月25日 23:59
- **主推后端**: fealpy（纯 Python FEA，新软件首个接入 → 50分基础分）
- **扩展后端**: Abaqus、NNW-HyFLOW（各 10 分基础分）
- **提交方式**: 按软件分别发邮件至 ai4is2026@163.com
  - 标题: `仿真软件 Agent 接入挑战赛提交 - 唐彬涵 - fealpy`
  - 附件: Agent 代码 + 环境说明 + 测试案例 + 运行结果 + 可视化报告

## 当前状态

- ✅ fealpy 后端代码已完成（`myagent/fealpy/` 5 个文件）
- ✅ 端到端测试通过（112 个测试，零回归）
- ✅ 2 个案例结果已生成（`output/e2e_demo/` + `output/e2e_clamped_beam/`）
- ⬜ **提交文件夹待整理** — 当前过时、臃肿（175MB examples + 376MB output）

## 任务清单（按顺序执行）

### 任务 1: 清理提交文件夹冗余文件
```
目标文件夹: D:\MyAgent\MyAgent-CAE_唐彬涵\

删除:
  - examples/nnw/ThreeD_*/  (6 个大型 NNW 网格目录，合计 175MB)
  - output/nnw_simulation_*/  (5 个冗余 NNW 运行，合计 330MB)
  - output/onera_m6_*/  (NNW 测试运行)
  - output/simply_supported_beam_*/  (开发测试)
  - output/_test_hypara, output/bin/, output/output/, output/test/
  - 所有 **/__pycache__/ 目录

保留:
  - output/abaqus_simulation_20260623_231642/  (1 个 Abaqus 参考)
```

### 任务 2: 更新 config.yaml
```
文件: MyAgent-CAE_唐彬涵\config.yaml

修改:
  1. cae.backend: nnw → fealpy
  2. 添加 fealpy 配置段:
     fealpy:
       python_path: ''
       work_dir: output
       timeout: 3600
  3. 软件路径脱敏:
     - C:\SIMULIA\Commands\abaqus.bat → C:\YOUR_ABAQUS_PATH\Commands\abaqus.bat
     - C:\SIMULIA\EstProducts\2024 → C:\YOUR_ABAQUS_PATH\EstProducts\2024
     - D:\NNW\NNW-HyFLOW_V1.1_win64_ed → D:\YOUR_NNW_PATH\NNW-HyFLOW_V1.1_win64_ed
  4. 确认所有 api_key 使用 ${ENV_VAR} 格式（不应有硬编码 Key）
```

### 任务 3: 同步最新源码到提交文件夹
```
从 D:\MyAgent\ 复制到 D:\MyAgent\MyAgent-CAE_唐彬涵\:

  myagent/fealpy/          (整个目录，5 个 .py 文件)
  myagent/report.py         (含模态 section 修复)
  myagent/main.py           (含 fealpy 导入)
  myagent/web.py
  myagent/config.py
  myagent/presenter.py
  myagent/cae/*.py
  myagent/llm/*.py
  README.md                 (fealpy 为主推的版本)
  PROGRESS.md               (含 Phase 7 + 端到端验收)
  PROJECT.md                (新建，项目信息)
  requirements.txt           (含 fealpy, scipy)
  tests/test_fealpy.py
  tests/test_fealpy_e2e.py
  tests/test_fealpy_complex.py
```

### 任务 4: 同步端到端案例结果
```
从 D:\MyAgent\output\ 复制到 D:\MyAgent\MyAgent-CAE_唐彬涵\output\:

  output/e2e_demo/          (悬臂梁 1000mm: 783KB HTML + 8 PNG + results.json)
  output/e2e_clamped_beam/  (固支梁 600mm: 683KB HTML + 8 PNG + results.json)
```

### 任务 5: 编写 fealpy_提交说明.md
```
新建: MyAgent-CAE_唐彬涵\fealpy_提交说明.md

参照格式: Abaqus_提交说明.md 和 NNW-HyFLOW_提交说明.md

必须包含:
  - 基本信息: 姓名=唐彬涵, 软件名=fealpy, Agent=MyAgent
  - 基本功能: 自然语言调用、真实案例运行(2个)、结果获取与可视化报告
  - 5 项扩展功能 (每项 2 分，共 10 分):
    1. 静力-模态联合分析与振型可视化
       (同时输出位移/应力/安全系数 + 前6阶固有频率 + 振型云图)
    2. 自研应力恢复与安全系数评估引擎
       (手写 B 矩阵 + Voigt 弹性矩阵 + Jacobian 逆变换 → von Mises + 安全系数)
    3. 高鲁棒性求解策略
       (手动 BC 替代 DirichletBC bug、质量矩阵 1e15、ARPACK which='SM'、截断检测)
    4. 多 AI 模型运行时切换
       (10 模型/双协议/终端一键切换/API Key 安全管理)
    5. Web 交互界面与自包含 FEA 报告系统
       (FastAPI + 左右分栏前端 + base64 内嵌 HTML 报告)
  - 环境配置: conda ccuse, pip install fealpy scipy, ${DEEPSEEK_API_KEY}
  - 2 个测试案例详情(含理论验证)
  - 附件清单
```

### 任务 6: 更新 examples/
```
文件: MyAgent-CAE_唐彬涵\examples\

  - examples/nnw/demo_cases_nl.md: 脱敏 D:\NNW\ 绝对路径 → <NNW_INSTALL_PATH>
  - 新建 examples/fealpy_demo_cases.md: 2 个 e2e 案例的自然语言描述 + 更多案例
```

### 任务 7: 最终隐私检查
```bash
# 在 MyAgent-CAE_唐彬涵 文件夹下运行:
grep -r "sk-" . --include="*.yaml" --include="*.py" --include="*.md"
# → 应无结果（无硬编码 API Key）

grep -r "D:\\\\NNW" examples/ --include="*.md"
# → 应无结果（仅占位符）

grep -r "D:\\\\NNW" config.yaml
# → 应仅见占位符路径

grep -r "C:\\\\SIMULIA" . --include="*.yaml"
# → 应仅见占位符路径

# 确认 __pycache__ 全部清理
find . -name "__pycache__" -type d
# → 应无结果
```

## 5 项扩展功能详细设计

| # | 功能名 | 区分度说明 |
|---|--------|-----------|
| 1 | 静力-模态联合分析与振型可视化 | 一次分析同时输出静力+模态结果，HTML报告含位移/应力云图+固有频率表+6阶振型图 |
| 2 | 自研应力恢复与安全系数评估引擎 | 手写B矩阵+Voigt弹性矩阵+Jacobian逆变换→von Mises→安全系数，不依赖fealpy内置后处理 |
| 3 | 高鲁棒性求解策略 | 手动BC(DirichletBC bug)、M对角1e15(防虚假模态)、which='SM'(防ARPACK不收敛)、LLM截断检测(5类特征) |
| 4 | 多AI模型运行时切换 | 10模型/Anthropic+OpenAI双协议/一键切换/model add/apikey管理 |
| 5 | Web交互与自包含FEA报告 | FastAPI+左右分栏前端+base64内嵌单文件HTML报告(离线可查看) |

## 验证

提交前最终确认:
1. `fealpy_提交说明.md` 存在且完整
2. `config.yaml` 中 `cae.backend: fealpy`
3. 运行 `pytest tests/ -q` 确认测试通过（如果 fealpy 未安装则至少语法正确）
4. `output/e2e_demo/analysis_report.html` 可在浏览器打开
5. 隐私检查全部通过（无硬编码 Key、无个人路径）
