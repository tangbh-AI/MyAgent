"""仿真可视化报告生成器

读取仿真结果（results.json + paths.json + 云图PNG），
用 matplotlib 生成曲线图，打包为自包含 HTML 报告。

支持 FEA（Abaqus）和 CFD（NNW-HyFLOW）两种模式，
自动检测结果类型并匹配对应样式。
"""

import base64
import json
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use('Agg')  # 非 GUI 后端，支持无头服务器
import matplotlib.pyplot as plt


class ReportGenerator:
    """仿真分析报告生成器

    从作业目录读取结果数据，生成包含关键指标、云图、曲线的 HTML 报告。
    自动检测 FEA / CFD 结果类型，匹配对应主题样式。

    用法:
        report_path = ReportGenerator(job_dir).generate()
    """

    def __init__(self, job_dir: str, solver_name: str = "Abaqus"):
        """初始化

        Args:
            job_dir: 仿真作业输出目录
            solver_name: 求解器名称（用于报告标题）
        """
        self.job_dir = Path(job_dir)
        self.solver_name = solver_name
        self.results: Dict[str, Any] = {}
        self.paths: Dict[str, Any] = {}
        self.images_b64: Dict[str, str] = {}  # 文件名 -> base64
        self.result_type: str = "fea"  # "fea" 或 "cfd"，读取数据后自动检测
        self._chart_b64: Dict[str, str] = {}  # 图表名 -> base64

    def generate(self) -> Optional[str]:
        """生成完整的 HTML 分析报告

        Returns:
            报告文件路径，数据不足时返回 None
        """
        self._read_data()

        if not self.results:
            return None

        self._generate_charts()
        report_path = self.job_dir / 'analysis_report.html'
        html = self._build_html()
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"[Report] 分析报告已生成: {report_path}")
        return str(report_path)

    # ——— 数据读取 ———

    def _read_data(self):
        """读取 results.json 和 paths.json，加载云图 base64"""
        # results.json
        results_path = self.job_dir / 'results.json'
        if results_path.exists():
            with open(results_path, 'r', encoding='utf-8') as f:
                self.results = json.load(f)

        # paths.json
        paths_path = self.job_dir / 'paths.json'
        if paths_path.exists():
            with open(paths_path, 'r', encoding='utf-8') as f:
                self.paths = json.load(f)

        # 图片 base64 编码
        for img_name in self.results.get('images', []):
            img_path = self.job_dir / img_name
            if img_path.exists():
                with open(img_path, 'rb') as f:
                    self.images_b64[img_name] = base64.b64encode(f.read()).decode()

        # 自动检测结果类型
        self._detect_result_type()

    def _detect_result_type(self):
        """自动检测结果类型：CFD（有升力/阻力系数）或 FEA（有应力/位移）"""
        summary = self.results.get('summary', {})
        if "cl" in summary or "cd" in summary:
            self.result_type = "cfd"
        elif "max_stress_mises" in summary or "max_displacement" in summary:
            self.result_type = "fea"
        else:
            # 默认保持 FEA（向后兼容）
            self.result_type = "fea"

    # ——— 图表生成 ———

    def _generate_charts(self):
        """用 matplotlib 生成曲线图，保存为 base64 编码的 PNG"""
        if not self.paths:
            return

        curves = self.paths.get('curves', {})
        if not curves:
            return

        main_axis = self.paths.get('main_axis', {})
        axis_label = main_axis.get('direction', 'X')
        axis_unit = main_axis.get('unit', 'mm')

        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

        x_label = f'位置 ({axis_label}, {axis_unit})'

        # 图表 1: 应力分布曲线
        if 'stress_mises' in curves:
            self._chart_b64['stress_curve'] = self._draw_line_chart(
                curves['stress_mises'],
                title='von Mises 应力分布',
                xlabel=x_label,
                ylabel='应力 (MPa)',
                color='#e74c3c',
            )

        # 图表 2: 位移曲线
        if 'displacement' in curves:
            self._chart_b64['displacement_curve'] = self._draw_line_chart(
                curves['displacement'],
                title='位移分布',
                xlabel=x_label,
                ylabel='位移 (mm)',
                color='#3498db',
            )

        # 图表 3: 主应力曲线
        if 'max_principal_stress' in curves and 'min_principal_stress' in curves:
            self._chart_b64['principal_curve'] = self._draw_dual_line_chart(
                curves['max_principal_stress'],
                curves['min_principal_stress'],
                title='主应力分布',
                xlabel=x_label,
                ylabel='应力 (MPa)',
            )

        plt.close('all')

    def _draw_line_chart(
        self,
        data: List[Dict],
        title: str,
        xlabel: str,
        ylabel: str,
        color: str,
        figsize=(8, 4),
    ) -> str:
        """绘制单线折线图，返回 base64 PNG"""
        fig, ax = plt.subplots(figsize=figsize)
        xs = [p['x'] for p in data]
        ys = [p['y'] for p in data]

        ax.plot(xs, ys, color=color, linewidth=2, marker='.', markersize=3)
        ax.fill_between(xs, ys, alpha=0.1, color=color)
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel(xlabel, fontsize=11)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        # 标注最大值
        if ys:
            max_idx = ys.index(max(ys))
            ax.annotate(
                f'{ys[max_idx]:.2f}',
                xy=(xs[max_idx], ys[max_idx]),
                xytext=(0, 10),
                textcoords='offset points',
                fontsize=9,
                color=color,
                ha='center',
                fontweight='bold',
            )

        fig.tight_layout()
        return self._fig_to_b64(fig)

    def _draw_dual_line_chart(
        self,
        data1: List[Dict],
        data2: List[Dict],
        title: str,
        xlabel: str,
        ylabel: str,
        figsize=(8, 4),
    ) -> str:
        """绘制双线折线图（对比最大/最小主应力）"""
        fig, ax = plt.subplots(figsize=figsize)

        xs1, ys1 = [p['x'] for p in data1], [p['y'] for p in data1]
        xs2, ys2 = [p['x'] for p in data2], [p['y'] for p in data2]

        ax.plot(xs1, ys1, color='#e74c3c', linewidth=2, label='最大主应力', marker='.')
        ax.plot(xs2, ys2, color='#3498db', linewidth=2, label='最小主应力', marker='.')
        ax.fill_between(xs1, ys1, ys2, alpha=0.05, color='gray')

        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel(xlabel, fontsize=11)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.legend(loc='best', frameon=True, fancybox=True)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        fig.tight_layout()
        return self._fig_to_b64(fig)

    def _fig_to_b64(self, fig) -> str:
        """将 matplotlib figure 转为 base64 PNG 字符串"""
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=120, bbox_inches='tight')
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode()
        buf.close()
        return b64

    # ——— HTML 报告生成（入口） ———

    def _build_html(self) -> str:
        """组装完整的 HTML 报告 — 根据结果类型分派"""
        if self.result_type == "cfd":
            return self._build_html_cfd()
        else:
            return self._build_html_fea()

    # ——— FEA HTML（保持向后兼容） ———

    def _build_html_fea(self) -> str:
        """组装 FEA（Abaqus）HTML 报告"""
        summary = self.results.get('summary', {})
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cards = self._build_fea_cards_html(summary)
        contour_section = self._build_contour_section()
        chart_section = self._build_chart_section()

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MyAgent 仿真分析报告</title>
<style>
{self._base_styles()}
{self._fea_styles()}
</style>
</head>
<body>
<div class="header fea-header">
<h1>MyAgent 有限元仿真分析报告</h1>
<p>自动生成于 {now} | 求解器: {self.solver_name}</p>
</div>

<div class="container">
{cards}

{contour_section}

{chart_section}
</div>

<div class="footer">
<p>MyAgent — {self.solver_name} 自然语言智能助手 | 本报告由 AI 自动生成</p>
</div>
</body>
</html>"""

    # ——— CFD HTML（参考 NNW 报告样式） ———

    def _build_html_cfd(self) -> str:
        """组装 CFD（NNW-HyFLOW）HTML 报告 — 匹配参考报告样式"""
        summary = self.results.get('summary', {})
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        project_name = summary.get('project_name', 'CFD 仿真')

        # 各区域
        op_section = self._build_operating_conditions()
        aero_section = self._build_cfd_aero_cards(summary)
        exp_compare = self._build_experiment_compare(summary)
        conv_section = self._build_convergence_section(summary)
        flowfield_section = self._build_flowfield_section()
        result_images = self._build_result_images_section()

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MyAgent CFD 仿真分析报告 — {project_name}</title>
<style>
{self._base_styles()}
{self._cfd_styles()}
</style>
</head>
<body>
<div class="header cfd-header">
<h1>MyAgent CFD 仿真分析报告</h1>
<p>{project_name} | 求解器: {self.solver_name} (PHengLEI) | {now}</p>
</div>

<div class="container">
{op_section}

{aero_section}

{exp_compare}

{conv_section}

{flowfield_section}

{result_images}
</div>

<div class="footer">
<p>MyAgent — NNW-HyFLOW CFD 自然语言智能助手 | 本报告由 AI 自动生成</p>
</div>
</body>
</html>"""

    # ——— 基础样式（FEA + CFD 共用） ———

    @staticmethod
    def _base_styles() -> str:
        """基础样式，FEA 和 CFD 共用"""
        return """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    background: #f5f7fa; color: #2c3e50; line-height: 1.6;
}
.header {
    color: white; padding: 35px 40px; text-align: center;
}
.header h1 { font-size: 28px; margin-bottom: 8px; }
.header p { opacity: 0.85; font-size: 14px; }
.container { max-width: 1100px; margin: 0 auto; padding: 20px; }
.section {
    background: white; border-radius: 12px; padding: 25px 30px;
    margin-bottom: 24px; box-shadow: 0 2px 12px rgba(0,0,0,0.06);
}
.section h2 {
    font-size: 20px; color: #2c3e50; margin-bottom: 16px;
    padding-bottom: 10px; border-bottom: 2px solid #3498db;
}
.metrics { display: flex; flex-wrap: wrap; gap: 16px; }
.card {
    flex: 1; min-width: 160px; background: linear-gradient(135deg, #f8f9fa, #e9ecef);
    border-radius: 10px; padding: 18px 20px; text-align: center;
    border-left: 4px solid #3498db;
}
.card .value { font-size: 24px; font-weight: 700; color: #2c3e50; }
.card .label { font-size: 13px; color: #7f8c8d; margin-top: 4px; }
.card.warning { border-left-color: #e67e22; }
.card.success { border-left-color: #27ae60; }
.contour-grid { display: flex; flex-wrap: wrap; gap: 20px; }
.contour-item { flex: 1; min-width: 400px; }
.contour-item img { width: 100%; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
.contour-item p { text-align: center; margin-top: 8px; color: #7f8c8d; font-size: 13px; }
.chart-item { margin-bottom: 20px; }
.chart-item img { width: 100%; border-radius: 8px; }
.chart-item p { text-align: center; margin-top: 4px; color: #7f8c8d; font-size: 13px; }
.footer {
    text-align: center; color: #95a5a6; font-size: 12px;
    padding: 20px; margin-top: 10px;
}
.no-data { text-align: center; color: #95a5a6; padding: 30px; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 12px 16px; border-bottom: 1px solid #eee; }
th { background: #f0f4f8; font-weight: 600; }
tr:hover { background: #f8f9fa; }
.param-table td:first-child { font-weight: 600; color: #2c3e50; width: 200px; }
.params { font-size: 14px; }
.params td { padding: 6px 12px; }
"""

    # ——— FEA 专属样式 ———

    @staticmethod
    def _fea_styles() -> str:
        """FEA（Abaqus）专属样式"""
        return """
.fea-header {
    background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
}
.section h2 { border-bottom-color: #3498db; }
.card { border-left-color: #3498db; }
"""

    # ——— CFD 专属样式（匹配 NNW 参考报告） ———

    @staticmethod
    def _cfd_styles() -> str:
        """CFD（NNW-HyFLOW）专属样式 — 深蓝主题"""
        return """
.cfd-header {
    background: linear-gradient(135deg, #1a3a4a 0%, #2980b9 100%);
}
.section h2 { border-bottom-color: #2980b9; }
.card { border-left-color: #2980b9; }
.contour-item { min-width: 400px; }
"""  # CFD 继承基础样式的 .card.warning / .card.success

    # ——— 工况参数 section（CFD） ———

    def _build_operating_conditions(self) -> str:
        """构建工况参数 section — 从 results.json 的 operating_conditions 读取"""
        op = self.results.get('summary', {}).get('operating_conditions')
        if not op:
            return ''

        rows = []
        # 定义参数显示顺序和标签
        param_specs = [
            ('mach_number', '马赫数 Ma'),
            ('attack_angle_deg', '攻角 AoA', '°'),
            ('reynolds_number', '雷诺数 Re', '/m'),
            ('temperature_k', '来流温度 T∞', 'K'),
            ('sideslip_angle_deg', '侧滑角', '°'),
            ('wall_temperature', '壁面'),
            ('turbulence_model', '湍流模型'),
            ('gamma', '比热比 γ'),
            ('inviscid_flux', '无粘通量'),
            ('limiter', '限制器'),
            ('gradient_method', '梯度方法'),
            ('time_integration', '时间推进'),
            ('cfl_info', 'CFL'),
            ('grid_info', '网格'),
        ]

        row_parts = []
        col_count = 0
        for spec in param_specs:
            key = spec[0]
            if key not in op:
                continue
            label = spec[1]
            unit = spec[2] if len(spec) > 2 else ''
            val = op[key]
            # 格式化数值
            if isinstance(val, float):
                val_str = f'{val:.4g}'
            else:
                val_str = str(val)
            if unit:
                val_str = f'{val_str} {unit}'

            # 两个参数一行
            row_parts.append(f'<td>{label}</td><td>{val_str}</td>')
            col_count += 1

        if not row_parts:
            return ''

        # 拼成两列的表格
        rows_html = []
        for i in range(0, len(row_parts), 2):
            pair = ''.join(row_parts[i:i+2])
            rows_html.append(f'<tr>{pair}</tr>')

        return (
            '<div class="section">'
            '<h2>工况参数</h2>'
            '<table class="param-table params">'
            + ''.join(rows_html) +
            '</table>'
            '</div>'
        )

    # ——— 气动力系数卡片（CFD） ———

    def _build_cfd_aero_cards(self, summary: Dict) -> str:
        """构建气动力系数指标卡片 — 不含收敛信息（收敛信息独立 section）"""
        cards = []

        cfd_metrics = [
            ('cl', '升力系数 CL', '', ''),
            ('cd', '阻力系数 CD', '', ''),
            ('l_d', '升阻比 L/D', '', 'success'),
            ('cm', '俯仰力矩 Cm', '', ''),
            ('cz', '侧向力 CZ', '', ''),
        ]

        for key, label, unit, style in cfd_metrics:
            if key in summary and summary[key] is not None:
                val = summary[key]
                val_str = f'{val:.6f}' if isinstance(val, float) and abs(val) < 10 else (
                    f'{val:.4f}' if isinstance(val, float) else str(val))
                cards.append(
                    f'<div class="card {style}">'
                    f'<div class="value">{val_str}</div>'
                    f'<div class="label">{label}</div>'
                    f'</div>'
                )

        if not cards:
            return ''

        return (
            '<div class="section">'
            '<h2>气动力系数</h2>'
            f'<div class="metrics">{"".join(cards)}</div>'
            '</div>'
        )

    # ——— 收敛信息 section（CFD） ———

    def _build_convergence_section(self, summary: Dict) -> str:
        """构建收敛信息独立 section"""
        cards = []

        converged = summary.get("converged", False)
        final_res = summary.get("final_residual")
        n_iter = summary.get("n_iterations")

        conv_style = "success" if converged else "warning"
        conv_text = "[OK] 已收敛" if converged else "[?] 未收敛"

        cards.append(
            f'<div class="card {conv_style}">'
            f'<div class="value">{conv_text}</div>'
            f'<div class="label">收敛状态</div>'
            f'</div>'
        )

        if final_res is not None:
            cards.append(
                f'<div class="card">'
                f'<div class="value">{final_res:.2e}</div>'
                f'<div class="label">最终残差</div>'
                f'</div>'
            )

        if n_iter is not None:
            cards.append(
                f'<div class="card">'
                f'<div class="value">{n_iter}</div>'
                f'<div class="label">迭代步数</div>'
                f'</div>'
            )

        if not cards:
            return ''

        return (
            '<div class="section">'
            '<h2>收敛信息</h2>'
            f'<div class="metrics">{"".join(cards)}</div>'
            '</div>'
        )

    # ——— 实验对比 section（CFD） ———

    def _build_experiment_compare(self, summary: Dict) -> str:
        """构建实验结果对比 section — 仅在有参考数据时显示"""
        exp_ref = summary.get('experiment_reference')
        if not exp_ref:
            return ''

        rows = ''
        for key, info in exp_ref.get('comparisons', {}).items():
            sim_val = summary.get(key.lower())
            if sim_val is None:
                continue
            exp_val = info.get('value')
            label = info.get('label', key)
            # 计算偏差
            try:
                dev = abs(sim_val - exp_val) / max(abs(exp_val), 1e-10) * 100
                dev_str = f'{dev:.1f}%'
                dev_color = 'green' if dev < 10 else ('orange' if dev < 30 else 'red')
            except (TypeError, ZeroDivisionError):
                dev_str = '--'
                dev_color = '#95a5a6'

            rows += (
                f'<tr><td>{label}</td>'
                f'<td>{sim_val:.6f}</td>'
                f'<td>{exp_val}</td>'
                f'<td style="color:{dev_color}">{dev_str}</td></tr>'
            )

        if not rows:
            return ''

        ref_text = exp_ref.get('description', '')
        ref_note = f'<p style="font-size:12px;color:#95a5a6;margin-top:8px;">参考: {ref_text}</p>' if ref_text else ''

        return (
            '<div class="section">'
            '<h2>实验结果对比</h2>'
            '<table style="width:100%;border-collapse:collapse;text-align:center;">'
            '<tr style="background:#f0f4f8;"><th>参数</th><th>本仿真</th><th>文献实验值</th><th>偏差</th></tr>'
            + rows +
            '</table>'
            + ref_note +
            '</div>'
        )

    # ——— 流场云图 section（CFD） ———

    def _build_flowfield_section(self) -> str:
        """构建流场云图 section — 显示 tecflow 等 CFD 云图"""
        # CFD 特征云图关键词
        cfd_keywords = ['contour', 'mach', 'pressure', 'density', 'tecflow',
                       'cp_', 'velocity', 'temperature', 'vorticity']

        cfd_images = {}
        other_images = {}
        for name, b64 in self.images_b64.items():
            name_lower = name.lower()
            if any(kw in name_lower for kw in cfd_keywords):
                cfd_images[name] = b64
            else:
                other_images[name] = b64

        if not cfd_images:
            return ''

        items = []
        for img_name, b64 in cfd_images.items():
            label = img_name.replace('_', ' ').replace('.png', '')
            items.append(
                f'<div class="contour-item" style="min-width:600px;">'
                f'<img src="data:image/png;base64,{b64}" alt="{label}">'
                f'<p>{label}</p>'
                f'</div>'
            )

        # 备注
        summary = self.results.get('summary', {})
        grid_info = ''
        if 'operating_conditions' in summary:
            grid_info = summary['operating_conditions'].get('grid_info', '')
        note = ''
        if grid_info:
            note = f'<p style="font-size:12px;color:#95a5a6;margin-top:8px;">数据来源: tecflow.plt (PHengLEI 计算, {grid_info})</p>'
        elif summary.get('has_tecflow'):
            note = '<p style="font-size:12px;color:#95a5a6;margin-top:8px;">数据来源: tecflow.plt (PHengLEI 计算)</p>'

        return (
            '<div class="section">'
            '<h2>流场云图 (对称面)</h2>'
            f'<div class="contour-grid">{"".join(items)}</div>'
            + note +
            '</div>'
        )

    # ——— 结果图像 section（CFD） ———

    def _build_result_images_section(self) -> str:
        """构建结果图像 section — 气动力曲线、残差曲线等"""
        # 分类：曲线图 vs 云图
        curve_keywords = ['aerodynamic', 'residual', 'coefficient', 'convergence',
                         'aero', 'force', 'moment', 'cp_distribution']
        cfd_contour_kw = ['contour', 'mach', 'pressure', 'density']

        curve_images = {}
        for name, b64 in self.images_b64.items():
            name_lower = name.lower()
            # 排除流场云图（已在 _build_flowfield_section 中显示）
            if any(kw in name_lower for kw in cfd_contour_kw):
                continue
            curve_images[name] = b64

        if not curve_images:
            return (
                '<div class="section">'
                '<h2>结果图像</h2>'
                '<div class="no-data">暂无结果图像</div>'
                '</div>'
            )

        items = []
        for img_name, b64 in curve_images.items():
            label = img_name.replace('_', ' ').replace('.png', '')
            items.append(
                f'<div class="contour-item">'
                f'<img src="data:image/png;base64,{b64}" alt="{label}">'
                f'<p>{label}</p>'
                f'</div>'
            )

        return (
            '<div class="section">'
            '<h2>结果图像</h2>'
            f'<div class="contour-grid">{"".join(items)}</div>'
            '</div>'
        )

    # ——— 向后兼容的 FEA 方法 ———

    def _build_fea_cards_html(self, summary: Dict) -> str:
        """构建 FEA 关键指标卡片（保持向后兼容）"""
        # 自动检测：如果有 cl/cd 则走 CFD 路线
        if "cl" in summary or "cd" in summary:
            return self._build_cfd_aero_cards(summary)
        return self._build_fea_cards(summary)

    # 向后兼容的别名（旧测试调用 _build_metric_cards）
    _build_metric_cards = _build_fea_cards_html

    def _build_fea_cards(self, summary: Dict) -> str:
        """构建 FEA 关键指标卡片"""
        cards = []
        metrics = [
            ('max_stress_mises', '最大 von Mises 应力', 'MPa', 'warning'),
            ('max_displacement', '最大位移', 'mm', ''),
            ('max_principal_stress', '最大主应力', 'MPa', ''),
            ('min_principal_stress', '最小主应力', 'MPa', ''),
            ('total_force', '总反力', 'N', ''),
            ('safety_factor', '安全系数', '', 'success'),
        ]

        for key, label, unit, style in metrics:
            if key in summary:
                val = summary[key]
                val_str = f'{val:.2f}' if isinstance(val, float) else str(val)
                cards.append(
                    f'<div class="card {style}">'
                    f'<div class="value">{val_str}<span class="unit">{unit}</span></div>'
                    f'<div class="label">{label}</div>'
                    f'</div>'
                )

        if not cards:
            return ''

        return (
            '<div class="section">'
            '<h2>关键结果</h2>'
            f'<div class="metrics">{"".join(cards)}</div>'
            '</div>'
        )

    def _build_cfd_cards(self, summary: Dict) -> str:
        """构建 CFD 气动力系数指标卡片 — 向后兼容（含收敛信息，用于旧调用方）"""
        # 直接委托给新的独立方法并附加收敛信息
        aero = self._build_cfd_aero_cards(summary)
        conv = self._build_convergence_section(summary)
        return aero + conv

    def _build_contour_section(self) -> str:
        """构建云图区域 — FEA 模式"""
        img_keys = [k for k in self.images_b64 if 'contour' in k.lower() or 'stress' in k.lower() or 'disp' in k.lower()]
        if not img_keys:
            img_keys = list(self.images_b64.keys())

        if not img_keys:
            return (
                '<div class="section">'
                '<h2>结果云图</h2>'
                '<div class="no-data">暂无云图</div>'
                '</div>'
            )

        items = []
        for img_name in img_keys:
            b64 = self.images_b64[img_name]
            label = img_name.replace('_', ' ').replace('.png', '')
            items.append(
                f'<div class="contour-item">'
                f'<img src="data:image/png;base64,{b64}" alt="{label}">'
                f'<p>{label}</p>'
                f'</div>'
            )

        return (
            '<div class="section">'
            '<h2>结果云图</h2>'
            f'<div class="contour-grid">{"".join(items)}</div>'
            '</div>'
        )

    def _build_chart_section(self) -> str:
        """构建曲线图区域"""
        chart_names = {
            'stress_curve': '应力分布曲线',
            'displacement_curve': '位移曲线',
            'principal_curve': '主应力分布曲线',
        }

        available = [(k, v) for k, v in self._chart_b64.items() if v]
        if not available:
            return (
                '<div class="section">'
                '<h2>分析曲线</h2>'
                '<div class="no-data">暂无曲线数据</div>'
                '</div>'
            )

        items = []
        for key, b64 in available:
            title = chart_names.get(key, key)
            items.append(
                f'<div class="chart-item">'
                f'<img src="data:image/png;base64,{b64}" alt="{title}">'
                f'<p>{title}</p>'
                f'</div>'
            )

        return (
            '<div class="section">'
            '<h2>分析曲线</h2>'
            f'{"".join(items)}'
            '</div>'
        )
