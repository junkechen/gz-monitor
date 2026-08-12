# -*- coding: utf-8 -*-
"""
首次启动教学引导（产品巡览 / onboarding tour）。

实现方式：全屏半透明遮罩 + 聚光灯挖洞（露出目标控件）+ 脉冲边框高亮 +
底部浮层卡片，分步讲解核心功能。

设计要点：
- 不修改任何目标控件的样式表（避免破坏既有暗色主题），遮罩与高亮全部自绘。
- 遮罩为 MainWindow 的子 QWidget，覆盖整个主窗口；聚光灯区域用
  CompositionMode_Clear 擦除为透明，露出下层真实控件。
- 卡片为浮层子控件，含「上一步 / 跳过 / 下一步」与步骤计数。
- 支持键盘：Esc 跳过，Enter/Space 下一步。
- 监听 MainWindow 的 resize/move，自动重算遮罩与卡片位置。
"""
import math

from PyQt5.QtCore import Qt, QPoint, QRect, QRectF, QTimer, QEvent, pyqtSignal
from PyQt5.QtGui import QPainter, QPainterPath, QColor, QBrush, QPen
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QFrame, QVBoxLayout, QHBoxLayout,
)

try:
    from config import COLORS
except Exception:  # 容错：脱离 src 包独立运行时
    COLORS = {}


def _c(key, fallback):
    """取主题色，缺失时回退到硬编码色。"""
    v = COLORS.get(key) if COLORS else None
    return v if v else fallback


# ── 按钮样式 ────────────────────────────────────────────────────────────────
_BTN_STYLE = f"""
    QPushButton {{
        background: {_c('bg_input', '#21262d')};
        color: {_c('text_primary', '#e6edf3')};
        border: 1px solid {_c('border', '#30363d')};
        border-radius: 6px;
        font-size: 12.5px;
        padding: 0 14px;
    }}
    QPushButton:hover {{ background: {_c('secondary', '#30363d')}; }}
    QPushButton:disabled {{ color: #6e7681; background: #161b22; }}
"""
_BTN_STYLE_NEXT = f"""
    QPushButton {{
        background: {_c('primary', '#1f6feb')};
        color: white;
        border: none;
        border-radius: 6px;
        font-size: 12.5px;
        font-weight: bold;
        padding: 0 16px;
    }}
    QPushButton:hover {{ background: #388bfd; }}
"""

# 聚光灯脉冲主色（蓝）
_HL_COLOR = (88, 166, 255)


class TourGuide(QWidget):
    """教学引导遮罩。finish 时发出 finished 信号。"""

    finished = pyqtSignal()

    def __init__(self, parent_window, steps):
        # 关键修复：必须是顶层窗口（无 parent），WA_TranslucentBackground 才生效。
        # 之前作为 MainWindow 的子 widget 设置该属性，在 Win7 上整控件透明不可见。
        super().__init__()
        self._win = parent_window
        self._steps = list(steps) if steps else []
        self._idx = -1
        self._hole = QRect()
        self._pulse = 0.0
        self._phase = 0.0

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._build_card()
        if self._win is not None:
            self._win.installEventFilter(self)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    # ── 构建浮层卡片 ──────────────────────────────────────────────────────
    def _build_card(self):
        self._card = QFrame(self)
        self._card.setObjectName("tour_card")
        self._card.setFixedWidth(340)
        self._card.setStyleSheet(f"""
            QFrame#tour_card {{
                background: {_c('bg_card', '#161b22')};
                border: 1px solid {_c('primary', '#1f6feb')};
                border-radius: 10px;
                padding: 14px;
            }}
        """)

        title = QLabel("", self._card)
        title.setObjectName("tour_title")
        title.setStyleSheet("color:#e6edf3;font-size:15px;font-weight:bold;")

        body = QLabel("", self._card)
        body.setObjectName("tour_body")
        body.setWordWrap(True)
        body.setStyleSheet("color:#c9d1d9;font-size:12.5px;line-height:1.5;")

        counter = QLabel("", self._card)
        counter.setObjectName("tour_counter")
        counter.setStyleSheet("color:#8b949e;font-size:11px;")

        btn_prev = QPushButton("上一步")
        btn_skip = QPushButton("跳过")
        btn_next = QPushButton("下一步")
        for b in (btn_prev, btn_skip, btn_next):
            b.setFixedHeight(30)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_prev.setObjectName("tour_prev")
        btn_skip.setObjectName("tour_skip")
        btn_next.setObjectName("tour_next")
        btn_prev.setStyleSheet(_BTN_STYLE)
        btn_skip.setStyleSheet(_BTN_STYLE)
        btn_next.setStyleSheet(_BTN_STYLE_NEXT)
        btn_prev.clicked.connect(self._prev)
        btn_skip.clicked.connect(self._finish)
        btn_next.clicked.connect(self._next)

        v = QVBoxLayout(self._card)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addWidget(title)
        v.addWidget(body)
        v.addWidget(counter)

        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        h.addWidget(btn_prev)
        h.addStretch(1)
        h.addWidget(btn_skip)
        h.addWidget(btn_next)
        v.addLayout(h)

        self._title = title
        self._body = body
        self._counter = counter
        self._btn_prev = btn_prev
        self._btn_next = btn_next

    # ── 控制接口 ──────────────────────────────────────────────────────────
    def start(self):
        """启动引导（覆盖主窗口、定位到第 0 步）。"""
        self._follow_window()
        self.show()
        self.raise_()
        self.activateWindow()
        self._goto(0)

    def _goto(self, idx):
        if idx < 0:
            idx = 0
        if idx >= len(self._steps):
            self._finish()
            return
        self._idx = idx
        step = self._steps[idx]

        pre = step.get("pre")
        if callable(pre):
            try:
                pre()
            except Exception:
                pass

        self._title.setText(step.get("title", ""))
        self._body.setText(step.get("text", ""))
        total = len(self._steps)
        self._counter.setText(f"第 {idx + 1} / {total} 步")
        self._btn_prev.setEnabled(idx > 0)
        self._btn_next.setText("完成 ✅" if idx == total - 1 else "下一步")

        self._recompute_hole()
        self.raise_()
        self._card.raise_()
        self.update()

    def _next(self):
        if self._idx >= len(self._steps) - 1:
            self._finish()
        else:
            self._goto(self._idx + 1)

    def _prev(self):
        if self._idx > 0:
            self._goto(self._idx - 1)

    def _finish(self):
        try:
            self._timer.stop()
        except Exception:
            pass
        self.hide()
        self.finished.emit()

    # ── 几何计算 ──────────────────────────────────────────────────────────
    def _follow_window(self):
        """把遮罩对齐到主窗口在屏幕上的几何区域（含标题栏，基准与 mapToGlobal 一致）。"""
        if self._win is None:
            return
        self.setGeometry(self._win.frameGeometry())

    def _recompute_hole(self):
        """根据当前步骤目标控件，计算聚光灯矩形（屏幕坐标 → 遮罩坐标）。"""
        self._hole = QRect()
        if 0 <= self._idx < len(self._steps):
            target = self._steps[self._idx].get("target")
            if target is not None and hasattr(target, "mapToGlobal") and hasattr(target, "size"):
                try:
                    # 控件全局坐标 - 遮罩全局原点 = 相对遮罩坐标
                    top_left = target.mapToGlobal(QPoint(0, 0)) - self.geometry().topLeft()
                    self._hole = QRect(top_left, target.size()).adjusted(-8, -8, 8, 8)
                except Exception:
                    self._hole = QRect()
        self._place_card()

    def _place_card(self):
        w = self.width()
        h = self.height()
        cw = self._card.width()
        ch = self._card.height()
        if self._hole.isNull():
            x = max(8, (w - cw) // 2)
            y = h - ch - 24
        else:
            x = self._hole.center().x() - cw // 2
            if self._hole.bottom() + ch + 16 < h:
                y = self._hole.bottom() + 16
            else:
                y = max(8, self._hole.top() - ch - 16)
            x = max(8, min(x, w - cw - 8))
            y = max(8, min(y, h - ch - 8))
        self._card.setGeometry(x, y, cw, ch)
        self._card.show()
        self._card.raise_()

    def _tick(self):
        self._phase += 0.12
        self._pulse = (math.sin(self._phase) + 1) / 2.0
        if not self._hole.isNull():
            self.update()

    # ── 事件 ──────────────────────────────────────────────────────────────
    def eventFilter(self, obj, event):
        if obj is self._win and event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self._follow_window()
            self._recompute_hole()
            self.update()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._finish()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._next()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            # 半透明暗色遮罩
            painter.fillRect(self.rect(), QColor(10, 13, 18, 180))
            if self._hole.isNull():
                return

            # 挖洞：CompositionMode_Clear 把该区域擦成透明，露出下层真实控件
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            path = QPainterPath()
            path.addRoundedRect(QRectF(self._hole), 10, 10)
            painter.setBrush(QBrush(QColor(0, 0, 0, 255)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.fillPath(path, painter.brush())

            # 脉冲边框（在洞外扩一圈，营造高亮呼吸效果）
            painter.setCompositionMode(QPainter.CompositionMode.SourceOver)
            pad = 3 + int(7 * self._pulse)
            alpha = int(150 + 105 * (1 - self._pulse))
            r, g, b = _HL_COLOR
            color = QColor(r, g, b, alpha)
            pen = QPen(color, 3 + int(2 * self._pulse))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            ring = self._hole.adjusted(-pad, -pad, pad, pad)
            path2 = QPainterPath()
            path2.addRoundedRect(QRectF(ring), 12, 12)
            painter.drawPath(path2)
            painter.end()
        except Exception:  # 防御：绘制异常不应导致程序崩溃
            pass


# ── 默认引导步骤 ────────────────────────────────────────────────────────────
def build_default_steps(mw):
    """构造默认 8 步引导（基于 MainWindow 实例 mw 的控件引用）。

    步骤覆盖核心闭环：排放口选择 → 实时数据 → 进入预测页 → 开始预测 →
    结果表 → 对比参数 → 归一化 → 对比模式。
    pre 动作负责切换页签，确保目标控件可见。
    """
    return [
        {
            "target": mw.sub_list,
            "title": "① 排放口列表",
            "text": "左侧是各企业排放口列表。选中任意一个排放口，右侧会显示其实时监测数据。",
        },
        {
            "target": mw.realtime_table,
            "title": "② 实时监测数据",
            "text": "这里实时展示选中排放口各项污染因子的当前数值、达标状态与预警等级。",
            "pre": lambda: mw.right_panel.setCurrentWidget(mw.realtime_tab),
        },
        {
            "target": mw.right_panel.tabBar(),
            "title": "③ 切换功能页签",
            "text": "顶部页签可在 实时监控 / 历史数据 / 数据预测 / 系统设置 间切换。\n接下来我们进入【数据预测】。",
            "pre": lambda: mw.right_panel.setCurrentWidget(mw.prediction_tab),
        },
        {
            "target": mw.pred_btn,
            "title": "④ 开始预测",
            "text": "点击「🚀 开始预测」即可对所有排放口的各项参数发起预测分析（默认自动更新）。",
        },
        {
            "target": mw.pred_table,
            "title": "⑤ 预测结果表",
            "text": "预测完成后，这里列出各排放口的预测值、趋势、置信度与超标预警状态。",
        },
        {
            "target": mw.param_picker,
            "title": "⑥ 对比参数选择器",
            "text": "左侧分类导航 + 搜索框可快速筛选指标；勾选后，下方趋势图会叠加对比这些参数曲线。",
        },
        {
            "target": mw.pred_normalize_btn,
            "title": "⑦ 归一化开关",
            "text": "不同指标量级差异大时，打开「归一化」可把各曲线缩放到 0–1，方便对比走势形状。",
        },
        {
            "target": mw.pred_mode_combo,
            "title": "⑧ 对比模式",
            "text": "可切换「同排口多参数」（看一个排口多个指标）或「同参数多排口」（看一个指标跨排口对比）。\n\n到这里基础操作就介绍完啦，祝使用愉快！",
        },
    ]
