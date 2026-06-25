"""NNW-HyFLOW 知识库 — 注入 LLM system prompt 的 CFD 参考

提供 NNW-HyFLOW 的 .hypara 参数文件格式参考，
以及 CFD 仿真常用参数说明，帮助 LLM 生成正确的配置。

NNW-HyFLOW (PHengLEI) 是基于有限体积法的 CFD 求解器，
支持结构/非结构/混合网格，可求解可压缩/不可压缩流动。
"""

# ——— .hypara 文件格式说明 ———
HYPARA_FORMAT_DOC = """
## .hypara 参数文件格式

NNW-HyFLOW 使用 C-like 语法的参数文件，每个参数一行:
  type name = value;
  type name = value1,value2,...;
  type name[] = [v1,v2,v3];
  string name = "...";

类型: int, double, string
注意: 每行必须以分号结尾，数组用方括号。

### 文件编码: 全部使用 UTF-8（不加 BOM）
"""

# ——— 常用 CFD 参数默认值 ———
CFD_DEFAULTS = {
    # 流动参数
    "refMachNumber": 0.5,         # 默认亚声速
    "attackd": 0.0,               # 攻角(度)
    "angleSlide": 0.0,            # 侧滑角(度)
    "refReNumber": 1.0e6,         # 雷诺数
    "refDimensionalTemperature": 288.15,  # 来流温度(K)
    "wallTemperature": 300.0,     # 壁温(K)或-1绝热壁
    "refGama": 1.4,               # 比热比(空气=1.4)
    "prl": 0.72,                  # 层流普朗特数
    "prt": 0.90,                  # 湍流普朗特数

    # 空间离散
    "inviscidSchemeName": "roe",  # 无粘通量格式: roe/vanleer/steger
    "str_limiter_name": "smooth", # 结构网格限制器: smooth/minmod/vencat
    "uns_scheme_name": "roe",     # 非结构网格格式
    "uns_limiter_name": "vencat", # 非结构网格限制器
    "gradientName": "ggnode",     # 梯度方法: ggnode/ggcell

    # 湍流模型
    "viscousType": 3,             # 1=层流, 2=无粘, 3=湍流
    "viscousName": "1eq-sa",      # 湍流模型: laminar/1eq-sa/sst/kw-sst
    "turbInterval": 1,            # 湍流方程求解间隔

    # 时间推进
    "tscheme": 4,                 # 4=LU-SGS隐式
    "ifLocalTimeStep": 0,         # 0=全局时间步, 1=当地时间步
    "CFLStart": 1.0,              # 起始CFL数
    "CFLEnd": 10.0,               # 最大CFL数
    "CFLVaryStep": 500,           # CFL爬升步数
    "nLUSGSSweeps": 3,            # LU-SGS扫描次数

    # 迭代控制
    "maxSimuStep": 20000,         # 最大迭代步
    "intervalStepFlow": 1000,     # 流场保存间隔
    "intervalStepForce": 100,     # 气动力输出间隔
    "intervalStepRes": 10,        # 残差输出间隔

    # 输出控制（可视化变量含义）
    # 0=密度 1=X速度 2=Y速度 3=Z速度 4=压力 5=温度
    # 6=马赫数 38=湍流涡粘系数
    "nVisualVariables": 7,
    "visualVariables": [0, 1, 2, 3, 4, 5, 6],
}

# ——— 典型工况模板 ———
SCENARIO_TEMPLATES = {
    "subsonic": """
# === 亚声速翼型/机翼 CFD 模板 ===
# 典型参数: Ma=0.5-0.8, Re=1e6-1e7
# 使用 SA 湍流模型, ROE 格式

cfd_para:
  int iunsteady = 0;  # 定常
  double refMachNumber = 0.73;
  double attackd = 2.0;
  double refReNumber = 6.5e6;
  int viscousType = 3;
  string viscousName = "1eq-sa";
  string inviscidSchemeName = "roe";
  string str_limiter_name = "smooth";
  double CFLStart = 1.0;
  double CFLEnd = 10.0;
  int maxSimuStep = 10000;
""",

    "supersonic": """
# === 超声速流动 CFD 模板 ===
# 典型参数: Ma=2.0-5.0, 激波捕捉
# 使用 Steger-Warming 格式或 ROE+熵修正

cfd_para:
  int iunsteady = 0;
  double refMachNumber = 3.0;
  double attackd = 1.0;
  double refReNumber = 1.0e7;
  int viscousType = 3;
  string viscousName = "1eq-sa";
  string inviscidSchemeName = "steger";
  double CFLStart = 0.1;
  double CFLEnd = 5.0;
  int roeEntropyFixMethod = 2;
""",

    "hypersonic": """
# === 高超声速流动 CFD 模板 ===
# 典型参数: Ma>5, 高温真实气体效应
# 可能需要化学反应模型

cfd_para:
  int iunsteady = 0;
  double refMachNumber = 10.0;
  double attackd = 0.0;
  double refReNumber = 1.0e5;
  int viscousType = 3;
  string viscousName = "1eq-sa";
  string inviscidSchemeName = "steger";
  double CFLStart = 0.01;
  double CFLEnd = 1.0;
  double refDimensionalTemperature = 288.15;
  int nchem = 5;  # 5组元空气
  string gasfile = "DK5";
""",
}

# ——— NNW-HyFLOW 核心 API 参考 ———
NNW_API_REFERENCE = """
## NNW-HyFLOW 参数文件生成规范

你需要生成以下 5 个配置文件（写入 job_dir/bin/ 目录）：

### 1. key.hypara — 主控文件
```c
string title = "PHengLEIMainParameterControlFile";
string defaultParaFile = "./bin/default_cfd_para.hypara";
int ndim = 3;               // 维度: 2 或 3
int nparafile = 1;          // 参数文件数量
int nsimutask = 0;          // 子任务数
string parafilename = "./bin/cfd_para.hypara";  // 指向 cfd 参数文件
int numberOfGridProcessor = 0;
string parafilename1 = "";
string parafilename2 = "";
```

### 2. cfd_para.hypara — CFD 求解参数（最重要的文件）
```c
// ——— 流动条件 ———
int iunsteady = 0;                // 0=定常, 1=非定常
double refMachNumber = ${Ma};     // 来流马赫数
double attackd = ${AoA};          // 攻角 (度)
double angleSlide = ${sideslip};  // 侧滑角 (度)
int inflowParaType = 0;           // 0=无量纲参数
double refReNumber = ${Re};       // 雷诺数 (单位长度)
double refDimensionalTemperature = ${T};   // 来流温度 (K)
double wallTemperature = ${Tw};            // 壁温 (K), -1=绝热壁
double gridScaleFactor = 1.0;     // 网格缩放

// ——— 参考量 ———
double forceReferenceLengthSpanWise = 1.0;
double forceReferenceLength = 1.0;
double forceReferenceArea = 1.0;
double refDimensionalPressure = 1.01313E05;
double refGama = 1.4;             // 比热比
double prl = 0.72;                // 层流 Prandtl
double prt = 0.90;                // 湍流 Prandtl

// ——— 空间离散 ———
string inviscidSchemeName = "roe";       // 无粘格式
string str_limiter_name = "smooth";     // 限制器 (结构网格)
string uns_scheme_name = "roe";         // 非结构网格格式
string uns_limiter_name = "vencat";     // 非结构网格限制器
string gradientName = "ggnode";         // 梯度方法
int ivencat = 7;                         // Venkat参数
double venkatCoeff = 5.0;
int roeEntropyFixMethod = 2;            // 熵修正
double roeEntropyScale = 1.0;

// ——— 湍流模型 ———
int viscousType = 3;                    // 1=层流, 3=SA湍流
string viscousName = "1eq-sa";          // laminar/1eq-sa/sst
int turbInterval = 1;
int mod_turb_res = 0;
int kindOfTurbSource = 0;
double freeStreamViscosity = 1.0e-3;

// ——— 时间推进 ———
int tscheme = 4;                        // 4=LU-SGS
int ifLocalTimeStep = 0;                // 0=全局时间步
double CFLStart = 1.0;
double CFLEnd = 10.0;
int CFLVaryStep = 500;
int nLUSGSSweeps = 3;
double LUSGSTolerance = 0.01;
double turbCFLScale = 1;

// ——— 迭代控制 ———
int maxSimuStep = 10000;
int intervalStepFlow = 1000;
int intervalStepPlot = 1000;
int intervalStepForce = 100;
int intervalStepRes = 10;

// ——— 气体模型 ———
int nchem = 0;                          // 组元数 (0=完全气体)
int nchemsrc = 1;
int nchemrad = 1;
int ntmodel = 1;                        // 温度模型 (1=单温)
double catalyticCoef = 0.0;
string gasfile = "DK5";                 // NNW 标准气体数据库                 // 气体数据库
string speciesName = "O,O2,NO,N,N2";
string initMassFraction = "0.0,0.233,0.0,0.0,0.767";

// ——— 网格 ———
string gridfile = "./grid/mesh.fts";    // 网格文件路径
int walldistMethod = 1;                 // 壁面距离计算方法

// ——— 输出文件 ———
string resSaveFile = "results/res.dat";           // 残差
string turbresfile = "results/turbres.dat";       // 湍流残差
string aircoeffile = "results/aircoef.dat";       // 气动力系数
string restartNSFile = "results/flow.dat";        // 流场重启
string turbfile = "results/turb.dat";             // 湍流重启
string visualfile = "results/tecflow.plt";        // 流场可视化
string wall_aircoefile = "results/wall_aircoef.dat";  // 壁面气动力

// ——— 可视化变量 ———
int nVisualVariables = 7;
int visualVariables[] = [0,1,2,3,4,5,6];   // ρ,u,v,w,p,T,Ma
```

### 3. grid_para.hypara — 网格导入参数
```c
int gridtype = 1;               // 1=仅结构, 0=混合
int axisup = 2;                 // 轴向: 1=X, 2=Y, 3=Z
int from_gtype = 2;             // 源网格格式: 2=CGNS
string from_gfile = "${grid_path}";  // 输入网格 (.cgns)
string out_gfile = "${fts_path}";    // 输出网格 (.fts)
```
注意: gridtype 含义
  0=混合网格, 1=结构网格
  axisup 含义: 1=X轴向上, 2=Y轴向上, 3=Z轴向上
  from_gtype 含义: 1=PLOT3D, 2=CGNS, 3=Fluent Case

### 4. boundary_condition.hypara — 边界条件
	注意：不同 bcType 需要不同参数！不要把远场参数放到壁面或对称面块中！
	bcName 必须与 CGNS 网格中的 patch 名称完全一致！

	```c
	int nBoundaryConditons = ${nbc};

	// —— 远场边界 (bcType=4) —— 需要来流参数 ——
	string bcName = "${farfield_name}";     // 通常是 "Farfield"
	{
	    int bcType = 4;
	    int inflowParaType = 0;
	    double attackd = ${AoA};
	    double angleSlide = ${sideslip};
	    double refDimensionalTemperature = ${T};
	    double refMachNumber = ${Ma};
	    double refReNumber = ${Re};
	}

	// —— 对称面 (bcType=3) —— 只需要 bcType ——
	string bcName = "${symmetry_name}";     // 通常是 "Symmetry"
	{
	    int bcType = 3;
	}

	// —— 壁面 (bcType=2) —— 只需要壁面参数，不需要来流参数！——
	string bcName = "${wall_name}";         // 必须与网格 patch 名称一致！
	{
	    int bcType = 2;
	    int reParaCheckBox = 0;
	    int twall_control_select = 0;
	    double wallTemperature = ${Tw};     // -1 = 绝热壁
	}
	// 如果有多个壁面 patch（如机翼上下表面），为每个 patch 各写一个块：
	string bcName = "${wall_name_2}";
	{
	    int bcType = 2;
	    int reParaCheckBox = 0;
	    int twall_control_select = 0;
	    double wallTemperature = ${Tw};
	}

	// —— 出口 (bcType=5) —— 只需要 bcType ——
	string bcName = "${outlet_name}";
	{
	    int bcType = 5;
	}
	```

	参数作用域规则（关键！）：
	- bcType=2 (壁面): 只需要 bcType, wallTemperature, reParaCheckBox, twall_control_select
	- bcType=3 (对称面): 只需要 bcType
	- bcType=4 (远场): 需要 bcType, inflowParaType, attackd, angleSlide, refMachNumber, refReNumber, refDimensionalTemperature
	- bcType=5 (出口): 只需要 bcType
	严禁把远场参数 (attackd, refMachNumber 等) 放入 Wall 或 Symmetry 块！

```

### 5. partition.hypara — 网格分区
	```c
	int pgridtype = 1;                                  // 1=结构网格, 0=非结构/混合
	int maxproc = ${ncpus};                             // MPI 进程数
	string original_grid_file = "${fts_path}";          // 输入网格 (.fts)
	string partition_grid_file = "${fts_path}";         // 分区后（单进程时与输入相同）
	int numberOfMultigrid = 1;                          // 多重网格层数
	```
	注意: pgridtype=1=结构网格, 0=非结构/混合
	单进程 (maxproc=1) 时 original_grid_file == partition_grid_file
"""

# ——— System Prompt ———
def get_nnw_system_prompt() -> str:
    """获取用于 LLM 的 NNW-HyFLOW 系统提示词

    包含 CFD 基础知识、.hypara 格式参考和生成规则。

    Returns:
        系统提示词字符串
    """
    return f"""你是一个 NNW-HyFLOW 计算流体力学 (CFD) 仿真专家。
NNW-HyFLOW 使用 PHengLEI 求解器，通过 .hypara 参数文件进行配置。

## 单位制
- 长度: 米 (m)
- 温度: 开尔文 (K)
- 压力: 帕斯卡 (Pa)
- 密度: kg/m³
- 速度: m/s
- 角度: 度 (°)

## 网格说明
- 用户需要提供计算网格文件（CGNS .cgns 格式，或 FTS .fts 格式）
- 如果用户只描述了网格路径，将其填入 gridfile 参数
- 3D 网格 ndim=3, 2D 网格 ndim=2

## 常用湍流模型选择
- 层流: viscousType=1, viscousName="laminar"
- SA 一方程: viscousType=3, viscousName="1eq-sa" (最常用)
- SST 两方程: viscousType=3, viscousName="sst"
- 无粘欧拉: viscousType=2

## 常用无粘通量格式
- "roe" — Roe 格式（通用性好）
- "vanleer" — Van Leer 矢通量分裂（超声速）
- "steger" — Steger-Warming 分裂（高超声速）
- "ausmpwplus" — AUSM+ 系列（全速域）

{HYPARA_FORMAT_DOC}

{NNW_API_REFERENCE}

## 边界条件参数作用域（关键！）
每个 bcType 只需要特定参数，不要把不相关的参数放入边界块：
- bcType=2 (Wall): 只需要 bcType, wallTemperature
- bcType=3 (Symmetry): 只需要 bcType
- bcType=4 (Farfield): 需要 bcType, inflowParaType, attackd, angleSlide, refMachNumber, refReNumber, refDimensionalTemperature
- bcType=5 (Outlet): 只需要 bcType
常见错误: 把远场参数 (attackd, refMachNumber 等) 放入 Wall 或 Symmetry 块 — 求解器会出错！

## 网格文件名一致性（关键！）
所有 .hypara 文件中的网格文件引用必须一致：
- CGNS 文件名 X.cgns → .fts 文件名必须为 X.fts
- grid_para.hypara: from_gfile="./grid/X.cgns", out_gfile="./grid/X.fts"
- cfd_para.hypara: gridfile="./grid/X.fts" (使用 .fts 文件)
- partition.hypara: original_grid_file="./grid/X.fts", partition_grid_file="./grid/X.fts"
严禁在不同文件中使用不同的文件名（如一个文件用 mesh.fts，另一个用 X.fts）！

## 生成规则
1. 只输出 .hypara 文件的内容，用以下标记分隔各个文件：
   ```
   ===FILE: key.hypara===
   (内容)
   ===FILE: cfd_para.hypara===
   (内容)
   ===FILE: grid_para.hypara===
   (内容)
   ===FILE: boundary_condition.hypara===
   (内容)
   ===FILE: partition.hypara===
   (内容)
   ```
2. 所有 .hypara 文件使用 UTF-8 编码
3. 每个参数语句必须以分号结尾
4. 网格路径如果用户未提供，使用 "./grid/mesh.cgns" 作为占位符
5. 根据用户描述的工况选择合适的默认参数:
   - 亚声速 (Ma<1.0): CFL=1~10, roe格式, SA湍流
   - 超声速 (1.0<Ma<5.0): CFL=0.1~5, steger或roe+熵修正
   - 高超声速 (Ma>5.0): CFL=0.01~1, steger格式
6. 2D 网格需设置 ndim=2, gridtype=0; 3D 网格 ndim=3
7. 不要输出额外的解释文字，只输出 ===FILE: ...=== 分隔的文件内容
"""
