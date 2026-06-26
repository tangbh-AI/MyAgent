# MyAgent 项目信息

## 基本信息

- **项目名称**: MyAgent — 多 CAE 后端自然语言智能助手
- **项目路径**: `D:\MyAgent`
- **版本**: 0.1.0
- **CAE 后端**: fealpy 3.4.0（主推 FEA）+ Abaqus 2024（结构 FEA）+ NNW-HyFLOW 1.1（CFD）

## 运行环境

- **Conda 环境**: `ccuse`
- **Python**: 3.10+
- **激活**: `conda activate ccuse`
- **安装**: `pip install -r requirements.txt && pip install -e .`
- **启动**: `conda activate ccuse && myagent`
- **Web 启动**: `conda activate ccuse && myagent-web`

## 外部依赖

| 依赖 | 版本 | 路径 | 必需 |
|------|------|------|------|
| fealpy | 3.4.0 | pip (conda ccuse) | 可选 |
| Abaqus | 2024 | `C:\SIMULIA\EstProducts\2024\` | 可选 |
| Abaqus 命令 | 2024 | `C:\SIMULIA\Commands\abaqus.bat` | 可选 |
| NNW-HyFLOW | 1.1 | `D:\NNW\NNW-HyFLOW_V1.1_win64_ed` | 可选 |
| PHengLEI 求解器 | — | `D:\NNW\NNW-HyFLOW_V1.1_win64_ed\X64\PHengLEIv3d0.exe` | 可选 |

## 项目结构

```
D:\MyAgent\
├── CLAUDE.md              # 项目规则（不可修改，简洁7条）
├── PROJECT.md             # 本文件 — 项目信息
├── README.md              # 说明文档
├── PROGRESS.md            # 进度追踪
├── config.yaml            # 用户配置（10个模型 + 2个CAE后端）
├── setup.py               # 安装配置
├── requirements.txt       # 依赖
├── myagent/               # 核心包
│   ├── main.py            # CLI 入口（多 CAE 后端）
│   ├── web.py             # Web 入口 (FastAPI + 多后端)
│   ├── static/            # Web 前端
│   │   ├── index.html     # 左右分栏页面
│   │   ├── app.js         # 前端逻辑 + 轮询
│   │   └── style.css      # 样式 + 响应式
│   ├── config.py          # 配置管理（含 CAE 后端选择）
│   ├── cae/               # CAE 抽象层
│   │   ├── base.py        # SimulationResult + 3 抽象基类
│   │   └── factory.py     # 后端注册表 + 工厂函数
│   ├── llm/               # LLM 抽象层
│   │   ├── base.py        # AbstractLLM 抽象基类
│   │   ├── openai_compat.py # OpenAI 兼容接口
│   │   ├── anthropic_llm.py # Anthropic 接口
│   │   └── factory.py     # 模型工厂
│   ├── fealpy/            # 🆕 fealpy 操作层（主推 FEA 后端）
│   │   ├── knowledge.py   # 🆕 fealpy API 知识库
│   │   ├── generator.py   # 🆕 脚本生成器
│   │   ├── executor.py    # 🆕 Python 子进程执行器
│   │   └── result.py      # 🆕 结果读取器
│   ├── abaqus/            # Abaqus 操作层（结构 FEA）
│   │   ├── generator.py   # ScriptGenerator (.py 脚本)
│   │   ├── executor.py    # AbaqusExecutor (abaqus.bat)
│   │   ├── result.py      # ResultReader (ODB 结果)
│   │   └── knowledge.py   # Abaqus API 知识库
│   ├── nnw/               # NNW-HyFLOW 操作层（CFD）
│   │   ├── generator.py   # ScriptGenerator (.hypara 文件)
│   │   ├── executor.py    # NNWExecutor (PHengLEIv3d0.exe)
│   │   ├── result.py      # ResultReader (aircoef.dat + tecflow.plt)
│   │   └── knowledge.py   # NNW CFD 知识库
│   ├── presenter.py       # 结果呈现
│   └── report.py          # 可视化报告生成 (FEA/CFD 双模式)
├── output/                 # 仿真输出
├── docs/                   # 设计文档
├── examples/               # 使用示例
│   └── nnw/                # NNW Demo 案例 (6 个)
└── tests/                  # 测试 (84 个全部通过)
```

## 架构概要

```
用户输入 (NL)
    │
    ▼
┌──────────────┐    ┌─────────────────┐
│   LLM 层     │    │  10 个 AI 模型  │
│  factory.py  │───▶│  OpenAI/Anthropic│
└──────────────┘    └─────────────────┘
    │ 提取参数 + 生成脚本
    ▼
┌──────────────┐    ┌─────────────────┐
│   CAE 层     │    │  2 个后端       │
│  factory.py  │───▶│  abaqus / nnw   │
└──────────────┘    └─────────────────┘
    │ 执行仿真 + 读取结果
    ▼
┌──────────────┐
│  Presenter   │───▶ 自然语言总结 + 图片
│  + Report    │───▶ HTML 可视化报告
└──────────────┘
```
