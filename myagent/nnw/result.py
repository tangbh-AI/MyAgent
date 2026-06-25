"""NNW-HyFLOW 结果读取 — 解析 CFD 仿真输出文件"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use('Agg')  # 非 GUI 后端，支持无头服务器
import matplotlib.pyplot as plt
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
import numpy as np

# SimulationResult 已迁移到 CAE 抽象层，此处重导出以保持向后兼容
from myagent.cae.base import SimulationResult, AbstractResultReader


class ResultReader(AbstractResultReader):
    """NNW-HyFLOW 仿真结果读取器

    读取 CFD 仿真完成后生成的结果文件，包括：
    - aircoef.dat — 气动力系数（升力/阻力/力矩）
    - res.dat — 收敛残差历史
    - tecflow.plt — 流场可视化数据
    - 自动生成收敛曲线、气动力曲线图
    """

    @staticmethod
    def read(job_dir: str) -> SimulationResult:
        """读取 CFD 仿真结果

        Args:
            job_dir: 仿真作业输出目录

        Returns:
            SimulationResult 对象
        """
        result = SimulationResult(job_dir)
        job_path = Path(job_dir)

        if not job_path.exists():
            result.error = f"作业目录不存在: {job_dir}"
            return result

        results_dir = job_path / "results"
        if not results_dir.exists():
            result.error = f"结果目录不存在: {results_dir}"
            return result

        # 1. 检查求解器是否运行过
        output_files = list(results_dir.glob("*"))
        if not output_files:
            result.error = "求解器未生成任何输出文件"
            return result

        # 2. 读取气动力系数
        aircoef_path = results_dir / "aircoef.dat"
        aircoef_data = None
        if aircoef_path.exists():
            aircoef_data = ResultReader._parse_aircoef(aircoef_path)
            if aircoef_data:
                result.raw_data["aircoef"] = aircoef_data
                result.success = True

        # 3. 读取残差历史
        res_path = results_dir / "res.dat"
        if res_path.exists():
            res_data = ResultReader._parse_residual(res_path)
            if res_data:
                result.raw_data["residual"] = res_data
                if not result.success:
                    result.success = True  # 有输出就算成功运行过

        # 4. 检查 tecflow.plt
        tecflow_path = results_dir / "tecflow.plt"
        has_tecflow = tecflow_path.exists()

        # 5. 提取摘要
        summary = ResultReader._build_summary(aircoef_data, res_path, has_tecflow)

        # 5.5 从 .hypara 文件提取工况参数（供报告使用）
        op_conditions = ResultReader._parse_operating_conditions(job_path)
        if op_conditions:
            summary["operating_conditions"] = op_conditions

        result.results_json = {"summary": summary}

        # 6. 生成可视化图片
        images = ResultReader._generate_plots(job_path, aircoef_data, res_path)
        result.images = images
        # 同时写入 results_json，供 ReportGenerator 读取
        result.results_json["images"] = images

        # 7. 保存 results.json
        ResultReader._save_results_json(job_path, result.results_json)

        # 7.5 生成 CFD 文本摘要（存入 _text_summary 供 get_text_summary 使用）
        result._text_summary = ResultReader.generate_text_summary(result)

        # 8. 错误情况
        if not result.success:
            error_details = []
            execution_log = job_path / "execution.log"
            if execution_log.exists():
                try:
                    log_text = execution_log.read_text(encoding="utf-8")
                    error_lines = [l for l in log_text.split("\n") if "error" in l.lower()]
                    if error_lines:
                        error_details.append("; ".join(error_lines[-3:]))
                except Exception:
                    pass
            if error_details:
                result.error = "; ".join(error_details)
            else:
                result.error = "仿真执行失败，未生成有效的气动力系数数据"

        return result

    # ——— 解析函数 ———

    @staticmethod
    def _parse_aircoef(filepath: Path) -> Optional[Dict]:
        """解析 aircoef.dat — NNW 气动力系数输出文件

        NNW 的 aircoef.dat 通常是多列格式，包含：
        iter, CL, CD, CZ, Cml, Cmn, Cm, CL_p, CD_p, ...

        Args:
            filepath: aircoef.dat 文件路径

        Returns:
            解析后的字典: {iterations: [], CL: [], CD: [], ...}
        """
        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
            lines = text.strip().split("\n")

            # 跳过注释/头部行，同时尝试从 VARIABLES 块提取列名
            data_lines = []
            header_found = False
            header_col_names: Optional[List[str]] = None
            in_variables = False  # 是否在 VARIABLES 块内收集列名
            var_lines: List[str] = []  # VARIABLES 后的列名行
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # 跳过纯注释行
                if line.startswith(("#", "!", "//", "TITLE")):
                    header_found = True
                    continue
                # 尝试从 VARIABLES 行提取列名
                if line.upper().startswith("VARIABLES"):
                    header_found = True
                    in_variables = True
                    var_lines = []
                    # 也检查 VARIABLES 行本身是否有列名
                    initial = ResultReader._parse_variables_line(line)
                    if initial:
                        header_col_names = initial
                        in_variables = False
                    continue
                # 在 VARIABLES 块内收集列名行
                if in_variables:
                    # 当遇到纯数字行时退出 VARIABLES 块
                    if re.match(r'^[\d\s.eE+\-]+$', line):
                        in_variables = False
                        data_lines.append(line)
                    else:
                        var_lines.append(line)
                    continue
                # 跳过只有文字的行（不含 HTML 标签的纯字母行）
                if re.match(r'^[A-Za-z"]', line) and not re.match(r'^[A-Za-z"].*\d', line):
                    header_found = True
                    continue
                data_lines.append(line)

            # 处理 VARIABLES 块收集到的列名（支持 HTML 格式如 <i>C<sub>L</sub></i>）
            if var_lines and header_col_names is None:
                header_col_names = ResultReader._parse_html_column_names(var_lines)

            if not data_lines:
                return None

            # 解析数值
            iterations = []
            values = {}  # column_key -> list

            # 先扫描所有行确定列数，一次性确定列名
            all_nums_list = []
            for line in data_lines:
                parts = line.split()
                try:
                    nums = [float(p) for p in parts]
                    all_nums_list.append(nums)
                except ValueError:
                    continue

            if not all_nums_list:
                return None

            ncols = len(all_nums_list[0])
            if header_col_names and len(header_col_names) == ncols:
                col_names = header_col_names
            else:
                col_names = ResultReader._guess_aircoef_columns(ncols)

            for i, nums in enumerate(all_nums_list):
                iterations.append(i + 1)

                for j, val in enumerate(nums):
                    if j < len(col_names):
                        col_key = col_names[j]
                    else:
                        col_key = f"col_{j}"
                    if col_key not in values:
                        values[col_key] = []
                    values[col_key].append(val)

            if not iterations:
                return None

            return {
                "iterations": iterations,
                "values": values,
                "nrows": len(iterations),
                "ncols": len(values),
            }
        except Exception as e:
            print(f"[NNW Result] 解析 aircoef.dat 失败: {e}")
            return None

    @staticmethod
    def _guess_aircoef_columns(ncols: int) -> List[str]:
        """根据列数推测 aircoef.dat 的列名

        NNW 的常见列顺序（从 DEMO 的 postParaCaption 推断）。
        对于简单格式（如 iter CL CD），首列直接为 iter。

        Args:
            ncols: 列数

        Returns:
            列名列表
        """
        # NNW 的完整列顺序（2 种格式）
        # 格式 A: 14 列 — 标准格式
        standard_cols_a = [
            "iter",       # 0 - 迭代步
            "CL",         # 1 - 升力系数
            "CD",         # 2 - 阻力系数
            "CZ",         # 3 - 侧向力系数
            "CD_p",       # 4 - 压差阻力
            "CD_f",       # 5 - 摩擦阻力
            "L_D",        # 6 - 升阻比
            "CA",         # 7 - 轴向力系数
            "CN",         # 8 - 法向力系数
            "CZ1",        # 9 - 横向力系数
            "Cml",        # 10 - 滚转力矩
            "Cmn",        # 11 - 偏航力矩
            "Cm",         # 12 - 俯仰力矩
            "Xcp",        # 13 - 压心X
        ]
        # 格式 B: 15 列 — 含涡阻修正项 CD-CL²/(π4Ar)
        standard_cols_b = [
            "iter",       # 0 - 迭代步
            "CL",         # 1 - 升力系数
            "CD",         # 2 - 阻力系数
            "CZ",         # 3 - 侧向力系数
            "CD_p",       # 4 - 压差阻力
            "CD_f",       # 5 - 摩擦阻力
            "CD_CL2_K",   # 6 - 涡阻修正项 CD-CL²/(π4Ar)
            "Xcp",        # 7 - 压心X
            "CA",         # 8 - 轴向力系数
            "CN",         # 9 - 法向力系数
            "CZ1",        # 10 - 横向力系数
            "Cml",        # 11 - 滚转力矩
            "Cmn",        # 12 - 偏航力矩
            "Cm",         # 13 - 俯仰力矩
            "Walltime",   # 14 - 壁钟时间
        ]

        if ncols == 15:
            return standard_cols_b
        if ncols <= len(standard_cols_a):
            return standard_cols_a[:ncols]
        return standard_cols_a + [f"col_{i}" for i in range(len(standard_cols_a), ncols)]

    @staticmethod
    def _parse_html_column_names(var_lines: List[str]) -> Optional[List[str]]:
        """从 VARIABLES 块的多行列名中提取列名（支持 HTML 格式）

        NNW 的 aircoef.dat VARIABLES 块格式示例:
          Variables=
          iter
          <i>C<sub>L</sub></i>
          <i>C<sub>D</sub></i>
          ...
          "Walltime"

        每行一个列名，可能是纯文本、HTML 标签包装、或引号包装。

        Args:
            var_lines: VARIABLES 后的列名行列表（不包含数据行）

        Returns:
            列名列表，解析失败返回 None
        """
        if not var_lines:
            return None

        names = []
        for line in var_lines:
            line = line.strip()
            if not line:
                continue
            # 先移除引号
            name = line.strip('"')
            # 移除 HTML 标签: <i>C<sub>L</sub></i> → CL
            name = re.sub(r'<[^>]+>', '', name)
            # 移除多余的空白
            name = name.strip()
            if name:
                # 规范化常见名称
                if name.upper() == 'WALLTIME':
                    name = 'Walltime'
                names.append(name)

        return names if names else None

    @staticmethod
    def _parse_variables_line(line: str) -> Optional[List[str]]:
        """从 VARIABLES 行解析列名

        格式: VARIABLES = "name1" "name2" ...
        或: VARIABLES = name1 name2 ...

        Args:
            line: VARIABLES 行文本

        Returns:
            列名列表，解析失败返回 None
        """
        # 移除 "VARIABLES =" 前缀
        line = re.sub(r'(?i)variables\s*=\s*', '', line).strip()

        # 提取引号内的名称
        quoted = re.findall(r'"([^"]+)"', line)
        if quoted:
            # 去重并保持顺序
            seen = set()
            result = []
            for name in quoted:
                if name not in seen:
                    seen.add(name)
                    result.append(name)
            if result:
                return result

        # 如果引号内提取失败，用空格分隔
        parts = line.strip('"').split()
        if parts:
            return [p.strip('"') for p in parts if p.strip('"')]

        return None

    @staticmethod
    def _parse_residual(filepath: Path) -> Optional[Dict]:
        """解析 res.dat — 残差收敛历史

        NNW 的 res.dat 通常是多列: iter, averageRes, rhoRes, ...

        Args:
            filepath: res.dat 文件路径

        Returns:
            解析后的字典: {iterations: [], averageRes: [], ...}
        """
        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
            lines = text.strip().split("\n")

            data_lines = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith(("#", "!", "//", "TITLE", "VARIABLES")):
                    continue
                data_lines.append(line)

            if not data_lines:
                return None

            iterations = []
            residuals = []

            for i, line in enumerate(data_lines):
                parts = line.split()
                if len(parts) < 2:
                    continue
                try:
                    nums = [float(p) for p in parts]
                except ValueError:
                    continue

                iterations.append(i + 1)
                # 第一列可能是迭代步，第二列是平均残差
                if len(nums) >= 2:
                    residuals.append(nums[1] if nums[1] > 0 else nums[0])
                else:
                    residuals.append(nums[0])

            if not iterations:
                return None

            # 过滤掉太大的初始残差（>1e10）和太小的（0或接近机器零）
            valid_res = [r for r in residuals if 1e-20 < r < 1e15]
            converged = False
            if valid_res and len(valid_res) > 10:
                # 最后 10% 的残差变化 < 1% 认为收敛
                tail = valid_res[-max(10, len(valid_res)//10):]
                converged = max(tail) / max(min(tail), 1e-30) < 10

            return {
                "iterations": iterations,
                "residual": residuals,
                "converged": converged,
                "final_residual": residuals[-1] if residuals else None,
            }
        except Exception as e:
            print(f"[NNW Result] 解析 res.dat 失败: {e}")
            return None

    # ——— 摘要构建 ———

    @staticmethod
    def _build_summary(
        aircoef_data: Optional[Dict],
        res_path: Optional[Path],
        has_tecflow: bool,
    ) -> Dict[str, Any]:
        """构建结果摘要

        Args:
            aircoef_data: 气动力系数数据
            res_path: 残差文件路径（用于标记收敛状态）
            has_tecflow: 是否有流场可视化数据

        Returns:
            摘要字典
        """
        summary: Dict[str, Any] = {}

        if aircoef_data:
            values = aircoef_data["values"]

            # 提取最终稳定值（取最后 10% 迭代的平均值，排除初始波动）
            for key in ["CL", "CD", "CZ", "Cm", "L_D"]:
                if key in values:
                    arr = values[key]
                    tail_n = max(1, len(arr) // 10)
                    tail = arr[-tail_n:]
                    summary[key.lower()] = round(float(np.mean(tail)), 6)
                    # 也保存最终值
                    summary[f"{key.lower()}_final"] = round(arr[-1], 6)

            # 升阻比 — 始终从 CL/CD 直接计算（不依赖列名）
            if "CL" in values and "CD" in values:
                cl_arr = values["CL"][-max(1, len(values["CL"])//10):]
                cd_arr = values["CD"][-max(1, len(values["CD"])//10):]
                ld = np.mean(cl_arr) / max(np.mean(cd_arr), 1e-10)
                summary["l_d"] = round(float(ld), 4)

            # 力和力矩系数
            for key in ["ca", "cn", "cml", "cmn"]:
                key_upper = key.upper()
                if key_upper in values:
                    arr = values[key_upper]
                    tail = arr[-max(1, len(arr)//10):]
                    summary[key] = round(float(np.mean(tail)), 6)

            summary["n_iterations"] = aircoef_data["nrows"]

        # 收敛状态
        res_data = None
        if res_path and res_path.exists():
            res_data = ResultReader._parse_residual(res_path)

        if res_data:
            summary["converged"] = res_data.get("converged", False)
            summary["final_residual"] = res_data.get("final_residual")
            summary["n_residual_steps"] = len(res_data.get("iterations", []))
        else:
            summary["converged"] = aircoef_data is not None

        # tecflow 标记
        summary["has_tecflow"] = has_tecflow

        return summary

    # ——— 工况参数提取 ———

    @staticmethod
    def _parse_operating_conditions(job_path: Path) -> Dict[str, Any]:
        """从 .hypara 文件提取工况参数，供报告生成器显示

        解析 bin/cfd_para.hypara（主要参数）、bin/key.hypara（维度）、
        bin/grid_para.hypara（网格类型），提取报告所需的工况参数。

        Args:
            job_path: 仿真作业目录

        Returns:
            工况参数字典，键名与 report.py 的 _build_operating_conditions 对齐
        """
        op: Dict[str, Any] = {}

        # —— 解析单个 .hypara 文件，返回 {参数名: 值} 字典 ——
        def parse_hypara(filepath: Path) -> Dict[str, str]:
            result = {}
            if not filepath.exists():
                return result
            try:
                text = filepath.read_text(encoding="utf-8", errors="replace")
                # 匹配格式: type name = value;  或  type name[] = [...];
                # 支持 string / double / int 类型
                for match in re.finditer(
                    r'(?:string|double|int)\s+(\w+(?:\[\])?)\s*=\s*(.+?);',
                    text
                ):
                    name = match.group(1).rstrip('[]')  # 去掉数组标记
                    value = match.group(2).strip().strip('"')
                    result[name] = value
            except Exception as e:
                print(f"[NNW Result] 解析 .hypara 文件失败 {filepath}: {e}")
            return result

        # 1. 解析 cfd_para.hypara（主要 CFD 参数）
        cfd_path = job_path / "bin" / "cfd_para.hypara"
        cfd = parse_hypara(cfd_path)

        # 2. 解析 key.hypara（维度等）
        key_path = job_path / "bin" / "key.hypara"
        key = parse_hypara(key_path)

        # 3. 解析 grid_para.hypara（网格类型）
        grid_path = job_path / "bin" / "grid_para.hypara"
        grid = parse_hypara(grid_path)

        # ——— 参数映射 ———
        # 马赫数
        if "refMachNumber" in cfd:
            try:
                op["mach_number"] = float(cfd["refMachNumber"])
            except ValueError:
                op["mach_number"] = cfd["refMachNumber"]

        # 攻角
        if "attackd" in cfd:
            try:
                op["attack_angle_deg"] = float(cfd["attackd"])
            except ValueError:
                op["attack_angle_deg"] = cfd["attackd"]

        # 侧滑角
        if "angleSlide" in cfd:
            try:
                op["sideslip_angle_deg"] = float(cfd["angleSlide"])
            except ValueError:
                op["sideslip_angle_deg"] = cfd["angleSlide"]

        # 雷诺数
        if "refReNumber" in cfd:
            try:
                op["reynolds_number"] = float(cfd["refReNumber"])
            except ValueError:
                op["reynolds_number"] = cfd["refReNumber"]

        # 来流温度
        if "refDimensionalTemperature" in cfd:
            try:
                op["temperature_k"] = float(cfd["refDimensionalTemperature"])
            except ValueError:
                op["temperature_k"] = cfd["refDimensionalTemperature"]

        # 壁面温度（-1 表示绝热壁）
        if "wallTemperature" in cfd:
            try:
                wt = float(cfd["wallTemperature"])
                op["wall_temperature"] = "绝热壁 (Twall=-1)" if wt < 0 else f"{wt} K"
            except ValueError:
                op["wall_temperature"] = cfd["wallTemperature"]

        # 湍流模型 — 映射简称
        if "viscousName" in cfd:
            turb_map = {
                "1eq-sa": "SA 一方程 (Spalart-Allmaras)",
                "sst": "SST k-ω 二方程",
                "kw-sst": "SST k-ω 二方程",
                "laminar": "层流 (Laminar)",
                "euler": "无粘 (Euler)",
            }
            raw = cfd["viscousName"].strip('"')
            op["turbulence_model"] = turb_map.get(raw, raw)

        # 比热比
        if "refGama" in cfd:
            try:
                op["gamma"] = float(cfd["refGama"])
            except ValueError:
                op["gamma"] = cfd["refGama"]

        # 无粘通量格式
        if "inviscidSchemeName" in cfd:
            flux_map = {"roe": "Roe 格式", "vanleer": "Van Leer 格式",
                       "steger": "Steger-Warming 格式", "ausmpwplus": "AUSM+ 格式"}
            raw = cfd["inviscidSchemeName"].strip('"')
            op["inviscid_flux"] = flux_map.get(raw, raw)

        # 限制器
        if "str_limiter_name" in cfd:
            lim_map = {"smooth": "smooth", "minmod": "minmod", "vencat": "Venkatakrishnan"}
            raw = cfd["str_limiter_name"].strip('"')
            op["limiter"] = lim_map.get(raw, raw)

        # 梯度方法
        if "gradientName" in cfd:
            grad_map = {"ggnode": "Green-Gauss (ggnode)", "ggcell": "Green-Gauss (ggcell)"}
            raw = cfd["gradientName"].strip('"')
            op["gradient_method"] = grad_map.get(raw, raw)

        # 时间推进
        if "tscheme" in cfd:
            t_map = {"4": "LU-SGS 隐式", "1": "Runge-Kutta 显式"}
            op["time_integration"] = t_map.get(cfd["tscheme"], f"tscheme={cfd['tscheme']}")

        # CFL 信息
        cfl_start = cfd.get("CFLStart", "")
        cfl_end = cfd.get("CFLEnd", "")
        if cfl_start and cfl_end:
            try:
                cs = float(cfl_start)
                ce = float(cfl_end)
                op["cfl_info"] = f"{cs:.4g} → {ce:.4g}"
            except ValueError:
                op["cfl_info"] = f"{cfl_start} → {cfl_end}"

        # 网格信息
        gridfile = cfd.get("gridfile", "").strip('"')
        gridtype = grid.get("gridtype", "")
        ndim = key.get("ndim", "")
        grid_parts = []
        if gridfile:
            # 提取文件名
            grid_name = Path(gridfile).stem
            grid_parts.append(grid_name)
        # 网格类型
        gt_map = {"1": "结构网格", "2": "非结构网格", "3": "混合网格"}
        if gridtype in gt_map:
            grid_parts.append(gt_map[gridtype])
        # 维度
        dim_map = {"2": "2D", "3": "3D"}
        if ndim in dim_map:
            grid_parts.append(dim_map[ndim])
        # 格式
        if gridfile:
            ext = Path(gridfile).suffix.upper().lstrip('.')
            if ext:
                grid_parts.append(f"({ext})")
        if grid_parts:
            op["grid_info"] = " ".join(grid_parts)

        return op

    # ——— tecflow 流场数据解析 ———

    @staticmethod
    def _parse_tecflow_block(job_path: Path) -> Dict[str, np.ndarray]:
        """解析 tecflow.plt（Tecplot BLOCK 格式），提取结构化网格上的流场变量

        PHengLEI 输出的 tecflow.plt 头部格式:
          title="Flow Fields of PHengLEI"
          variables="x", "y", "z", "density", "u", "v", "w", "pressure", "temperature", "mach"
          zone T = "Zone0 Symmetry"
          I = 25, J = 49, K = 1
          f = BLOCK
          <每个变量 I×J×K 个浮点数的连续块>

        Args:
            job_path: 仿真作业目录

        Returns:
            {变量名: 2D numpy数组 (J, I)} 字典，解析失败返回空字典
        """
        # 查找 tecflow 文件：优先 tecflow0.plt，回退 tecflow.plt
        results_dir = job_path / "results"
        tecflow_path = results_dir / "tecflow0.plt"
        if not tecflow_path.exists():
            tecflow_path = results_dir / "tecflow.plt"
        if not tecflow_path.exists():
            return {}

        try:
            text = tecflow_path.read_text(encoding="utf-8", errors="replace")
            lines = text.split("\n")
        except Exception as e:
            print(f"[NNW Result] 读取 tecflow 文件失败: {e}")
            return {}

        # —— 解析头部 ——
        var_names: List[str] = []
        grid_dims: Dict[str, int] = {}
        data_start_line = -1

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # 提取变量名
            m = re.match(r'variables\s*=\s*(.+)', line_stripped, re.IGNORECASE)
            if m:
                # 格式: "x", "y", "z", ...
                var_str = m.group(1)
                var_names = [v.strip().strip('"') for v in var_str.split(",")]
                continue

            # 提取网格维度 I / J / K
            m2 = re.match(r'\s*([IJK])\s*=\s*(\d+)', line_stripped)
            if m2:
                grid_dims[m2.group(1)] = int(m2.group(2))
                continue

            # 定位 BLOCK 数据起始
            if 'f = BLOCK' in line_stripped or 'f=BLOCK' in line_stripped:
                data_start_line = i + 1
                break

        if not var_names or not grid_dims or data_start_line < 0:
            print("[NNW Result] tecflow 头部信息不完整，跳过云图生成")
            return {}

        I = grid_dims.get("I", 1)
        J = grid_dims.get("J", 1)
        K = grid_dims.get("K", 1)
        n_per_var = I * J * K
        n_vars = len(var_names)
        total_expected = n_vars * n_per_var

        # —— 解析数据块 ——
        all_values: List[float] = []
        for line in lines[data_start_line:]:
            stripped = line.strip()
            if not stripped:
                continue
            # 跳过可能的注释或 zone 分隔（可能还有其他 zone）
            if stripped.startswith(("ZONE", "zone", "TITLE", "title",
                                     "VARIABLES", "variables")):
                break
            try:
                parts = stripped.split()
                for p in parts:
                    all_values.append(float(p))
            except ValueError:
                continue

        if len(all_values) < total_expected:
            print(f"[NNW Result] tecflow 数据不足: 期望 {total_expected}, 实际 {len(all_values)}")
            # 尽可能用已有数据
            actual_n = min(len(all_values), total_expected)
        else:
            actual_n = total_expected

        # —— 按变量分组并 reshape ——
        result: Dict[str, np.ndarray] = {}
        for vi, vname in enumerate(var_names):
            start = vi * n_per_var
            end = min(start + n_per_var, actual_n)
            if end <= start:
                break
            # 取第一个 K 层（对称面 K=0）
            layer_size = I * J
            layer_start = start
            layer_end = min(start + layer_size, end)
            vals = np.array(all_values[layer_start:layer_end], dtype=np.float64)
            if len(vals) == layer_size:
                result[vname] = vals.reshape(J, I)
            elif len(vals) > 0:
                # 数据量不对，尽力而为
                flat_size = min(len(vals), I * J)
                padded = np.zeros(I * J, dtype=np.float64)
                padded[:flat_size] = vals[:flat_size]
                result[vname] = padded.reshape(J, I)

        if "x" in result and "y" in result:
            print(f"[NNW Result] 已解析 tecflow: {len(var_names)} 个变量, "
                  f"网格 {I}×{J}×{K}, shape={result['x'].shape}")

        return result

    @staticmethod
    def _generate_contour_plots(
        job_path: Path,
        tecflow_data: Dict[str, np.ndarray],
    ) -> List[str]:
        """从 tecflow 流场数据生成填充云图 PNG

        生成 5 张云图：马赫数、压力、密度、温度、速度大小。

        Args:
            job_path: 作业目录
            tecflow_data: _parse_tecflow_block 的返回值

        Returns:
            新生成的图片文件名列表
        """
        images = []

        # 确保有坐标数据
        if "x" not in tecflow_data or "y" not in tecflow_data:
            return images

        x = tecflow_data["x"]
        y = tecflow_data["y"]
        x_flat = x.flatten()
        y_flat = y.flatten()

        # 定义要绘制的变量: (变量名, 文件名, 标签, 色条标签, 色图)
        plot_specs = [
            ("mach", "contour_mach.png", "马赫数分布 (对称面)", "Ma", "jet"),
            ("pressure", "contour_pressure.png", "压力分布 (对称面)", "Pressure (Pa)", "jet"),
            ("density", "contour_density.png", "密度分布 (对称面)", "Density (kg/m^3)", "jet"),
            ("temperature", "contour_temperature.png", "温度分布 (对称面)", "Temperature (K)", "hot"),
        ]

        for var_name, filename, title, cbar_label, cmap in plot_specs:
            if var_name not in tecflow_data:
                continue
            try:
                scalar = tecflow_data[var_name].flatten()

                fig, ax = plt.subplots(figsize=(10, 6))
                tcf = ax.tricontourf(x_flat, y_flat, scalar, levels=25, cmap=cmap)
                cbar = fig.colorbar(tcf, ax=ax, label=cbar_label)
                ax.set_title(title, fontsize=14, fontweight="bold")
                ax.set_xlabel("x")
                ax.set_ylabel("y")
                ax.set_aspect("equal")
                ax.grid(True, alpha=0.2, linestyle="--")

                img_path = job_path / filename
                fig.savefig(img_path, dpi=150, bbox_inches="tight")
                plt.close(fig)
                images.append(filename)
                print(f"[NNW Result] 已保存流场云图: {img_path}")
            except Exception as e:
                print(f"[NNW Result] 生成 {title} 失败: {e}")

        # 5. 速度大小 (由 u, v, w 合成)
        if "u" in tecflow_data and "v" in tecflow_data:
            try:
                u = tecflow_data["u"].flatten()
                v = tecflow_data["v"].flatten()
                w = tecflow_data.get("w", None)
                if w is not None:
                    w = w.flatten()
                    vel = np.sqrt(u**2 + v**2 + w**2)
                else:
                    vel = np.sqrt(u**2 + v**2)

                fig, ax = plt.subplots(figsize=(10, 6))
                tcf = ax.tricontourf(x_flat, y_flat, vel, levels=25, cmap="jet")
                cbar = fig.colorbar(tcf, ax=ax, label="Velocity (m/s)")
                ax.set_title("速度大小分布 (对称面)", fontsize=14, fontweight="bold")
                ax.set_xlabel("x")
                ax.set_ylabel("y")
                ax.set_aspect("equal")
                ax.grid(True, alpha=0.2, linestyle="--")

                img_path = job_path / "contour_velocity.png"
                fig.savefig(img_path, dpi=150, bbox_inches="tight")
                plt.close(fig)
                images.append("contour_velocity.png")
                print(f"[NNW Result] 已保存速度云图: {img_path}")
            except Exception as e:
                print(f"[NNW Result] 生成速度云图失败: {e}")

        return images

    # ——— 图片生成 ———

    @staticmethod
    def _generate_plots(
        job_path: Path,
        aircoef_data: Optional[Dict],
        res_path: Optional[Path],
    ) -> List[str]:
        """生成可视化图片

        Args:
            job_path: 作业目录
            aircoef_data: 气动力系数数据
            res_path: 残差文件路径

        Returns:
            生成的图片文件名列表
        """
        images = []

        # 1. 气动力系数曲线
        if aircoef_data:
            try:
                img = ResultReader._plot_aero_coefficients(job_path, aircoef_data)
                if img:
                    images.append(img)
            except Exception as e:
                print(f"[NNW Result] 气动力曲线生成失败: {e}")

        # 2. 收敛残差曲线
        if res_path and res_path.exists():
            try:
                res_data = ResultReader._parse_residual(res_path)
                if res_data:
                    img = ResultReader._plot_residual(job_path, res_data)
                    if img:
                        images.append(img)
            except Exception as e:
                print(f"[NNW Result] 残差曲线生成失败: {e}")

        # 3. 流场云图（从 tecflow.plt 生成）
        try:
            tecflow_data = ResultReader._parse_tecflow_block(job_path)
            if tecflow_data:
                contour_imgs = ResultReader._generate_contour_plots(job_path, tecflow_data)
                images.extend(contour_imgs)
        except Exception as e:
            print(f"[NNW Result] 流场云图生成失败: {e}")

        # 4. 扫描结果目录中已有的图片
        for ext in [".png", ".jpg", ".jpeg", ".bmp"]:
            for img_file in job_path.glob(f"*{ext}"):
                if img_file.name not in images:
                    images.append(img_file.name)
            for img_file in job_path.glob(f"*{ext.upper()}"):
                if img_file.name not in images:
                    images.append(img_file.name)
        # 也扫描 results/ 子目录
        results_dir = job_path / "results"
        if results_dir.exists():
            for ext in [".png", ".jpg"]:
                for img_file in results_dir.glob(f"*{ext}"):
                    images.append(f"results/{img_file.name}")

        return images

    @staticmethod
    def _plot_aero_coefficients(job_path: Path, data: Dict) -> Optional[str]:
        """绘制气动力系数收敛曲线

        Args:
            job_path: 作业目录
            data: 气动力系数数据

        Returns:
            图片文件名或 None
        """
        values = data["values"]
        iterations = data["iterations"]

        # 确定要绘制的系数
        plot_keys = []
        for key in ["CL", "CD", "CZ", "Cm"]:
            if key in values and len(values[key]) > 1:
                plot_keys.append(key)

        if not plot_keys:
            return None

        fig, axes = plt.subplots(len(plot_keys), 1, figsize=(10, 3 * len(plot_keys)))
        if len(plot_keys) == 1:
            axes = [axes]

        for ax, key in zip(axes, plot_keys):
            arr = values[key]
            x = iterations[-len(arr):] if len(arr) <= len(iterations) else range(len(arr))
            ax.plot(x, arr, linewidth=1.2, color='#2196F3')
            ax.set_ylabel(key)
            ax.set_xlabel("迭代步")
            ax.grid(True, alpha=0.3)
            ax.set_title(f"{key} 收敛曲线")

        plt.tight_layout()
        img_path = job_path / "aerodynamic_coefficients.png"
        fig.savefig(img_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"[NNW Result] 已保存气动力系数图: {img_path}")
        return "aerodynamic_coefficients.png"

    @staticmethod
    def _plot_residual(job_path: Path, data: Dict) -> Optional[str]:
        """绘制残差收敛曲线

        Args:
            job_path: 作业目录
            data: 残差数据

        Returns:
            图片文件名或 None
        """
        residuals = data["residual"]
        iterations = data["iterations"]

        if len(residuals) < 2:
            return None

        fig, ax = plt.subplots(figsize=(10, 5))

        # 半对数坐标
        ax.semilogy(iterations, residuals, linewidth=1.2, color='#E91E63')
        ax.set_xlabel("迭代步")
        ax.set_ylabel("残差")
        ax.set_title("残差收敛历史")
        ax.grid(True, alpha=0.3)

        # 收敛状态
        if data.get("converged"):
            ax.text(0.98, 0.95, "Converged [OK]", transform=ax.transAxes,
                    ha='right', va='top', fontsize=12, color='green',
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        else:
            ax.text(0.98, 0.95, "Not converged [?]", transform=ax.transAxes,
                    ha='right', va='top', fontsize=12, color='orange',
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

        plt.tight_layout()
        img_path = job_path / "residual_convergence.png"
        fig.savefig(img_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"[NNW Result] 已保存残差曲线图: {img_path}")
        return "residual_convergence.png"

    # ——— 工具函数 ———

    @staticmethod
    def _save_results_json(job_path: Path, results_json: Dict):
        """保存 results.json 到作业目录

        Args:
            job_path: 作业目录
            results_json: 结果数据
        """
        json_path = job_path / "results.json"
        try:
            # 序列化时处理 numpy 类型
            def convert_numpy(obj):
                if isinstance(obj, (np.integer,)):
                    return int(obj)
                elif isinstance(obj, (np.floating,)):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                return obj

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(results_json, f, ensure_ascii=False, indent=2, default=convert_numpy)
            print(f"[NNW Result] 已保存: results.json")
        except Exception as e:
            print(f"[NNW Result] 写入 results.json 失败: {e}")

    # ——— 覆写文本摘要 ———

    def get_text_summary(self) -> str:
        """生成 CFD 结果的文本摘要

        覆写基类的默认实现，提供 NNW CFD 特有的摘要格式。

        Returns:
            文本摘要字符串
        """
        return ResultReader.generate_text_summary(self)


    @staticmethod
    def generate_text_summary(result: SimulationResult) -> str:
        """静态方法 — 为给定的 SimulationResult 生成 CFD 文本摘要

        Args:
            result: SimulationResult 对象

        Returns:
            文本摘要字符串
        """
        if not result.success:
            return f"CFD 仿真失败: {result.error}"

        summary = result.results_json.get("summary", {})
        lines = []

        # 气动力系数
        aero_items = [
            ("cl", "升力系数 CL"),
            ("cd", "阻力系数 CD"),
            ("l_d", "升阻比 L/D"),
            ("cz", "侧向力系数 CZ"),
            ("cm", "俯仰力矩系数 Cm"),
            ("ca", "轴向力系数 CA"),
            ("cn", "法向力系数 CN"),
            ("cml", "滚转力矩系数 Cml"),
            ("cmn", "偏航力矩系数 Cmn"),
        ]

        has_aero = False
        for key, label in aero_items:
            if key in summary:
                if not has_aero:
                    lines.append("  [气动力系数]")
                    has_aero = True
                val = summary[key]
                lines.append(f"    {label} = {val:.6f}")

        # 收敛信息
        if "converged" in summary:
            status = "已收敛" if summary["converged"] else "可能未收敛"
            lines.append(f"  [收敛状态] {status}")

        if "final_residual" in summary and summary["final_residual"] is not None:
            lines.append(f"    最终残差: {summary['final_residual']:.2e}")

        if "n_iterations" in summary:
            lines.append(f"    迭代步数: {summary['n_iterations']}")

        if "has_tecflow" in summary and summary["has_tecflow"]:
            lines.append("  [流场数据] tecflow.plt 已生成")

        if not lines:
            lines.append("  (结果数据暂无)")

        lines.append(f"\n  [img] 结果图片: {len(result.images)} 张")
        for img in result.images:
            lines.append(f"     - {img}")

        return "\n".join(lines)
