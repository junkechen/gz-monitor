# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 图表组件
使用 matplotlib 替代 WebEngine，Windows 7 兼容
支持点击图例隐藏/显示曲线，默认都不选中
支持鼠标悬停显示数值（精准 annotate + 竖线跟踪）
"""

import os
import re
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QScrollArea, QFrame, QLabel
from PyQt5.QtCore import Qt, QPoint

# 设置 matplotlib 使用 Qt5 后端
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from datetime import datetime

# 设置中文字体 - 优先使用系统自带的中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

# ── 时间缩写转换 ──────────────────────────────────────────────────────────────
_MONTH_SHORT = {
    '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr',
    '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Aug',
    '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec',
}

def _fmt_time_label(time_str):
    """
    将时间字符串转为英文缩写，节省 X 轴空间。
    支持格式：
      '2026-03-25 14:00' → 'Mar 25\n14:00'
      '2026-03-25 14'    → 'Mar 25\n14:00'   (历史小时数据)
      '2026-03-25'       → 'Mar 25'
      其他格式原样返回
    """
    if not time_str:
        return time_str
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{2})(?::(\d{2}))?)?', str(time_str))
    if not m:
        return time_str
    _, month, day, hh, mm = m.groups()
    mon = _MONTH_SHORT.get(month, month)
    day_str = f"{mon} {int(day)}"
    if hh is not None:
        time_part = f"{hh}:{mm}" if mm is not None else f"{hh}:00"
        return f"{day_str}\n{time_part}"
    return day_str


def _fmt_tooltip_time(time_str):
    """
    Tooltip 专用：显示完整年月日 + 时间，方便用户看清楚数据点所在时间。
    支持格式：
      '2026-03-25 14:00' → '2026-03-25\n14:00'
      '2026-03-25 14'    → '2026-03-25\n14:00'   (历史小时数据，只有HH)
      '2026-03-25'       → '2026-03-25'
      其他格式原样返回
    """
    if not time_str:
        return str(time_str) if time_str is not None else ''
    s = str(time_str).strip()
    # 匹配 YYYY-MM-DD[ HH[:MM[:SS]]]
    m = re.match(r'(\d{4}-\d{2}-\d{2})(?:\s+(\d{2})(?::(\d{2})(?::\d{2})?)?)?$', s)
    if not m:
        return s
    date_part, hh, mm = m.groups()
    if hh is not None:
        time_part = f"{hh}:{mm}" if mm is not None else f"{hh}:00"
        return f"{date_part}\n{time_part}"
    return date_part


class HoverFigureCanvas(FigureCanvasQTAgg):
    """支持鼠标悬停的 Canvas（使用 annotate + 竖线跟踪）"""

    def __init__(self, figure):
        super().__init__(figure)
        self._times = []          # 原始时间字符串列表
        self._callback_id = None
        self._vline = None        # 竖线对象
        self._annot = None        # annotate 对象
        self._dot_artists = []    # 高亮圆点列表

    def set_hover_data(self, times):
        """设置时间轴数据（仅需时间列表，系列数据从 ax.lines 实时读取）"""
        self._times = times

    def setup_hover(self):
        """绑定/重新绑定鼠标移动事件"""
        if self._callback_id is not None:
            try:
                self.mpl_disconnect(self._callback_id)
            except Exception:
                pass
        self._callback_id = self.mpl_connect('motion_notify_event', self._on_hover)
        # 鼠标离开画布时隐藏
        self.mpl_connect('axes_leave_event', lambda e: self._hide_tooltip())

    # ── 内部工具 ──────────────────────────────────────────────────────────────
    def _get_ax(self):
        return self.figure.axes[0] if self.figure.axes else None

    def _hide_tooltip(self):
        """清除所有悬停装饰"""
        changed = False
        if self._annot and self._annot.axes:
            self._annot.set_visible(False)
            changed = True
        if self._vline and self._vline.axes:
            self._vline.set_visible(False)
            changed = True
        for dot in self._dot_artists:
            if dot.axes:
                dot.set_visible(False)
        self._dot_artists = []
        if changed:
            self.draw_idle()

    def _on_hover(self, event):
        ax = self._get_ax()
        if ax is None or event.inaxes != ax:
            self._hide_tooltip()
            return

        xdata = event.xdata
        if xdata is None or not self._times:
            self._hide_tooltip()
            return

        n = len(self._times)
        # 找到最近的数据点索引（X 轴是整数索引 0..n-1）
        idx = int(round(xdata))
        idx = max(0, min(idx, n - 1))

        # 收集所有可见线条在该点的值
        visible_lines = [ln for ln in ax.lines if ln.get_visible() and not ln.get_label().startswith('_')]
        if not visible_lines:
            self._hide_tooltip()
            return

        rows = []
        valid_y = []
        for ln in visible_lines:
            ydata = ln.get_ydata()
            if idx < len(ydata):
                yv = ydata[idx]
                # 过滤 nan/None
                try:
                    if yv is None or (yv != yv):  # nan check
                        yv = None
                except Exception:
                    yv = None
                label = ln.get_label()
                color = ln.get_color()
                rows.append((label, yv, color))
                if yv is not None:
                    valid_y.append(yv)

        if not valid_y:
            self._hide_tooltip()
            return

        time_str = self._times[idx] if idx < len(self._times) else ''

        # ── 更新竖线 ────────────────────────────────────────────────────────
        if self._vline and self._vline.axes:
            self._vline.set_xdata([idx, idx])
            self._vline.set_visible(True)
        else:
            self._vline = ax.axvline(x=idx, color='gray', linestyle='--', linewidth=0.8, alpha=0.6, zorder=2)

        # ── 清除旧高亮圆点 ───────────────────────────────────────────────────
        for dot in self._dot_artists:
            try:
                dot.remove()
            except Exception:
                pass
        self._dot_artists = []

        # ── 画高亮圆点 ───────────────────────────────────────────────────────
        for label, yv, color in rows:
            if yv is not None:
                dot, = ax.plot(idx, yv, 'o', color=color, markersize=6, zorder=5)
                self._dot_artists.append(dot)

        # ── 构建 tooltip 文本 ────────────────────────────────────────────────
        # 时间行：显示完整年月日 + 时间（如 "2026-03-25 14:00"）
        time_display = _fmt_tooltip_time(time_str)
        time_lines = time_display.split('\n')
        max_time_len = max(len(l) for l in time_lines)
        lines_text = [f"  {l}  " for l in time_lines]
        lines_text.append("─" * max(max_time_len + 4, 20))
        for label, yv, color in rows:
            val_str = f"{yv:.3f}".rstrip('0').rstrip('.') if yv is not None else '—'
            lines_text.append(f"  {label}: {val_str}  ")
        text = "\n".join(lines_text)

        # ── 确定 tooltip 位置（偏右上，超出右边界则偏左） ───────────────────
        x_lim = ax.get_xlim()
        y_lim = ax.get_ylim()
        x_range = x_lim[1] - x_lim[0]
        y_range = y_lim[1] - y_lim[0]

        # tooltip 锚点在最上方有效值附近
        anchor_y = max(valid_y)

        # 偏移量（数据坐标）
        x_off = x_range * 0.015
        y_off = y_range * 0.03

        # 如果偏右会超出右边界，就偏左
        if idx + x_range * 0.35 > x_lim[1]:
            ha = 'right'
            x_off = -x_off
        else:
            ha = 'left'

        # ── 更新或创建 annotate ──────────────────────────────────────────────
        if self._annot and self._annot.axes:
            self._annot.set_text(text)
            self._annot.set_position((idx + x_off, anchor_y + y_off))
            self._annot.set_ha(ha)
            self._annot.set_visible(True)
        else:
            self._annot = ax.annotate(
                text,
                xy=(idx, anchor_y),
                xytext=(idx + x_off, anchor_y + y_off),
                ha=ha,
                va='bottom',
                fontsize=8,
                bbox=dict(
                    boxstyle='round,pad=0.4',
                    facecolor='#FFFDE7',   # 淡黄底色
                    edgecolor='#BDBDBD',
                    alpha=0.92,
                    linewidth=0.8,
                ),
                zorder=10,
            )

        self.draw_idle()


class ChartWidget(QWidget):
    """图表组件（使用 Matplotlib，支持交互式图例和鼠标悬停）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(5)

        # 创建复选框区域（用于控制曲线显示）
        self._checkbox_frame = QFrame()
        self._checkbox_layout = QHBoxLayout(self._checkbox_frame)
        self._checkbox_layout.setContentsMargins(5, 2, 5, 2)
        self._checkbox_layout.setSpacing(10)
        self._checkbox_layout.setAlignment(Qt.AlignLeft)

        # 使用滚动区域容纳复选框
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setMaximumHeight(40)
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setWidget(self._checkbox_frame)

        self._main_layout.addWidget(self._scroll_area)

        # 创建 matplotlib 图形
        self.figure = Figure(figsize=(8, 4), dpi=100)
        self.canvas = HoverFigureCanvas(self.figure)
        self._main_layout.addWidget(self.canvas)

        # 存储当前数据
        self._current_times = []
        self._current_series_list = []
        self._current_title = ""
        self._lines = {}      # 存储线条对象
        self._checkboxes = {} # 存储复选框对象

    def plot_series(self, times, series_list, title="数据曲线"):
        """绘制多条曲线，默认都不显示，通过复选框控制"""
        # 保存当前数据
        self._current_times = times
        self._current_series_list = series_list
        self._current_title = title

        # 清空之前的图形和复选框
        self.figure.clear()
        self._lines = {}

        # 清除旧复选框
        for checkbox in self._checkboxes.values():
            checkbox.deleteLater()
        self._checkboxes = {}

        # 清除旧复选框布局中的弹性空间
        while self._checkbox_layout.count():
            item = self._checkbox_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 创建子图
        ax = self.figure.add_subplot(111)

        # ── 绘制曲线（默认不可见） ────────────────────────────────────────────
        colors = plt.cm.tab10.colors
        x_indices = list(range(len(times)))

        for i, series in enumerate(series_list):
            color = colors[i % len(colors)]
            line, = ax.plot(
                x_indices,
                series['data'],
                marker='o',
                markersize=3,
                linewidth=1.8,
                label=series['name'],
                color=color,
                visible=False,
            )
            self._lines[series['name']] = line

            # 创建对应复选框
            checkbox = QCheckBox(series['name'])
            checkbox.setChecked(False)
            r, g, b = int(color[0]*255), int(color[1]*255), int(color[2]*255)
            checkbox.setStyleSheet(f"""
                QCheckBox {{
                    color: rgb({r}, {g}, {b});
                    font-weight: bold;
                    font-size: 12px;
                }}
                QCheckBox::indicator {{
                    width: 14px;
                    height: 14px;
                }}
            """)
            checkbox.stateChanged.connect(
                lambda state, name=series['name']: self._toggle_line(name, state)
            )
            self._checkboxes[series['name']] = checkbox
            self._checkbox_layout.addWidget(checkbox)

        self._checkbox_layout.addStretch()

        # ── X 轴时间标签（英文缩写，节省空间） ───────────────────────────────
        num_points = len(times)
        if num_points == 0:
            pass
        elif num_points <= 12:
            ax.set_xticks(x_indices)
            ax.set_xticklabels([_fmt_time_label(t) for t in times],
                               rotation=0, ha='center', fontsize=8)
        else:
            max_labels = 12
            step = max(1, num_points // max_labels)
            tick_idx = list(range(0, num_points, step))
            tick_labels = [_fmt_time_label(times[i]) for i in tick_idx]
            ax.set_xticks(tick_idx)
            ax.set_xticklabels(tick_labels, rotation=0, ha='center', fontsize=8)

        # ── 图表装饰 ──────────────────────────────────────────────────────────
        ax.set_title(title, fontsize=11, fontweight='bold', pad=8)
        ax.set_ylabel("数值", fontsize=9)
        ax.grid(True, alpha=0.25, linestyle='--')
        ax.tick_params(axis='y', labelsize=8)

        # 预留底部空间给双行时间标签
        self.figure.subplots_adjust(bottom=0.18, left=0.08, right=0.97, top=0.90)

        # ── 绑定悬停 ─────────────────────────────────────────────────────────
        self.canvas.set_hover_data(times)
        self.canvas.setup_hover()

        self.canvas.draw()

    def _toggle_line(self, series_name, state):
        """切换线条显示/隐藏"""
        if series_name in self._lines:
            self._lines[series_name].set_visible(state == Qt.Checked)
            self._auto_scale()
            self.canvas.draw()

    def _auto_scale(self):
        """自动调整 Y 轴范围"""
        ax = self.figure.axes[0] if self.figure.axes else None
        if not ax:
            return

        visible_lines = [ln for ln in self._lines.values() if ln.get_visible()]
        if not visible_lines:
            ax.set_ylim(0, 1)
            self.canvas.draw()
            return

        all_y = []
        for ln in visible_lines:
            for y in ln.get_ydata():
                if y is not None:
                    try:
                        if y == y:  # not nan
                            all_y.append(y)
                    except Exception:
                        pass

        if all_y:
            y_min, y_max = min(all_y), max(all_y)
            margin = (y_max - y_min) * 0.12 if y_max != y_min else 1
            ax.set_ylim(y_min - margin, y_max + margin)

        self.canvas.draw()

    def clear(self):
        """清空图表"""
        self._current_times = []
        self._current_series_list = []
        self._current_title = ""
        self._lines = {}

        for checkbox in self._checkboxes.values():
            checkbox.deleteLater()
        self._checkboxes = {}

        while self._checkbox_layout.count():
            item = self._checkbox_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.text(0.5, 0.5, '暂无数据',
                horizontalalignment='center',
                verticalalignment='center',
                transform=ax.transAxes,
                fontsize=12, color='gray')
        ax.set_xticks([])
        ax.set_yticks([])
        self.canvas.draw()
