"""NNW-HyFLOW 执行器 — 调用 PHengLEI 求解器运行 CFD 仿真"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple

from myagent.cae.base import AbstractExecutor


# ——— 工具函数 ———

def _copy_grid_directory(src_dir: Path, dest_dir: Path):
    """拷贝网格源目录的所有文件到目标目录

    NNW 网格目录包含多个辅助文件（.bcmesh, .bcdir, .fts, .grd, .link, .inp 等），
    网格转换和分区间都需要这些文件，因此需要拷贝整个目录。

    Args:
        src_dir: 源网格目录
        dest_dir: 目标目录
    """
    if not src_dir.exists() or not src_dir.is_dir():
        print(f"[NNW Executor] 网格源目录不存在或不是目录: {src_dir}")
        return

    copied = 0
    for item in src_dir.iterdir():
        if item.is_file():
            dest = dest_dir / item.name
            if not dest.exists():
                shutil.copy2(item, dest)
                copied += 1

    print(f"[NNW Executor] 已拷贝网格目录 {copied} 个文件: {src_dir} -> {dest_dir}")


class NNWExecutor(AbstractExecutor):
    """NNW-HyFLOW 求解器执行器

    负责调用 PHengLEIv3d0.exe 运行 CFD 仿真，
    管理作业目录结构、网格文件、超时等。
    """

    def __init__(
        self,
        solver_path: str,
        install_path: str = "",
        work_dir: str = "output",
        timeout: int = 7200,
        ncpus: int = 4,
    ):
        """初始化执行器

        Args:
            solver_path: PHengLEIv3d0.exe 的路径
            install_path: NNW 安装根目录
            work_dir: 输出目录基础路径
            timeout: 执行超时时间（秒），CFD 默认 2 小时
            ncpus: MPI 并行核心数
        """
        self.solver_path = solver_path
        self.install_path = Path(install_path) if install_path else None
        self.work_dir = Path(work_dir)
        self.timeout = timeout
        self.ncpus = ncpus
        self._ensure_work_dir()

    def _ensure_work_dir(self):
        """确保输出目录存在"""
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        script_path: str,
        job_name: Optional[str] = None,
        grid_path: Optional[str] = None,
        **kwargs
    ) -> Dict:
        """执行 NNW-HyFLOW CFD 仿真

        工作流程：
        1. 创建时间戳作业目录，设置 bin/ grid/ results/ 子目录
        2. 将生成的 .hypara 文件部署到 bin/ 目录
        3. 如果提供了网格文件，复制到 grid/ 目录
        4. 在作业根目录创建 key.hypara
        5. 调用 PHengLEIv3d0.exe

        Args:
            script_path: 脚本路径（generator 生成的 job_dir）
            job_name: 作业名称
            grid_path: 网格文件路径

        Returns:
            执行结果字典
        """
        # 脚本路径是 generator 返回的 job_dir
        script_path = Path(script_path)

        # 确定作业目录
        if job_name is None:
            job_name = "nnw_simulation"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_dir = self.work_dir / f"{job_name}_{timestamp}"
        job_dir.mkdir(parents=True, exist_ok=True)

        # 如果 script_path 已经有 bin/ 子目录（由 generator 创建），复制整个结构
        src_bin = script_path / "bin"
        if src_bin.exists():
            dest_bin = job_dir / "bin"
            shutil.copytree(src_bin, dest_bin)
            print(f"[NNW Executor] 已复制参数文件: {src_bin} -> {dest_bin}")
        else:
            # 兼容旧模式：script_path 是 .hypara 文件
            dest_bin = job_dir / "bin"
            dest_bin.mkdir(parents=True, exist_ok=True)
            for hypara_file in script_path.glob("*.hypara"):
                shutil.copy2(hypara_file, dest_bin)

        # ——— 创建 results/ 目录 ———
        results_dir = job_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)

        # ——— 处理网格文件 ———
        # NNW 网格目录包含多个辅助文件（.bcmesh, .bcdir, .fts, .grd 等），
        # 需要拷贝整个目录而非单个文件
        grid_dir = job_dir / "grid"
        grid_dir.mkdir(parents=True, exist_ok=True)

        resolved_grid_filename = None
        if grid_path:
            # 调用方显式传入了网格路径
            grid_src = Path(grid_path)
            if grid_src.is_dir():
                # 拷贝整个网格目录，扫描目录找实际的 .cgns/.fts 文件名
                _copy_grid_directory(grid_src, grid_dir)
                for ext in ['.cgns', '.fts', '.CGNS', '.FTS']:
                    candidates = list(grid_dir.glob(f'*{ext}'))
                    if candidates:
                        resolved_grid_filename = candidates[0].name
                        break
                if resolved_grid_filename is None:
                    print(f"[NNW Executor] 警告: 无法在网格目录中找到 .cgns/.fts 文件: {grid_src}")
            elif grid_src.exists():
                # 单个文件 —— 拷贝其所在目录的所有文件
                _copy_grid_directory(grid_src.parent, grid_dir)
                resolved_grid_filename = grid_src.name
            else:
                print(f"[NNW Executor] 警告: 网格路径不存在: {grid_path}")
        else:
            # 尝试从参数文件中读取网格路径
            grid_info = self._find_grid_in_params(job_dir)
            if grid_info:
                original_path, filename = grid_info
                grid_src = Path(original_path)
                if grid_src.exists():
                    # 拷贝网格文件所在目录的所有内容（含 .fts, .grd, .bcmesh 等辅助文件）
                    _copy_grid_directory(grid_src.parent, grid_dir)
                    resolved_grid_filename = filename
                    print(f"[NNW Executor] 已复制网格目录: {grid_src.parent} -> {grid_dir}")
                elif not original_path.startswith("./"):
                    # 绝对路径但文件不存在 —— 报错
                    print(f"[NNW Executor] 警告: 网格文件不存在: {original_path}")
                else:
                    # 相对路径（如 ./grid/mesh.fts）—— 可能是占位符，保留原样
                    resolved_grid_filename = filename
                    print(f"[NNW Executor] 网格使用相对路径: {original_path}")
            else:
                print("[NNW Executor] 警告: 未在参数文件中找到网格文件路径")

        # ——— 更新 .hypara 文件中的网格路径为相对路径 ———
        if resolved_grid_filename:
            self._update_grid_path(job_dir, resolved_grid_filename)

        # ——— 后处理: 修正 LLM 常见生成错误 ———
        self._fix_common_llm_mistakes(
            job_dir,
            grid_filename=resolved_grid_filename if resolved_grid_filename else None
        )

        # ——— 确保 key.hypara 在作业根目录 ———
        # key.hypara 应该在作业根目录，指向 bin/ 下的参数文件
        root_key = job_dir / "key.hypara"
        bin_key = dest_bin / "key.hypara"
        if bin_key.exists():
            shutil.copy2(bin_key, root_key)
        elif not root_key.exists():
            # 创建默认 key.hypara
            self._create_default_key(job_dir)

        # ——— 验证关键文件存在 ———
        if not (dest_bin / "cfd_para.hypara").exists():
            print("[NNW Executor] 警告: cfd_para.hypara 未找到，仿真可能失败")

        # ——— 执行求解器 ———
        # PHengLEIv3d0.exe 在当前工作目录运行，读取 ./key.hypara
        command = f'"{self.solver_path}"'

        print(f"\n[NNW Executor] 执行命令: {command}")
        print(f"[NNW Executor] 工作目录: {job_dir}")
        print(f"[NNW Executor] 超时: {self.timeout} 秒")
        print(f"[NNW Executor] CPU 核心: {self.ncpus}")

        start_time = datetime.now()

        try:
            # 设置环境变量
            env = os.environ.copy()
            if self.install_path:
                bin_install = self.install_path / "bin"
                env["PATH"] = str(bin_install) + os.pathsep + str(bin_install / "X64") + os.pathsep + env.get("PATH", "")
                # 如果存在 MPI，添加到 PATH
                if (bin_install / "X64" / "msmpi.dll").exists():
                    env["PATH"] = str(bin_install / "X64") + os.pathsep + env["PATH"]

            result = subprocess.run(
                command,
                shell=True,
                cwd=str(job_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
                errors="replace",
                env=env,
            )

            duration = (datetime.now() - start_time).total_seconds()
            stdout = result.stdout
            stderr = result.stderr
            return_code = result.returncode
            success = return_code == 0

            error = None
            if not success:
                error = self._extract_error(stdout, stderr, results_dir)

        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            success = False
            return_code = -1
            stdout = ""
            stderr = ""
            error = f"CFD 仿真执行超时（超过 {self.timeout} 秒）"

        except FileNotFoundError:
            duration = 0
            success = False
            return_code = -1
            stdout = ""
            stderr = ""
            error = f"找不到 NNW 求解器: {self.solver_path}"

        # 保存执行日志
        log_path = job_dir / "execution.log"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"命令: {command}\n")
            f.write(f"返回码: {return_code}\n")
            f.write(f"耗时: {duration:.1f} 秒\n\n")
            f.write("=== STDOUT ===\n")
            f.write(stdout + "\n")
            f.write("=== STDERR ===\n")
            f.write(stderr + "\n")

        return {
            "success": success,
            "job_dir": str(job_dir),
            "stdout": stdout,
            "stderr": stderr,
            "return_code": return_code,
            "duration": round(duration, 1),
            "error": error,
        }

    def _find_grid_in_params(self, job_dir: Path) -> Optional[Tuple[str, str]]:
        """从参数文件中查找网格文件原始路径

        优先搜索 grid_para.hypara 的 from_gfile（实际输入文件），
        再回退到 cfd_para.hypara 的 gridfile（求解器读取的文件）。
        仅返回存在的绝对路径，相对路径（如 ./grid/mesh.fts）跳过。

        Args:
            job_dir: 作业目录

        Returns:
            (原始完整路径, 文件名) 元组，或 None
        """
        bin_dir = job_dir / "bin"

        # 优先搜索 from_gfile（实际输入网格），再回退 gridfile
        search_specs = [
            ("grid_para.hypara", r'from_gfile\s*=\s*"(.+?)"'),
            ("cfd_para.hypara", r'gridfile\s*=\s*"(.+?)"'),
        ]

        for filename, pattern in search_specs:
            para_file = bin_dir / filename
            if not para_file.exists():
                continue

            try:
                content = para_file.read_text(encoding="utf-8")
                match = re.search(pattern, content)
                if match:
                    original_path = match.group(1).strip()
                    # 跳过相对路径占位符（如 ./grid/mesh.fts）
                    if original_path.startswith("./") or original_path.startswith("../"):
                        continue
                    fname = Path(original_path).name
                    if fname:
                        return (original_path, fname)
            except Exception:
                pass

        return None

    def _update_grid_path(self, job_dir: Path, grid_filename: str):
        """更新所有参数文件中的网格路径为统一的相对路径

        从 .cgns 文件名自动推导 .fts 文件名（换后缀），确保：
        - grid_para.hypara: from_gfile=.cgns, out_gfile=.fts
        - cfd_para.hypara: gridfile=.fts
        - partition.hypara: original/partition_grid_file=.fts

        Args:
            job_dir: 作业目录
            grid_filename: 网格文件名（如 m6_str.cgns）
        """
        bin_dir = job_dir / "bin"

        # 推导 .fts 文件名
        grid_stem = Path(grid_filename).stem   # "m6_str"
        grid_ext = Path(grid_filename).suffix.lower()  # ".cgns"
        fts_filename = f"{grid_stem}.fts" if grid_ext in ('.cgns',) else grid_filename

        new_input_grid = f"./grid/{grid_filename}"
        new_fts_grid = f"./grid/{fts_filename}"

        # 1. 更新 grid_para.hypara — from_gfile 和 out_gfile
        grid_para = bin_dir / "grid_para.hypara"
        if grid_para.exists():
            try:
                content = grid_para.read_text(encoding="utf-8")
                content = re.sub(r'(from_gfile\s*=\s*")(.+)(")', rf'\1{new_input_grid}\3', content)
                content = re.sub(r'(out_gfile\s*=\s*")(.+)(")', rf'\1{new_fts_grid}\3', content)
                grid_para.write_text(content, encoding="utf-8")
                print(f"[NNW Executor] 已更新 grid_para: from_gfile={new_input_grid}, out_gfile={new_fts_grid}")
            except Exception as e:
                print(f"[NNW Executor] 更新 grid_para 失败: {e}")

        # 2. 更新 cfd_para.hypara — gridfile
        cfd_para = bin_dir / "cfd_para.hypara"
        if cfd_para.exists():
            try:
                content = cfd_para.read_text(encoding="utf-8")
                content = re.sub(r'(gridfile\s*=\s*")(.+)(")', rf'\1{new_fts_grid}\3', content)
                cfd_para.write_text(content, encoding="utf-8")
                print(f"[NNW Executor] 已更新 cfd_para: gridfile={new_fts_grid}")
            except Exception as e:
                print(f"[NNW Executor] 更新 cfd_para 失败: {e}")

        # 3. 更新 partition.hypara — original_grid_file 和 partition_grid_file
        part_para = bin_dir / "partition.hypara"
        if part_para.exists():
            try:
                content = part_para.read_text(encoding="utf-8")
                content = re.sub(
                    r'(original_grid_file\s*=\s*")(.+)(")',
                    rf'\1{new_fts_grid}\3', content
                )
                content = re.sub(
                    r'(partition_grid_file\s*=\s*")(.+)(")',
                    rf'\1{new_fts_grid}\3', content
                )
                part_para.write_text(content, encoding="utf-8")
                print(f"[NNW Executor] 已更新 partition: grid files -> {new_fts_grid}")
            except Exception as e:
                print(f"[NNW Executor] 更新 partition 失败: {e}")

    def _fix_common_llm_mistakes(self, job_dir: Path, grid_filename: Optional[str] = None):
        """后处理 .hypara 文件，修正 LLM 常见的生成错误

        这是鲁棒层 — 即使 LLM 提示词不完善，执行器在运行求解器前做最后修正。

        Args:
            job_dir: 作业目录
            grid_filename: 网格文件名（用于路径一致性）
        """
        bin_dir = job_dir / "bin"
        grid_dir = job_dir / "grid"

        # 1. 修正边界条件（最重要！bcName 必须匹配网格 patch 名）
        self._fix_boundary_condition(bin_dir, grid_dir)

        # 2. 修正 partition.hypara（结构网格 pgridtype=1）
        self._fix_partition_hypara(bin_dir)

        # 3. 修正 cfd_para 常见问题（gasfile 等）
        self._fix_cfd_para(bin_dir)

        # 4. 确保网格文件名跨文件一致
        if grid_filename:
            self._update_grid_path(job_dir, grid_filename)

    # ——— _fix_common_llm_mistakes 子方法 ———

    def _fix_boundary_condition(self, bin_dir: Path, grid_dir: Path):
        """修正 boundary_condition.hypara

        优先级:
        1. 如果 grid 目录有 .bcname 文件，直接用它生成正确的边界条件
        2. 否则，清理每个 bcType 块中不属于它的参数
        """
        bc_file = bin_dir / "boundary_condition.hypara"
        if not bc_file.exists():
            return

        # ——— 方案 A: 从 .bcname 文件生成 ———
        bcname_files = list(grid_dir.glob('*.bcname'))
        if bcname_files:
            try:
                bcname_content = bcname_files[0].read_text(encoding="utf-8")
                if bcname_content.strip():
                    bc_file.write_text(bcname_content, encoding="utf-8")
                    print(f"[NNW Executor] 已从 .bcname ({bcname_files[0].name}) 生成 boundary_condition.hypara")
                    return
            except Exception as e:
                print(f"[NNW Executor] 从 .bcname 生成边界条件失败: {e}")

        # ——— 方案 B: 清理参数污染 ———
        try:
            content = bc_file.read_text(encoding="utf-8")
            original = content

            # 从 Wall(bcType=2) 和 Symmetry(bcType=3) 块中移除远场参数
            # 匹配每个边界块
            block_pattern = re.compile(
                r'(string\s+bcName\s*=\s*"[^"]*";\s*\n\s*\{)(.*?)(\})',
                re.DOTALL
            )

            def clean_block(match):
                header = match.group(1)
                body = match.group(2)
                closing = match.group(3)

                # 检测 bcType
                bc_type_match = re.search(r'bcType\s*=\s*(\d+)', body)
                if not bc_type_match:
                    return match.group(0)
                bc_type = int(bc_type_match.group(1))

                if bc_type == 2:  # Wall
                    # 只保留: bcType, wallTemperature, reParaCheckBox, twall_control_select
                    keep_params = ['bcType', 'wallTemperature', 'reParaCheckBox', 'twall_control_select']
                    cleaned = self._filter_block_params(body, keep_params)
                elif bc_type == 3:  # Symmetry
                    # 只保留: bcType
                    cleaned = self._filter_block_params(body, ['bcType'])
                elif bc_type == 4:  # Farfield
                    # 保留远场参数，移除壁面参数
                    remove_params = ['wallTemperature', 'reParaCheckBox', 'twall_control_select',
                                     'dumpHingeMoment']
                    cleaned = self._remove_params(body, remove_params)
                elif bc_type == 5:  # Outlet
                    cleaned = self._filter_block_params(body, ['bcType'])
                else:
                    return match.group(0)

                return f"{header}{cleaned}{closing}"

            content = block_pattern.sub(clean_block, content)

            if content != original:
                bc_file.write_text(content, encoding="utf-8")
                print("[NNW Executor] 已清理 boundary_condition.hypara 中的参数污染")
        except Exception as e:
            print(f"[NNW Executor] 清理边界条件失败: {e}")

    @staticmethod
    def _filter_block_params(body: str, keep_params: list) -> str:
        """在边界块中只保留指定参数"""
        lines = body.strip().split('\n')
        kept = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped == '{':
                continue
            for param in keep_params:
                if re.match(rf'(int|double|string|float)\s+{param}\s*=', stripped):
                    kept.append(line)
                    break
        return '\n' + '\n'.join(kept) + '\n'

    @staticmethod
    def _remove_params(body: str, remove_params: list) -> str:
        """从边界块中移除指定参数"""
        lines = body.strip().split('\n')
        kept = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped == '{':
                continue
            should_remove = False
            for param in remove_params:
                if re.match(rf'(int|double|string|float)\s+{param}\s*=', stripped):
                    should_remove = True
                    break
            if not should_remove:
                kept.append(line)
        return '\n' + '\n'.join(kept) + '\n'

    def _fix_partition_hypara(self, bin_dir: Path):
        """修正 partition.hypara — 结构网格用 pgridtype=1

        移除 LLM 可能添加的多余多进程参数。
        """
        part_file = bin_dir / "partition.hypara"
        if not part_file.exists():
            return

        try:
            content = part_file.read_text(encoding="utf-8")

            # 修正 pgridtype: 结构网格 = 1
            content = re.sub(r'pgridtype\s*=\s*\d+', 'pgridtype = 1', content)

            # 移除多进程参数（单进程不需要）
            content = re.sub(r'\s*int\s+npartmethod\s*=\s*\d+\s*;\s*', '\n', content)
            content = re.sub(r'\s*int\s+parallelPartitionMethod\s*=\s*\d+\s*;\s*', '\n', content)
            content = re.sub(r'\s*double\s+parmetisBalance\s*=\s*[\d.]+\s*;\s*', '\n', content)

            # 清理多余空行
            content = re.sub(r'\n{3,}', '\n\n', content)

            part_file.write_text(content, encoding="utf-8")
            print("[NNW Executor] 已修正 partition.hypara (pgridtype=1)")
        except Exception as e:
            print(f"[NNW Executor] 修正 partition 失败: {e}")

    def _fix_cfd_para(self, bin_dir: Path):
        """修正 cfd_para.hypara 常见 LLM 错误

        修正项:
        - gasfile "air" → "DK5"（NNW 标准气体数据库）
        """
        cfd_file = bin_dir / "cfd_para.hypara"
        if not cfd_file.exists():
            return

        try:
            content = cfd_file.read_text(encoding="utf-8")
            modified = False

            # gasfile 修正
            if re.search(r'gasfile\s*=\s*"air"', content):
                content = re.sub(r'(gasfile\s*=\s*)"air"', r'\1"DK5"', content)
                modified = True

            if modified:
                cfd_file.write_text(content, encoding="utf-8")
                print("[NNW Executor] 已修正 cfd_para.hypara (gasfile=DK5)")
        except Exception as e:
            print(f"[NNW Executor] 修正 cfd_para 失败: {e}")

    def _create_default_key(self, job_dir: Path):
        """创建默认 key.hypara 文件

        Args:
            job_dir: 作业目录
        """
        key_content = """string title = "PHengLEIMainParameterControlFile";
string defaultParaFile = "./bin/default_cfd_para.hypara";
int ndim = 3;
int nparafile = 1;
int nsimutask = 0;
string parafilename = "./bin/cfd_para.hypara";
int numberOfGridProcessor = 0;
string parafilename1 = "";
string parafilename2 = "";
"""
        key_path = job_dir / "key.hypara"
        key_path.write_text(key_content, encoding="utf-8")
        print(f"[NNW Executor] 已创建默认 key.hypara: {key_path}")

    def _extract_error(self, stdout: str, stderr: str, results_dir: Path) -> str:
        """从求解器输出中提取错误信息

        Args:
            stdout: 标准输出
            stderr: 标准错误
            results_dir: 结果目录（用于检查输出文件）

        Returns:
            格式化的错误消息
        """
        errors = []
        combined = stdout + "\n" + stderr

        # 常见 CFD 求解器错误模式
        patterns = [
            (r'(?i)error[:\s]+(.+?)(?:\n|$)', "错误"),
            (r'(?i)fatal[:\s]+(.+?)(?:\n|$)', "致命错误"),
            (r'(?i)invalid (.+)', "无效参数"),
            (r'(?i)cannot open (.+)', "文件打开失败"),
            (r'(?i)negative .+ detected', "负值检测"),
            (r'(?i)CFL.+?diverg', "CFL发散"),
            (r'(?i)nan detected', "NaN 检测"),
            (r'(?i)divergence', "求解发散"),
            (r'(?i)out of memory', "内存不足"),
        ]

        for pattern, label in patterns:
            matches = re.findall(pattern, combined, re.IGNORECASE)
            for match in matches:
                errors.append(f"[{label}] {match.strip()}")

        if errors:
            return "\n".join(errors[-5:])

        # 检查是否生成了输出文件
        has_results = any(results_dir.glob("*"))
        if not has_results:
            return "求解器未生成任何输出文件 — 可能未正常启动。请检查 NNW 安装和许可证。"

        tail = stderr.strip() or stdout.strip()
        if tail:
            lines = tail.split("\n")
            return "\n".join(lines[-10:])

        return "未知错误"
