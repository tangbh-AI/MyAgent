# NNW-HyFLOW Demo 案例自然语言描述

将 6 个官方 Demo 案例转化为 MyAgent 的自然语言输入格式。
网格文件是 CFD 计算的必要条件（无法用自然语言生成），直接指定存储位置。

---

## 案例 1: ONERA M6 跨声速机翼绕流

```
对 ONERA M6 机翼进行 CFD 仿真分析。

网格文件: D:\NNW\NNW-HyFLOW_V1.1_win64_ed\bin\Demo\ThreeD_M6_Turbulence_Struct\grid\m6_str.cgns

来流条件:
  - 马赫数 Ma = 0.8395（跨声速）
  - 攻角 AoA = 3.06°
  - 侧滑角 = 0°
  - 雷诺数 Re = 1.171 × 10^7（单位长度）
  - 来流温度 T∞ = 288 K
  - 壁面为绝热壁（无热传导）

物理模型:
  - 湍流模型使用 SA 一方程模型 (Spalart-Allmaras)
  - 完全气体，比热比 γ = 1.4
  - 层流普朗特数 Prl = 0.72，湍流普朗特数 Prt = 0.9

数值格式:
  - 无粘通量: Roe 格式
  - 结构网格限制器: smooth
  - 梯度方法: Green-Gauss (ggnode)
  - 时间推进: LU-SGS 隐式，CFL 从 0.01 爬升到 5（500步）
  - 最大迭代步 200

输出:
  - 气动力系数（升力 CL、阻力 CD、俯仰力矩 Cm）
  - 流场可视化（密度、速度、压力、马赫数）
  - 残差收敛历史
  - 云图
```

---

## 案例 2: 30P30N 三段翼低速高攻角绕流

```
对 30P30N 三段翼型进行 2D CFD 仿真分析。

网格文件: D:\NNW\NNW-HyFLOW_V1.1_win64_ed\bin\Demo\TwoD_30p30n_SA_Struct\grid\30p30n_str.cgns

来流条件:
  - 马赫数 Ma = 0.2（低速）
  - 攻角 AoA = 19°（大攻角）
  - 侧滑角 = 0°
  - 雷诺数 Re = 9 × 10^6
  - 来流温度 T∞ = 288 K
  - 壁面绝热

物理模型:
  - SA 湍流模型
  - 完全气体

数值格式:
  - Roe 格式，smooth 限制器
  - LU-SGS 隐式，CFL 从 0.01 爬升到 10
  - 最大迭代步 200，2D 结构网格
```

---

## 案例 3: 平板低速层流边界层

```
对平板进行 2D 低速层流 CFD 仿真。

网格文件: D:\NNW\NNW-HyFLOW_V1.1_win64_ed\bin\Demo\TwoD_Plate_Laminar_Struct\grid\flat_laminar_73_81.fts

来流条件:
  - 马赫数 Ma = 0.1（极低速）
  - 攻角 AoA = 0°
  - 雷诺数 Re = 2 × 10^5
  - 来流温度 T∞ = 288.15 K

物理模型:
  - 层流（无湍流模型）
  - 完全气体

数值格式:
  - Roe 格式，无限限制器（nolim）
  - LU-SGS 隐式，CFL 从 0.01 爬升到 10
  - 2D 结构网格
  - 边界条件: 远场 + 入口 + 出口 + 壁面 + 对称面
```

---

## 案例 4: 高超声速圆柱绕流（HEG 工况）

```
对二维圆柱进行高超声速 CFD 仿真（模拟 HEG 激波风洞工况）。

网格文件: D:\NNW\NNW-HyFLOW_V1.1_win64_ed\bin\Demo\TwoD_Cylinder_OneTemperModel_Struct_Gu5\grid\2D_HEG_CYLINDER_65X88_DY2D-7.fts

来流条件:
  - 马赫数 Ma = 8.7569（高超声速）
  - 攻角 AoA = 0°
  - 雷诺数 Re = 4.70 × 10^5
  - 来流温度 T∞ = 694 K（高温来流）
  - 壁面温度 Tw = 300 K（等温壁）
  - 来流密度 3.207×10^-3 kg/m³
  - 来流速度 4775 m/s

物理模型:
  - 层流（高超声速下转捩前为层流）
  - 5 组元空气化学反应（O, O2, NO, N, N2）
  - 气体模型使用 Gu5
  - 来流组分质量分数: O=0.07955, O2=0.134, NO=0.0509, N=1e-9, N2=0.73555

数值格式:
  - 无粘通量: AUSMDV（全速域格式）
  - 结构网格限制器: minmod
  - Van Leer 矢通量分裂
  - LU-SGS 隐式，CFL 从 0.01 爬升到 10
  - 2D 结构网格 65×88
  - 熵修正方法 3
```

---

## 案例 5: RAM-C 返回舱高超声速再入

```
对 RAM-C 返回舱进行 3D 高超声速再入 CFD 仿真。

网格文件: D:\NNW\NNW-HyFLOW_V1.1_win64_ed\bin\Demo\ThreeD_Ramc_OneTemperModel_struct_DK7\grid\Ramc_dy1d-5.fts

来流条件:
  - 马赫数 Ma = 25.91（极高超声速）
  - 攻角 AoA = 0°
  - 雷诺数 Re = 3.61 × 10^4（稀薄效应显著）
  - 来流温度 T∞ = 216.85 K（高空低温）
  - 壁面温度 Tw = 1500 K（高温壁面，气动加热）
  - 来流密度 7.64×10^-5 kg/m³（60-80km 高空）
  - 来流速度 7662 m/s

物理模型:
  - 层流
  - 7 组元空气化学反应+电离（O, O2, NO, N, NO+, N2, e-）
  - 气体模型使用 DK7（含电子）
  - 单温模型

数值格式:
  - 无粘通量: AUSMDV
  - 限制器: minmod
  - Van Leer 分裂
  - LU-SGS 隐式，CFL 从 0.01 爬升到 10
  - 3D 结构网格
  - 最大迭代步 20000
```

---

## 案例 6: ELECTRE 标模锥体双温模型

```
对 ELECTRE 锥体进行 3D 高超声速 CFD 仿真（双温模型）。

网格文件: D:\NNW\NNW-HyFLOW_V1.1_win64_ed\bin\Demo\ThreeD_Electre_TwoTemperModel_struct_DK5\grid\Electre_Cone_Dy1d-6.fts

来流条件:
  - 马赫数 Ma = 12.935（高超声速）
  - 攻角 AoA = 0°
  - 雷诺数 Re = 1.63 × 10^5
  - 来流温度 T∞ = 265 K
  - 壁面温度 Tw = 343 K（等温壁）
  - 来流密度 7.00×10^-4 kg/m³
  - 来流速度 4230 m/s

物理模型:
  - 层流
  - 5 组元空气化学反应（O, O2, NO, N, N2）
  - 气体模型使用 DK5
  - **双温模型**（平动/转动温度 与 振动/电子温度 分别求解）
  - 振动温度初始 = 265 K

数值格式:
  - 无粘通量: AUSMDV
  - 限制器: minmod
  - Van Leer 分裂
  - LU-SGS 隐式，CFL 从 0.01 爬升到 5
  - 3D 结构网格，轴对称
  - 最大迭代步 20000
  - 可视化变量含振动温度 (变量33)
```

---

## 使用方式

在 MyAgent 中，先切换到 NNW 后端，然后输入任意案例的自然语言描述：

```
myagent> backend nnw
myagent> [粘贴上述任一案例的描述]
```

MyAgent 会提取参数（追问缺失项）、生成 `.hypara` 文件、运行 PHengLEI 求解器、
读取 `aircoef.dat` 输出气动力系数曲线和残差收敛图。
