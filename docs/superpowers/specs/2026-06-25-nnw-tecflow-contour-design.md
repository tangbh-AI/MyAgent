# NNW 流场云图生成 — 设计文档

## 背景

MyAgent NNW 后端的可视化报告需要包含 **流场云图** section（与参考报告一致），
展示 CFD 仿真结果中的马赫数、压力、密度、温度、速度分布。

当前 `report.py` 的 `_build_flowfield_section()` 和 `_build_result_images_section()` 
已实现，但缺少数据源 — `nnw/result.py` 未从 tecflow.plt 生成云图 PNG。

## 数据流

全部在 MyAgent 管道内：

```
tecflow.plt (PHengLEI 求解器输出)
  → nnw/result.py::_parse_tecflow_block()
     解析 Tecplot BLOCK 格式，提取结构化网格上的标量场
  → nnw/result.py::_generate_contour_plots()
     用 matplotlib 生成 5 张填充云图 PNG
  → _generate_plots() 将新图片加入结果列表
  → results.json 记录 images
  → report.py 自动嵌入报告
```

## 技术方案

### tecflow.plt BLOCK 格式

```
title="Flow Fields of PHengLEI"
variables="x", "y", "z", "density", "u", "v", "w", "pressure", "temperature", "mach"
zone T = "Zone0 Symmetry"
I = 25
J = 49
K = 1
f = BLOCK
<每个变量 I×J×K 个浮点数的连续块>
```

### 解析逻辑 (`_parse_tecflow_block`)

1. 逐行读取，跳过注释行
2. 从 `variables=` 行提取列名（逗号分隔，去引号）
3. 从 `I=`, `J=`, `K=` 行提取网格维度
4. 跳过其他头部行直到 `f = BLOCK`
5. `f = BLOCK` 之后所有行为数值
6. 总数值数 = n_vars × I × J × K
7. 按变量顺序每 `I×J×K` 个值为一组，reshape 为 `(J, I)` 2D 数组

### 云图变量 (5 张)

| 文件名 | 变量来源 |
|--------|----------|
| `contour_mach.png` | tecflow 直接输出 mach |
| `contour_pressure.png` | tecflow 直接输出 pressure |
| `contour_density.png` | tecflow 直接输出 density |
| `contour_temperature.png` | tecflow 直接输出 temperature |
| `contour_velocity.png` | sqrt(u² + v² + w²) 合成 |

### 绘图参数

- `matplotlib.pyplot.tricontourf` 填充云图（兼容非结构网格）
- 色条 bar + 中文标签
- DPI=150, bbox_inches='tight'
- 中文字体：SimHei / Microsoft YaHei

## 修改范围

**唯一修改文件**：`myagent/nnw/result.py`

- 新增 `_parse_tecflow_block(job_path: Path) -> Optional[Dict]` (~50行)
- 新增 `_generate_contour_plots(job_path: Path, tecflow_data: Dict) -> List[str]` (~45行)
- 修改 `_generate_plots()` — 在生成气动力曲线后增加 tecflow 云图生成调用 (~5行)

**不修改**：`report.py`（已就绪，自动识别 contour_*.png）

## 边界情况

- tecflow.plt 不存在 → 跳过，返回空列表
- 格式异常 → 打印警告，跳过
- 多 zone 文件 → 只处理第一个 zone（最常见情况）
- K > 1 → 取 K=1 对称面

## 验证

1. `python -m pytest tests/ -v` — 84 测试通过，无回归
2. 手动验证：用 NNW 后端跑一次仿真，检查生成的 analysis_report.html 包含流场云图 section
