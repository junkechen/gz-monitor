# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 手动滑块验证对话框（兜底方案）

定位
----
正常情况下 **不需要** 人工拖动：``slider_solver.solve_trail()`` 通过 NCC
归一化互相关自动定位拼图缺口，实测连续 8 轮 Top-1 全部命中。

本对话框仅作为**兜底**：当自动求解失败（例如服务端更换了缺口渲染方式、
图片被重度压缩导致 NCC 失效）时，把滑块图片展示给用户，由用户用真实
鼠标拖动，从而产生服务端难以区分于人类的拖动轨迹。

跨线程约束（重要）
------------------
``login()`` 运行在 ``LoginWorker``(QThread) 后台线程中，Qt 控件**禁止**
在非 GUI 线程创建或显示。因此本模块的所有 Qt 代码都只允许在 GUI 主线程
调用，调用方通过 ``GZApiClient.login(..., trail_provider=...)`` 注入一个
「主线程弹窗 + 返回结果」的回调，线程桥接由 ``src/main.py`` 的
``LoginWorker`` 用 Qt 信号实现（本模块不感知线程，只负责弹窗与取值）。

坐标换算
--------
背景图原始尺寸 300x150，本对话框按 ``DISPLAY_SCALE``(=2) 放大到 600x300
显示，用户拖动的位移 ``dx_display`` 需换算回原始坐标系：

    trail = dx_display / DISPLAY_SCALE
"""

import random

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from slider_solver import (
    BG_HEIGHT,
    BG_WIDTH,
    SLIDER_HEIGHT,
    decode_data_url,
    fetch_slider_images,
)

# 显示放大倍数：背景 300x150 -> 600x300，便于鼠标精确拖动
DISPLAY_SCALE = 2

# 滑块按钮边长（显示像素）
HANDLE_SIZE = 50

# 位移小于该值（原始坐标系）视为误点
MIN_TRAIL = 5

# y 方向轻微抖动范围（显示像素），让轨迹更接近真实人手
JITTER_Y = 8


class SliderDialog(QDialog):
    """
    手动滑块验证对话框。

    必须在 GUI 主线程创建并通过 ``exec_()`` 显示。
    用户松手后若位移有效，``accept()`` 并记录 ``self.trail``；
    取消则 ``reject()``，``get_trail()`` 返回 None。
    """

    def __init__(self, background_data=None, slider_data=None,
                 background_pil=None, slider_pil=None, account_name="", parent=None):
        """
        Args:
            background_data: background 的 data URL 字符串（可选）
            slider_data: slider 的 data URL 字符串（可选）
            background_pil: 已解码的背景 PIL Image（可选，优先于 data URL）
            slider_pil: 已解码的滑块 PIL Image（可选，优先于 data URL）
            account_name: 当前正在登录的企业名，仅用于界面提示
            parent: 父窗口
        """
        super().__init__(parent)
        self._account_name = account_name or ""

        self.trail = None
        self._dragging = False
        self._press_offset = None  # 按下时鼠标相对按钮左边缘的偏移
        self._display_dx = 0       # 当前显示坐标系下的总位移

        # 解码图片：优先使用 PIL 对象，避免重复 base64 解码
        bg_pil = background_pil if background_pil is not None else decode_data_url(background_data)
        sl_pil = slider_pil if slider_pil is not None else decode_data_url(slider_data)

        self._bg_pil = bg_pil
        self._sl_pil = sl_pil

        self._display_w = BG_WIDTH * DISPLAY_SCALE
        self._display_h = BG_HEIGHT * DISPLAY_SCALE

        self.setWindowTitle("滑块验证")
        self.setModal(True)
        self.setFixedWidth(self._display_w + 40)
        self._build_ui()
        self._apply_images(bg_pil, sl_pil)

    # ── UI 构建 ──────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        if self._account_name:
            tip = QLabel("请完成滑块验证：%s" % self._account_name)
            tip.setStyleSheet("color: #1a6b3c; font-weight: bold;")
            layout.addWidget(tip)

        # 背景图容器：滑块按钮作为其子控件叠加在背景之上
        self._bg_label = QLabel(self)
        self._bg_label.setFixedSize(self._display_w, self._display_h)
        self._bg_label.setStyleSheet(
            "border:1px solid #cccccc; background:#f0f0f0;")
        self._bg_label.setScaledContents(False)
        layout.addWidget(self._bg_label)

        # 滑块按钮（可拖动）
        self._handle = QLabel(self._bg_label)
        self._handle.setFixedSize(HANDLE_SIZE, HANDLE_SIZE)
        self._handle.setAlignment(Qt.AlignCenter)
        self._handle.setText("→")
        self._handle.setStyleSheet(
            "background:#2d9e60; color:#ffffff; border:1px solid #1a6b3c;"
            "font-size:20px; font-weight:bold;")
        self._handle.setCursor(Qt.OpenHandCursor)
        self._handle.mousePressEvent = self._on_press
        self._handle.mouseMoveEvent = self._on_move
        self._handle.mouseReleaseEvent = self._on_release
        # 拖出按钮范围后仍要继续接收事件
        self._handle.setMouseTracking(True)
        self._handle.move(0, (self._display_h - HANDLE_SIZE) // 2)

        hint = QLabel("按住滑块拖动到缺口位置后松手")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #555555;")
        layout.addWidget(hint)

        # 实时反馈当前偏移量
        self._value_label = QLabel("当前偏移：0")
        self._value_label.setAlignment(Qt.AlignCenter)
        self._value_label.setStyleSheet("color: #888888; font-size:12px;")
        layout.addWidget(self._value_label)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _apply_images(self, bg_pil, sl_pil):
        """把 PIL 图片渲染到控件上"""
        bg_pm = QPixmap.fromImage(self._pil_to_qimage(bg_pil)).scaled(
            self._display_w, self._display_h)
        self._bg_label.setPixmap(bg_pm)

        # 滑块按钮内部显示拼图块缩略图，作为视觉提示
        sl_pm = QPixmap.fromImage(self._pil_to_qimage(sl_pil)).scaled(
            HANDLE_SIZE - 4, HANDLE_SIZE - 4)
        self._handle.setPixmap(sl_pm)

    @staticmethod
    def _pil_to_qimage(pil_image):
        """PIL Image -> QImage（避免额外依赖 qtpy/PIL-Qt 桥接）"""
        from PyQt5.QtGui import QImage

        rgb = pil_image.convert("RGB")
        data = rgb.tobytes("raw", "RGB")
        return QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format_RGB888)

    # ── 鼠标交互 ──────────────────────────────────────────────────────────
    def _on_press(self, event):
        """记录按下位置与鼠标相对按钮的偏移"""
        if event.button() != Qt.LeftButton:
            return
        self._dragging = True
        self._press_offset = event.pos().x()
        self._display_dx = self._handle.x()
        self._handle.setCursor(Qt.ClosedHandCursor)

    def _on_move(self, event):
        """水平移动按钮，y 方向给轻微随机抖动"""
        if not self._dragging:
            return

        parent_left = self._bg_label.x()
        # 鼠标在父容器坐标系中的横坐标
        mouse_x = event.pos().x() + self._handle.x() - self._press_offset
        new_x = mouse_x - parent_left

        max_x = self._display_w - HANDLE_SIZE
        new_x = max(0, min(max_x, new_x))
        self._display_dx = new_x

        base_y = (self._display_h - HANDLE_SIZE) // 2
        jitter = random.randint(-JITTER_Y, JITTER_Y) if JITTER_Y else 0
        self._handle.move(new_x, max(0, base_y + jitter))

        self._value_label.setText("当前偏移：%d" % self.current_trail())

    def _on_release(self, event):
        """松手：换算回原始坐标系并校验"""
        if not self._dragging:
            return
        self._dragging = False
        self._handle.setCursor(Qt.OpenHandCursor)

        trail = self.current_trail()
        if trail < MIN_TRAIL:
            # 误点：提示重试，不接受本次结果
            self.trail = None
            self._handle.move(0, (self._display_h - HANDLE_SIZE) // 2)
            self._value_label.setText("位移过小，请重新拖动（当前偏移：%d）" % trail)
            return

        self.trail = trail
        self.accept()

    # ── 对外接口 ──────────────────────────────────────────────────────────
    def current_trail(self):
        """当前显示位移换算回原始 300px 坐标系的偏移量（int，未截断）"""
        return int(self._display_dx / DISPLAY_SCALE)

    def get_trail(self):
        """
        返回用户拖动得到的偏移量（原始背景坐标系）。

        Returns:
            int —— 有效位移；None —— 用户取消或位移过小
        """
        return self.trail

    @staticmethod
    def fetch_image(session):
        """
        拉取滑块图片（静态方法，复用调用方的 Session 以保留 Cookie）。

        Args:
            session: requests.Session 实例

        Returns:
            (background_pil, slider_pil)
        """
        return fetch_slider_images(session)


# 模块级便捷别名，便于外部按名称引用尺寸常量
__all__ = [
    "SliderDialog",
    "DISPLAY_SCALE",
    "HANDLE_SIZE",
    "MIN_TRAIL",
    "BG_WIDTH",
    "BG_HEIGHT",
    "SLIDER_HEIGHT",
]
