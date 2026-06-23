"""仿真可视化报告生成器

读取 Abaqus 仿真结果（results.json + paths.json + 云图PNG），
用 matplotlib 生成曲线图，打包为自包含 HTML 报告。
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

    用法:
        report_path = ReportGenerator(job_dir).generate()
    """

    def __init__(self, job_dir: str):
        """初始化

        Args:
            job_dir: 仿真作业输出目录
        """
        self.job_dir = Path(job_dir)
        self.results: Dict[str, Any] = {}
        self.paths: Dict[str, Any] = {}
        self.images_b64: Dict[str, str] = {}  # 文件名 -> base64

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

    # ——— 图表生成 ———

    def _generate_charts(self):
        """用 matplotlib 生成曲线图，保存为 base64 编码的 PNG"""
        self._chart_b64: Dict[str, str] = {}

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

    # ——— HTML 报告生成 ———

    def _build_html(self) -> str:
        """组装完整的 HTML 报告"""
        summary = self.results.get('summary', {})
        images = self.results.get('images', [])
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 关键指标卡片
        cards = self._build_metric_cards(summary)

        # 云图区域
        contour_section = self._build_contour_section()

        # 曲线图区域
        chart_section = self._build_chart_section()

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MyAgent 仿真分析报告</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
    background: #f5f7fa; color: #2c3e50; line-height: 1.6;
}}
.header {{
    background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
    color: white; padding: 30px 40px; text-align: center;
}}
.header h1 {{ font-size: 28px; margin-bottom: 5px; }}
.header p {{ opacity: 0.85; font-size: 14px; }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}
.section {{
    background: white; border-radius: 12px; padding: 25px 30px;
    margin-bottom: 24px; box-shadow: 0 2px 12px rgba(0,0,0,0.06);
}}
.section h2 {{
    font-size: 20px; color: #2c3e50; margin-bottom: 16px;
    padding-bottom: 10px; border-bottom: 2px solid #3498db;
}}
.metrics {{ display: flex; flex-wrap: wrap; gap: 16px; }}
.card {{
    flex: 1; min-width: 150px; background: linear-gradient(135deg, #f8f9fa, #e9ecef);
    border-radius: 10px; padding: 18px 20px; text-align: center;
    border-left: 4px solid #3498db;
}}
.card .value {{ font-size: 28px; font-weight: 700; color: #2c3e50; }}
.card .unit {{ font-size: 14px; color: #7f8c8d; }}
.card .label {{ font-size: 13px; color: #7f8c8d; margin-top: 4px; }}
.card.warning {{ border-left-color: #e74c3c; }}
.card.success {{ border-left-color: #27ae60; }}
.contour-grid {{ display: flex; flex-wrap: wrap; gap: 20px; }}
.contour-item {{ flex: 1; min-width: 350px; }}
.contour-item img {{ width: 100%; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
.contour-item p {{ text-align: center; margin-top: 8px; color: #7f8c8d; font-size: 13px; }}
.chart-item {{ margin-bottom: 20px; }}
.chart-item img {{ width: 100%; border-radius: 8px; }}
.chart-item p {{ text-align: center; margin-top: 4px; color: #7f8c8d; font-size: 13px; }}
.footer {{
    text-align: center; color: #95a5a6; font-size: 12px;
    padding: 20px; margin-top: 10px;
}}
.no-data {{ text-align: center; color: #95a5a6; padding: 30px; }}
</style>
</head>
<body>
<div class="header">
<h1>MyAgent 有限元仿真分析报告</h1>
<p>自动生成于 {now} | 求解器: Abaqus 2024</p>
</div>

<div class="container">
{cards}

{contour_section}

{chart_section}
</div>

<div class="footer">
<p>MyAgent — Abaqus 自然语言智能助手 | 本报告由 AI 自动生成</p>
</div>
</body>
</html>"""

    def _build_metric_cards(self, summary: Dict) -> str:
        """构建关键指标卡片"""
        if not summary:
            return ''

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

    def _build_contour_section(self) -> str:
        """构建云图区域"""
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
