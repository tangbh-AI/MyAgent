# MyAgent 使用示例

> 这些示例帮助您快速上手 MyAgent。

## 目录

| 文件 | 说明 |
|------|------|
| `sample_inputs.txt` | 典型仿真需求描述（5 个场景），可在 MyAgent CLI 中直接粘贴使用 |
| `config_template.yaml` | 安全的配置模板（所有 API Key 使用环境变量引用） |

## 使用方法

### 1. 从模板创建配置

```bash
# 复制配置模板
cp examples/config_template.yaml config.yaml

# 编辑 config.yaml，设置你的 API Key 环境变量
# 所有 Key 使用 ${VAR_NAME} 环境变量引用，确保安全
```

### 2. 设置环境变量

```bash
# 必须设置（DeepSeek 系列）
export DEEPSEEK_API_KEY=sk-your-deepseek-key

# 按需设置
export GLM_API_KEY=your-glm-api-key
export QWEN_API_KEY=your-qwen-api-key
export ANTHROPIC_API_KEY=your-anthropic-api-key
```

### 3. 启动 MyAgent

```bash
conda activate ccuse
myagent
```

### 4. 粘贴示例需求

打开 `sample_inputs.txt`，选择任意场景描述，粘贴到 MyAgent 的 `👤 用户>` 提示符下。

### 示例场景

1. **悬臂梁静力分析** — 最基本的入门场景，验证系统流程
2. **平板模态分析** — 动力特性分析
3. **轴扭转分析** — 扭矩载荷
4. **压力容器分析** — 内压载荷
5. **热应力分析** — 温度场 + 结构耦合
