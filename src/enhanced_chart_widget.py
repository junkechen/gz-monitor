# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 增强图表组件
支持多种图表类型：折线图、柱状图、饼图、仪表盘、散点图等
"""

import os
import sys
import tempfile

from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl


class EnhancedChartWidget(QWidget):
    """增强图表组件（使用Plotly）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self.web_view = QWebEngineView()
        self._layout.addWidget(self.web_view)

        self._tmp_file = None

    def plot_line(self, times, series_list, title="数据曲线", show_thresholds=None):
        """绘制折线图（支持阈值线）"""
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        fig = go.Figure()

        # 绘制数据曲线
        for series in series_list:
            fig.add_trace(go.Scatter(
                x=times,
                y=series['data'],
                mode='lines+markers',
                name=series['name'],
                connectgaps=False,
                line=dict(width=2, color=series.get('color', None)),
                marker=dict(size=6)
            ))

        # 绘制阈值线
        if show_thresholds:
            for param_name, threshold in show_thresholds.items():
                y_vals = [threshold] * len(times)
                fig.add_trace(go.Scatter(
                    x=times,
                    y=y_vals,
                    mode='lines',
                    name=f"{param_name}阈值",
                    line=dict(width=2, dash='dash', color='rgba(255, 99, 71, 0.8)'),
                    hoverinfo='name+y'
                ))

        fig.update_layout(
            title=title,
            xaxis_title="时间",
            yaxis_title="数值",
            hovermode='x unified',
            template='plotly_dark',
            height=450,
            margin=dict(l=60, r=30, t=50, b=50),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )

        self._load_html(fig.to_html(include_plotlyjs=True, full_html=True))

    def plot_bar(self, categories, values_list, series_names, title="柱状图"):
        """绘制柱状图（支持多系列对比）"""
        import plotly.graph_objects as go

        fig = go.Figure()

        for idx, values in enumerate(values_list):
            series_name = series_names[idx] if idx < len(series_names) else f"系列{idx+1}"
            fig.add_trace(go.Bar(
                x=categories,
                y=values,
                name=series_name,
                marker=dict(
                    color=values,
                    colorscale='Viridis'
                )
            ))

        fig.update_layout(
            title=title,
            xaxis_title="类别",
            yaxis_title="数值",
            barmode='group',
            template='plotly_dark',
            height=450,
            margin=dict(l=60, r=30, t=50, b=50)
        )

        self._load_html(fig.to_html(include_plotlyjs=True, full_html=True))

    def plot_pie(self, labels, values, title="饼图"):
        """绘制饼图"""
        import plotly.graph_objects as go

        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            textinfo='label+percent',
            textposition='inside',
            hole=0.3,
            marker=dict(colors=['#1a6b3c', '#2d9e60', '#58a6ff', '#f85149', '#3fb950'])
        )])

        fig.update_layout(
            title=title,
            template='plotly_dark',
            height=450,
            margin=dict(l=20, r=20, t=50, b=20)
        )

        self._load_html(fig.to_html(include_plotlyjs=True, full_html=True))

    def plot_gauge(self, value, title="仪表盘", max_value=100, threshold_warning=80, threshold_danger=95):
        """绘制仪表盘"""
        import plotly.graph_objects as go

        # 根据数值设置颜色
        if value <= threshold_warning:
            color = "#3fb950"  # 绿色
        elif value <= threshold_danger:
            color = "#ffd700"  # 黄色
        else:
            color = "#f85149"  # 红色

        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=value,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': title},
            delta={'reference': max_value * 0.8},
            gauge={
                'axis': {'range': [None, max_value], 'tickwidth': 1, 'tickcolor': "#8b949e"},
                'bar': {'color': color},
                'bgcolor': "white",
                'borderwidth': 2,
                'bordercolor': "#30363d",
                'steps': [
                    {'range': [0, threshold_warning], 'color': 'rgba(63, 185, 80, 0.2)'},
                    {'range': [threshold_warning, threshold_danger], 'color': 'rgba(255, 215, 0, 0.2)'},
                    {'range': [threshold_danger, max_value], 'color': 'rgba(248, 81, 73, 0.2)'}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': threshold_danger
                }
            }
        ))

        fig.update_layout(
            template='plotly_dark',
            height=400,
            margin=dict(l=20, r=20, t=50, b=20)
        )

        self._load_html(fig.to_html(include_plotlyjs=True, full_html=True))

    def plot_scatter(self, x_values, y_values, series_list, title="散点图"):
        """绘制散点图"""
        import plotly.graph_objects as go

        fig = go.Figure()

        for idx, series in enumerate(series_list):
            if idx < len(x_values) and idx < len(y_values):
                fig.add_trace(go.Scatter(
                    x=x_values[idx],
                    y=y_values[idx],
                    mode='markers',
                    name=series.get('name', f"系列{idx+1}"),
                    marker=dict(
                        size=10,
                        color=series.get('color', '#58a6ff'),
                        opacity=0.8
                    )
                ))

        fig.update_layout(
            title=title,
            xaxis_title="X轴",
            yaxis_title="Y轴",
            template='plotly_dark',
            height=450,
            margin=dict(l=60, r=30, t=50, b=50)
        )

        self._load_html(fig.to_html(include_plotlyjs=True, full_html=True))

    def plot_box(self, data_dict, title="箱线图"):
        """绘制箱线图"""
        import plotly.graph_objects as go

        fig = go.Figure()

        for name, values in data_dict.items():
            fig.add_trace(go.Box(
                y=values,
                name=name,
                boxpoints='outliers',
                marker_color='#58a6ff'
            ))

        fig.update_layout(
            title=title,
            yaxis_title="数值",
            template='plotly_dark',
            height=450,
            margin=dict(l=60, r=30, t=50, b=50)
        )

        self._load_html(fig.to_html(include_plotlyjs=True, full_html=True))

    def plot_heatmap(self, x_labels, y_labels, z_values, title="热力图"):
        """绘制热力图"""
        import plotly.graph_objects as go

        fig = go.Figure(data=go.Heatmap(
            z=z_values,
            x=x_labels,
            y=y_labels,
            colorscale='Viridis',
            showscale=True
        ))

        fig.update_layout(
            title=title,
            template='plotly_dark',
            height=450,
            margin=dict(l=80, r=50, t=50, b=50)
        )

        self._load_html(fig.to_html(include_plotlyjs=True, full_html=True))

    def plot_multi_chart(self, charts_data, title="多图表分析"):
        """绘制多图表布局（2x2或1x2）"""
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        n_charts = len(charts_data)

        if n_charts == 1:
            cols = 1
            rows = 1
        elif n_charts == 2:
            cols = 2
            rows = 1
        else:
            cols = 2
            rows = 2

        fig = make_subplots(
            rows=rows,
            cols=cols,
            subplot_titles=[chart['title'] for chart in charts_data[:n_charts]]
        )

        for idx, chart_data in enumerate(charts_data[:n_charts]):
            row = (idx // cols) + 1
            col = (idx % cols) + 1

            if chart_data['type'] == 'line':
                for series in chart_data['series']:
                    fig.add_trace(
                        go.Scatter(
                            x=chart_data['x'],
                            y=series['data'],
                            name=series['name'],
                            mode='lines+markers'
                        ),
                        row=row, col=col
                    )

        fig.update_layout(
            title_text=title,
            template='plotly_dark',
            height=600,
            margin=dict(l=60, r=30, t=80, b=50),
            showlegend=True
        )

        self._load_html(fig.to_html(include_plotlyjs=True, full_html=True))

    def _load_html(self, html: str):
        """将 HTML 写入临时文件后用 file:// 协议加载，绕过 setHtml 的 2MB 限制"""
        try:
            # 清理上一个临时文件
            if self._tmp_file and os.path.exists(self._tmp_file):
                try:
                    os.remove(self._tmp_file)
                except Exception:
                    pass

            # 写入新临时文件（UTF-8）
            fd, path = tempfile.mkstemp(suffix='.html', prefix='gz_enhanced_chart_')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(html)
            self._tmp_file = path

            self.web_view.setUrl(QUrl.fromLocalFile(path))
        except Exception as e:
            # 降级：直接 setHtml（可能被截断，但至少不崩溃）
            self.web_view.setHtml(html)

    def clear(self):
        """清空图表"""
        self.web_view.setHtml(
            "<div style='padding:40px; text-align:center; color:#8b949e; font-size:16px;'>暂无数据</div>"
        )
