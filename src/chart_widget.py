# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 图表组件
使用 matplotlib 替代 WebEngine，Windows 7 兼容
支持点击图例隐藏/显示曲线，默认都不选中
支持鼠标悬停显示数值（精准 annotate + 竖线跟踪）
支持双 Y 轴（twinx）与归一化（三项优化 T01）
"""

import os
import re
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QScrollArea, QFrame, QLabel
from PyQt5.QtCore import Qt, QPoint

from config import FIG_DPI

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


def _normalize_series(data):
    """把一条 series 的数据做各自 min-max 映射到 [0,1]（None 保持不变）。"""
    vals = [v for v in data if v is not None]
    if not vals:
        return list(data)
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return [0.0 if v is not None else None for v in data]
    return [(v - lo) / (hi - lo) if v is not None else None for v in data]


class HoverFigureCanvas(FigureCanvasQTAgg):
    """支持鼠标悬停的 Canvas（使用 annotate + 竖线跟踪），兼容双 Y 轴。"""

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
        """返回主（左）轴，兼容双轴场景。"""
        return self.figure.axes[0] if self.figure.axes else None

    def _get_ax_list(self):
        """返回所有 axes（双轴场景含左轴与右轴）。"""
        return self.figure.axes

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
        axes = self.figure.axes
        if not axes:
            self._hide_tooltip()
            return

        # 找到鼠标所在的轴（任一轴均可）
        cur_ax = None
        for a in axes:
            if event.inaxes == a:
                cur_ax = a
                break
        if cur_ax is None:
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

        # 聚合所有 axes 上的可见线条（跨双轴）
        visible_lines = []
        for a in axes:
            visible_lines.extend([
                ln for ln in a.lines
                if ln.get_visible() and not ln.get_label().startswith('_')
            ])
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

        # ── 更新竖线（画在主轴上，双轴共享 X，视觉贯穿全图） ───────────────
        if self._vline and self._vline.axes:
            self._vline.set_xdata([idx, idx])
            self._vline.set_visible(True)
        else:
            self._vline = axes[0].axvline(x=idx, color='gray', linestyle='--',
                                          linewidth=0.8, alpha=0.6, zorder=2)

        # ── 清除旧高亮圆点 ───────────────────────────────────────────────────
        for dot in self._dot_artists:
            try:
                dot.remove()
            except Exception:
                pass
        self._dot_artists = []

        # ── 画高亮圆点（落在各自所属轴上，保证位置正确） ───────────────────
        for k, (label, yv, color) in enumerate(rows):
            if yv is not None:
                owner = getattr(visible_lines[k], '_owner_ax', axes[0])
                dot, = owner.plot(idx, yv, 'o', color=color, markersize=6, zorder=5)
                self._dot_artists.append(dot)

        # ── 构建 tooltip 文本 ────────────────────────────────────────────────
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
        ax = axes[0]
        x_lim = ax.get_xlim()
        y_lim = ax.get_ylim()
        x_range = x_lim[1] - x_lim[0]
        y_range = y_lim[1] - y_lim[0]

        # tooltip 锚点：优先用左轴可见线的最高值，避免双轴量纲不一致导致错位
        left_visible = [
            ln for ln in ax.lines
            if ln.get_visible() and not ln.get_label().startswith('_')
        ]
        left_y = [ln.get_ydata()[idx] for ln in left_visible
                  if idx < len(ln.get_ydata())
                  and ln.get_ydata()[idx] is not None
                  and ln.get_ydata()[idx] == ln.get_ydata()[idx]]
        anchor_y = max(left_y) if left_y else y_lim[1]

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
    """图表组件（使用 Matplotlib，支持交互式图例和鼠标悬停，支持双 Y 轴/归一化）。"""

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

        # 创建 matplotlib 图形（T01：dpi=FIG_DPI，figsize 略缩以降低资源占用）
        self.figure = Figure(figsize=(7.6, 3.8), dpi=FIG_DPI)
        self.canvas = HoverFigureCanvas(self.figure)
        self._main_layout.addWidget(self.canvas)

        # 存储当前数据
        self._current_times = []
        self._current_series_list = []
        self._current_title = ""
        self._lines = {}          # 左轴线条对象
        self._checkboxes = {}     # 左轴复选框对象
        self._right_lines = {}    # 右轴线条对象（twinx）
        self._right_checkboxes = {}  # 右轴复选框对象
        self._normalize_active = False  # 是否处于归一化模式

    def _make_checkbox(self, name, color):
        """创建一条曲线的彩色 QCheckBox 并连接显隐信号。"""
        checkbox = QCheckBox(name)
        checkbox.setChecked(False)
        r, g, b = int(color[0] * 255), int(color[1] * 255), int(color[2] * 255)
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
            lambda state, nm=name: self._toggle_line(nm, state)
        )
        return checkbox

    def plot_series(self, times, series_list, title="数据曲线",
                    right_series_list=None, right_ylabel="", normalize=False):
        """绘制多条曲线，默认都不显示，通过复选框控制。

        Args:
            times: 公共 X 轴时间标签列表。
            series_list: 左轴 series 列表，元素 ``{name, data, times?}``。
            title: 图表标题。
            right_series_list: 右轴(twinx) series 列表，元素同 series_list；
                默认 None 表示单轴。
            right_ylabel: 右轴 Y 轴标题。
            normalize: True 时所有 series 各自 min-max 映射到 [0,1]，强制单轴
                （忽略右轴）。默认 False（双轴/单轴按 right_series_list 决定）。
        """
        normalize = bool(normalize)
        right_list = list(right_series_list) if right_series_list else []

        # 保存当前数据
        self._current_times = times
        self._current_series_list = series_list
        self._current_title = title
        self._normalize_active = normalize

        # 清空之前的图形和复选框
        self.figure.clear()
        self._lines = {}
        self._right_lines = {}

        # 清除旧复选框
        for checkbox in list(self._checkboxes.values()) + list(self._right_checkboxes.values()):
            checkbox.deleteLater()
        self._checkboxes = {}
        self._right_checkboxes = {}

        while self._checkbox_layout.count():
            item = self._checkbox_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 创建子图（主轴）
        ax = self.figure.add_subplot(111)
        colors = plt.cm.tab10.colors

        # 归一化模式：所有 series 合并到单轴并各自缩放到 [0,1]
        if normalize:
            all_series = list(series_list or []) + right_list
            for i, series in enumerate(all_series):
                color = colors[i % len(colors)]
                ndata = _normalize_series(series.get('data', []))
                line, = ax.plot(
                    list(range(len(times))),
                    ndata,
                    marker='o',
                    markersize=3,
                    linewidth=1.8,
                    label=series['name'],
                    color=color,
                    visible=False,
                )
                line._owner_ax = ax
                self._lines[series['name']] = line

                checkbox = self._make_checkbox(series['name'], color)
                self._checkboxes[series['name']] = checkbox
                self._checkbox_layout.addWidget(checkbox)

            ax.set_ylabel("归一化数值 (0-1)", fontsize=9)
        else:
            # 左轴 series
            for i, series in enumerate(series_list or []):
                color = colors[i % len(colors)]
                line, = ax.plot(
                    list(range(len(times))),
                    series.get('data', []),
                    marker='o',
                    markersize=3,
                    linewidth=1.8,
                    label=series['name'],
                    color=color,
                    visible=False,
                )
                line._owner_ax = ax
                self._lines[series['name']] = line

                checkbox = self._make_checkbox(series['name'], color)
                self._checkboxes[series['name']] = checkbox
                self._checkbox_layout.addWidget(checkbox)

            # 右轴 series（twinx）
            ax2 = None
            if right_list:
                ax2 = ax.twinx()
                for i, series in enumerate(right_list):
                    color = colors[(len(series_list or []) + i) % len(colors)]
                    line, = ax2.plot(
                        list(range(len(times))),
                        series.get('data', []),
                        marker='s',
                        markersize=3,
                        linewidth=1.8,
                        label=series['name'],
                        color=color,
                        visible=False,
                    )
                    line._owner_ax = ax2
                    self._right_lines[series['name']] = line

                    checkbox = self._make_checkbox(series['name'], color)
                    self._right_checkboxes[series['name']] = checkbox
                    self._checkbox_layout.addWidget(checkbox)
                ax2.set_ylabel(right_ylabel or "右轴", fontsize=9)

        self._checkbox_layout.addStretch()

        # ── X 轴时间标签（英文缩写，节省空间） ───────────────────────────────
        num_points = len(times)
        if num_points == 0:
            pass
        elif num_points <= 12:
            ax.set_xticks(list(range(num_points)))
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
        if not normalize:
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
        """切换线条显示/隐藏（兼容双轴）。"""
        target = None
        if series_name in self._lines:
            target = self._lines[series_name]
        elif series_name in self._right_lines:
            target = self._right_lines[series_name]

        if target is not None:
            target.set_visible(state == Qt.Checked)
            self._auto_scale()
            self.canvas.draw()

    def _auto_scale(self):
        """自动调整 Y 轴范围（兼容双轴与归一化）。"""
        axes = self.figure.axes
        if not axes:
            return
        ax = axes[0]

        # 归一化模式：固定 0-1，跳过缩放
        norm_mode = bool(getattr(self, '_normalize_active', False))

        # 左轴缩放
        visible_left = [ln for ln in self._lines.values() if ln.get_visible()]
        if visible_left and not norm_mode:
            all_y = self._collect_y(visible_left)
            if all_y:
                y_min, y_max = min(all_y), max(all_y)
                margin = (y_max - y_min) * 0.12 if y_max != y_min else 1
                ax.set_ylim(y_min - margin, y_max + margin)
            else:
                ax.set_ylim(0, 1)
        else:
            ax.set_ylim(0, 1)

        # 右轴缩放
        if len(axes) > 1:
            ax2 = axes[1]
            visible_right = [ln for ln in self._right_lines.values() if ln.get_visible()]
            if visible_right and not norm_mode:
                all_y = self._collect_y(visible_right)
                if all_y:
                    y_min, y_max = min(all_y), max(all_y)
                    margin = (y_max - y_min) * 0.12 if y_max != y_min else 1
                    ax2.set_ylim(y_min - margin, y_max + margin)
                else:
                    ax2.set_ylim(0, 1)
            else:
                ax2.set_ylim(0, 1)

        self.canvas.draw()

    @staticmethod
    def _collect_y(lines):
        all_y = []
        for ln in lines:
            for y in ln.get_ydata():
                if y is not None:
                    try:
                        if y == y:  # not nan
                            all_y.append(y)
                    except Exception:
                        pass
        return all_y

    def clear(self):
        """清空图表"""
        self._current_times = []
        self._current_series_list = []
        self._current_title = ""
        self._lines = {}
        self._right_lines = {}

        for checkbox in list(self._checkboxes.values()) + list(self._right_checkboxes.values()):
            checkbox.deleteLater()
        self._checkboxes = {}
        self._right_checkboxes = {}

        while self._checkbox_layout.count():
            item = self._checkbox_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        self._normalize_active = False
        ax.text(0.5, 0.5, '暂无数据',
                horizontalalignment='center',
                verticalalignment='center',
                transform=ax.transAxes,
                fontsize=12, color='gray')
        ax.set_xticks([])
        ax.set_yticks([])
        self.canvas.draw()
