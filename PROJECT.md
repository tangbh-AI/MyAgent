# MyAgent 项目信息

## 基本信息

- **项目名称**: MyAgent — Abaqus 自然语言智能助手
- **项目路径**: `D:\MyAgent`
- **Abaqus 版本**: 2024
- **Abaqus 安装路径**: `C:\SIMULIA\EstProducts\2024\`
- **Abaqus 命令**: `C:\SIMULIA\Commands\abaqus.bat`

## 运行环境

- **Conda 环境**: `ccuse`
- **激活**: `conda activate ccuse`
- **安装**: `pip install -r requirements.txt && pip install -e .`
- **启动**: `conda activate ccuse && myagent`

## 项目结构

```
D:\MyAgent\
├── CLAUDE.md              # 项目规则（不可修改）
├── PROJECT.md             # 本文件 — 项目信息
├── README.md              # 说明文档
├── PROGRESS.md            # 进度追踪
├── config.yaml            # 用户配置
├── myagent/               # 核心包
│   ├── main.py            # CLI 入口
│   ├── config.py          # 配置管理
│   ├── llm/               # LLM 抽象层
│   ├── abaqus/            # Abaqus 操作层
│   └── presenter.py       # 结果呈现
└── output/                 # 仿真输出
```
