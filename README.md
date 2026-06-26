# MyAgent — 多 CAE 后端自然语言智能助手

MyAgent 是一个 CLI 智能体，将使用者的自然语言描述转化为 CAE 仿真操作，
自动执行仿真并将结果以图片和自然语言描述的方式呈现给使用者。

支持多种 CAE 后端：**fealpy**（主推 FEA 后端，纯 Python）、**Abaqus**（结构有限元分析）、**NNW-HyFLOW**（计算流体力学 CFD）。

## 功能特性

- 🗣️ **自然语言交互**: 用日常语言描述仿真需求，无需记忆 CAE 命令
- 🤖 **多模型支持**: 支持 DeepSeek、GLM、Claude 等多种 AI 模型，可随时切换
- 🔄 **多 CAE 后端**: 支持 fealpy（纯 Python FEA）、Abaqus（结构 FEA）、NNW-HyFLOW（CFD），一键切换
- 🔬 **模态分析**: fealpy 后端支持静力 + 模态分析，报告含固有频率表 + 振型图
- 📊 **可视化报告**: 自动生成 HTML 报告，含应力/位移/振型云图、频率表、曲线图等
- 📝 **智能总结**: AI 自动分析仿真结果，用自然语言解释关键数据
- 💬 **交互对话**: 多轮对话逐步细化仿真需求，智能追问缺失参数

## 环境要求

- **Python**: 3.10+
- **Conda 环境**: `ccuse`
- **fealpy**: 3.4.0（纯 Python FEA，pip 安装，必需）
- **Abaqus**: 2024（安装在 `C:\SIMULIA\`，可选）
- **NNW-HyFLOW**: 1.1（安装在 `D:\NNW\`，可选）
- **LLM API**: DeepSeek / GLM / Claude 等 API Key

## 快速开始

### 1. 激活环境

```bash
conda activate ccuse
pip install -r requirements.txt
pip install -e .
```

### 2. 配置

编辑 `config.yaml`，填入你的 API Key 和模型配置：

```yaml
models:
  - name: deepseek-v3
    provider: openai_compat
    api_key: your-deepseek-api-key
    base_url: https://api.deepseek.com/v1
    model_id: deepseek-chat

abaqus:
  command_path: C:\SIMULIA\Commands\abaqus.bat
  version: 2024

nnw:
  install_path: D:\NNW\NNW-HyFLOW_V1.1_win64_ed
  solver: X64/PHengLEIv3d0.exe
```

### 3. 启动

```bash
myagent
```

### 4. 使用示例

```
🤖 MyAgent> 你好，请描述你的仿真需求。

👤 用户> 分析一个悬臂梁，长1m，矩形截面50x100mm，
        钢材料，自由端1000N向下力

🤖 MyAgent> 我来确认参数：
        - 悬臂梁 L=1000mm, 截面 50×100mm
        - 材料: 钢 (E=210GPa, ν=0.3)
        - 载荷: 自由端 -1000N (Y方向)
        - 分析类型: 静力分析
        网格尺寸默认5mm，可以吗？

👤 用户> 可以

🤖 MyAgent> [生成Abaqus脚本...]
        [执行仿真中...]
        [提取结果...]

        📊 仿真完成！
        - 最大应力: 120 MPa (固定端上表面)
        - 最大位移: 2.3 mm (自由端)
        - 安全系数: 2.08 (屈服强度250MPa)

        🖼️ output/cantilever_beam/stress.png
        🖼️ output/cantilever_beam/displacement.png
```

## 交互命令

启动 MyAgent 后，支持以下终端命令：

### 模型管理
| 命令 | 说明 | 示例 |
|------|------|------|
| `models` | 列出所有可用模型 | `models` |
| `model <name>` | 切换 AI 模型 | `model glm-4` |
| `model default <name>` | 设置默认模型 | `model default deepseek-v4-pro` |
| `model add <名称> <provider> <model_id> [base_url] [api_key]` | 添加新模型 | `model add my-llm openai_compat gpt-4 https://api.x.com sk-xxx` |

### API Key 管理
| 命令 | 说明 | 示例 |
|------|------|------|
| `apikey set <模型名> <key>` | 设置/更新 API Key | `apikey set deepseek-v4-pro sk-xxx` |
| `apikey show [模型名]` | 查看 API Key（脱敏） | `apikey show` |

### CAE 后端切换
| 命令 | 说明 | 示例 |
|------|------|------|
| `backend` | 显示当前后端和可用列表 | `backend` |
| `backend list` | 列出所有可用后端 | `backend list` |
| `backend <name>` | 切换 CAE 后端 | `backend abaqus` |

## Web 端

启动 Web 服务：

```bash
myagent-web
```

浏览器打开 `http://127.0.0.1:8000`，可在网页中对话、切换 AI 模型和 CAE 后端，并下载仿真报告。

| 参数 | 说明 | 示例 |
|------|------|------|
| `--host` | 绑定地址（默认 127.0.0.1） | `--host 0.0.0.0` |
| `--port` | 端口号（默认 8000） | `--port 8080` |
| `--config`, `-c` | 指定配置文件 | `--config my_config.yaml` |

### 其他
| 命令 | 说明 |
|------|------|
| `help` | 显示帮助信息 |
| `clear` | 清空对话上下文 |
| `exit` / `quit` | 退出 MyAgent |

## CAE 后端扩展

添加新 CAE 后端只需 4 个步骤：
1. 创建 `myagent/<backend>/` 包，实现 3 个抽象基类
2. 在 `__init__.py` 中调用 `register_backend()` 注册
3. 在 `config.yaml` 添加后端配置段
4. 在 `config.py` 添加对应属性

## 命令行参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--model`, `-m` | 临时切换 AI 模型 | `myagent --model glm-4` |
| `--config`, `-c` | 指定配置文件路径 | `myagent --config my_config.yaml` |
| `--list-models`, `-l` | 列出所有可用模型 | `myagent --list-models` |

## 项目结构

```
D:\MyAgent\
├── CLAUDE.md              # 项目规则（不可修改，简洁7条）
├── PROJECT.md             # 项目信息（路径、环境、结构）
├── README.md              # 本文件
├── PROGRESS.md            # 开发进度
├── setup.py               # 安装配置
├── requirements.txt       # 依赖
├── config.yaml            # 用户配置
├── myagent/               # 核心包
│   ├── main.py            # CLI 入口（多 CAE 后端）
│   ├── web.py             # Web 入口 (FastAPI + 多后端)
│   ├── static/            # Web 前端
│   │   ├── index.html     # 左右分栏页面
│   │   ├── app.js         # 前端逻辑
│   │   └── style.css      # 样式
│   ├── config.py          # 配置管理（含 CAE 后端选择）
│   ├── cae/               # CAE 抽象层
│   │   ├── base.py        # SimulationResult + 3 抽象基类
│   │   └── factory.py     # 后端注册表 + 工厂函数
│   ├── llm/               # LLM 抽象层
│   ├── fealpy/            # 🆕 fealpy 操作层（主推 FEA 后端）
│   │   ├── knowledge.py   # 🆕 fealpy API 知识库
│   │   ├── generator.py   # 🆕 脚本生成器
│   │   ├── executor.py    # 🆕 Python 子进程执行器
│   │   └── result.py      # 🆕 结果读取器
│   ├── abaqus/            # Abaqus 操作层（结构 FEA）
│   ├── nnw/               # NNW-HyFLOW 操作层（CFD）
│   │   ├── knowledge.py   # NNW 知识库
│   │   ├── generator.py   # .hypara 文件生成器
│   │   ├── executor.py    # PHengLEI 求解器执行器
│   │   └── result.py      # CFD 结果解析器
│   ├── presenter.py       # 结果呈现
│   └── report.py          # 可视化报告生成
├── output/                 # 仿真输出
│   └── e2e_demo/           # 🆕 端到端样例报告（含模态 section）
├── docs/                   # 设计文档
├── examples/               # 使用示例
└── tests/                  # 测试 (111 个全部通过)
```

## 开发说明

- 所有开发使用 conda 环境 `ccuse`
- 每次代码变更后更新本文件和 `PROGRESS.md`
- 遵循 `CLAUDE.md` 中的项目规则
