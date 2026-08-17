# -*- coding: utf-8 -*-
"""
v5.25 预测页面优化：下拉式多选"对比参数"选择器

设计目标（来源：用户反馈"原双栏分类 + 搜索 + 内部分割条太复杂"）
1. 主面板只保留一个按钮「对比参数 (N) ▾」，平时只占一行，最大化趋势图空间
2. 点击按钮弹出浮层，内含：顶部搜索、按废气/废水分组的勾选列表、底部全选/清空
3. 浮层关闭后状态保留，勾选变化通过 selected_changed(list[str]) 信号通知下游
4. 公共 API（set_available_params / get_selected / set_selected / select_all /
   invert / clear_selection / selected_changed）与 v5.20~v5.24 完全一致，
   因此 main_window.py 无需为本次重构改动调用契约

实现策略
- 主控件：QPushButton（toggle_btn）承载下拉
- 浮层：QWidget + Qt.Popup（点击外部/ESC 自动关闭，置顶）
- 浮层内：QLineEdit 搜索 + QScrollArea 分组勾选 + 底部操作栏
- 保留 _classify / _param_tag 便于分类与单测复用
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config import (
    COLORS,
    PARAM_CATEGORIES,
    RIGHT_AXIS_PARAMS,
)


class ParamPickerPanel(QWidget):
    """下拉式"对比参数"多选选择器。

    Signals
    -------
    selected_changed(list[str])  选中指标列表发生变化（增减）
    """

    selected_changed = pyqtSignal(list)

    # 分组顺序：key -> 中文标题（仅展示真实存在的分类）
    _GROUPS = (
        ("gas", "废气"),
        ("water", "废水"),
        ("rax", "双轴"),
        ("limbo", "其他"),
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._all_params: List[str] = []          # 当前可用指标（保序去重）
        self._selected: Set[str] = set()          # 已选指标
        self._checkboxes: Dict[str, QCheckBox] = {}  # param -> 勾选框
        self._suppress = False                    # 批量操作时阻止重复 emit
        self._build_ui()

    # ── 公开 API ─────────────────────────────────────────────────────────
    def set_available_params(self, params: Iterable[str]) -> None:
        """设置当前可用指标列表，重新构建浮层勾选项，并保留旧选中状态。"""
        seen: Set[str] = set()
        ordered: List[str] = []
        for p in params:
            if not p or p in seen:
                continue
            seen.add(p)
            ordered.append(p)
        self._all_params = ordered
        # 丢掉已不存在的选中项
        self._selected = {p for p in self._selected if p in seen}
        self._rebuild_list()
        self._refresh_labels()

    def get_selected(self) -> List[str]:
        """返回当前已选指标列表（按出现顺序）。"""
        return [p for p in self._all_params if p in self._selected]

    def set_selected(self, params: Iterable[str]) -> None:
        """外部设定已选指标（重置/导入方案），会清空现有选中。"""
        target = set(params)
        self._selected = {p for p in target if p in set(self._all_params)}
        self._suppress = True
        try:
            for p, cb in self._checkboxes.items():
                cb.setChecked(p in self._selected)
        finally:
            self._suppress = False
        self._refresh_labels()
        self.selected_changed.emit(self.get_selected())

    def selected_count(self) -> int:
        return len(self._selected)

    def total_count(self) -> int:
        return len(self._all_params)

    # ── 外部按钮驱动（main_window 的 _select_all_params 等仍调用） ──
    def select_all(self) -> None:
        self._suppress = True
        try:
            for p in self._all_params:
                self._selected.add(p)
                cb = self._checkboxes.get(p)
                if cb:
                    cb.setChecked(True)
        finally:
            self._suppress = False
        self._refresh_labels()
        self.selected_changed.emit(self.get_selected())

    def invert(self) -> None:
        self._suppress = True
        try:
            for p in self._all_params:
                new_state = p not in self._selected
                if new_state:
                    self._selected.add(p)
                else:
                    self._selected.discard(p)
                cb = self._checkboxes.get(p)
                if cb:
                    cb.setChecked(new_state)
        finally:
            self._suppress = False
        self._refresh_labels()
        self.selected_changed.emit(self.get_selected())

    def clear_selection(self) -> None:
        self._suppress = True
        try:
            for cb in self._checkboxes.values():
                cb.setChecked(False)
        finally:
            self._suppress = False
        self._selected.clear()
        self._refresh_labels()
        self.selected_changed.emit(self.get_selected())

    # ── UI 构建 ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self.toggle_btn = QPushButton("对比参数 (0)")
        self.toggle_btn.setMinimumHeight(30)
        self.toggle_btn.setStyleSheet(self._btn_style())
        self.toggle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toggle_btn.clicked.connect(self._toggle_popup)
        root.addWidget(self.toggle_btn, 1)

        # 整体 size policy 让 panel 可被外层 splitter 压高/拉高
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(40)

        self._build_popup()

    def _build_popup(self) -> None:
        self.popup = QWidget(self)
        self.popup.setWindowFlags(Qt.Popup)
        self.popup.setMinimumWidth(340)
        self.popup.setStyleSheet(self._popup_style())

        pw = QVBoxLayout(self.popup)
        pw.setContentsMargins(10, 10, 10, 10)
        pw.setSpacing(8)

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 输入关键字过滤（如 烟气·pH·温度）")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumHeight(28)
        self.search_edit.setStyleSheet(self._input_style())
        self.search_edit.textChanged.connect(self._on_search_changed)
        pw.addWidget(self.search_edit)

        # 分组勾选区（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(240)
        scroll.setMaximumHeight(360)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(3)
        scroll.setWidget(self._list_container)
        pw.addWidget(scroll, 1)

        # 底部操作栏
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self._count_label = QLabel("已选 0 / 0")
        self._count_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 12px;"
        )
        footer.addWidget(self._count_label)
        footer.addStretch()
        sel_all = QPushButton("全选")
        clear = QPushButton("清空")
        sel_all.setFixedHeight(26)
        clear.setFixedHeight(26)
        sel_all.setStyleSheet(self._btn_style())
        clear.setStyleSheet(self._btn_style())
        sel_all.clicked.connect(self.select_all)
        clear.clicked.connect(self.clear_selection)
        footer.addWidget(sel_all)
        footer.addWidget(clear)
        pw.addLayout(footer)

    # ── 样式 ────────────────────────────────────────────────────────────
    @staticmethod
    def _input_style() -> str:
        return (
            f"QLineEdit {{ background: {COLORS['bg_input']}; color: {COLORS['text_primary']};"
            f" border: 1px solid {COLORS['border']}; border-radius: 4px;"
            f" padding: 4px 8px; font-size: 12px; }}"
            f" QLineEdit:focus {{ border-color: {COLORS['accent']}; }}"
        )

    @staticmethod
    def _btn_style() -> str:
        return (
            f"QPushButton {{ background: {COLORS['bg_input']}; color: {COLORS['text_primary']};"
            f" border: 1px solid {COLORS['border']}; border-radius: 4px;"
            f" font-size: 12px; padding: 0 12px; }}"
            f" QPushButton:hover {{ background: {COLORS['secondary']}; }}"
            f" QPushButton:pressed {{ background: {COLORS['accent']}; color: white; }}"
        )

    @staticmethod
    def _popup_style() -> str:
        return (
            f"QWidget {{ background: {COLORS['bg_card']};"
            f" border: 1px solid {COLORS['border']}; border-radius: 6px; }}"
        )

    @staticmethod
    def _group_header_style() -> str:
        return (
            f"QLabel {{ color: {COLORS['accent']}; font-size: 12px;"
            f" font-weight: bold; padding: 4px 2px 2px 2px; }}"
        )

    @staticmethod
    def _checkbox_style() -> str:
        return (
            f"QCheckBox {{ color: {COLORS['text_primary']}; font-size: 12px;"
            f" padding: 3px 4px; spacing: 6px; }}"
            f" QCheckBox:hover {{ color: white; }}"
        )

    # ── 分类与列表 ─────────────────────────────────────────────────────
    def _classify(self, param: str) -> str:
        """把单个指标分到对应桶（与历史版本一致）。

        优先级：gas/water 首要标签 → rax（仅兜底：没在 gas/water 但走右轴）
                → limbo（无任何映射的扩展指标）
        """
        cat = PARAM_CATEGORIES.get(param)
        if cat in ("gas", "water"):
            return cat
        if param in RIGHT_AXIS_PARAMS:
            return "rax"
        return "limbo"

    @staticmethod
    def _param_tag(param: str) -> str:
        cats = []
        if PARAM_CATEGORIES.get(param) == "gas":
            cats.append("废气")
        elif PARAM_CATEGORIES.get(param) == "water":
            cats.append("废水")
        if param in RIGHT_AXIS_PARAMS:
            cats.append("双轴")
        return "·".join(cats)

    def _checkbox_text(self, param: str) -> str:
        tag = self._param_tag(param)
        return f"{param}    {tag}" if tag else param

    def _rebuild_list(self) -> None:
        """按分类重建浮层内的勾选列表。"""
        # 清掉旧控件
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._checkboxes.clear()

        if not self._all_params:
            empty = QLabel("（暂无可对比指标）")
            empty.setStyleSheet(
                f"color: {COLORS['text_secondary']}; font-size: 12px; padding: 8px;"
            )
            self._list_layout.addWidget(empty)
            return

        for key, title in self._GROUPS:
            items = [p for p in self._all_params if self._classify(p) == key]
            if not items:
                continue
            header = QLabel(title)
            header.setStyleSheet(self._group_header_style())
            self._list_layout.addWidget(header)
            for p in items:
                cb = QCheckBox(self._checkbox_text(p))
                cb.setStyleSheet(self._checkbox_style())
                cb.setChecked(p in self._selected)
                cb.stateChanged.connect(
                    lambda state, pp=p: self._on_check(pp, state)
                )
                self._checkboxes[p] = cb
                self._list_layout.addWidget(cb)

        self._list_layout.addStretch()

    def _on_check(self, param: str, state: int) -> None:
        if state == Qt.Checked:
            self._selected.add(param)
        else:
            self._selected.discard(param)
        self._refresh_labels()
        if not self._suppress:
            self.selected_changed.emit(self.get_selected())

    def _on_search_changed(self, _text: str) -> None:
        q = (self.search_edit.text() or "").strip().lower()
        for p, cb in self._checkboxes.items():
            cb.setVisible(q in p.lower())

    def _refresh_labels(self) -> None:
        sel = len(self._selected)
        tot = len(self._all_params)
        self.toggle_btn.setText(f"对比参数 ({sel})")
        if hasattr(self, "_count_label"):
            self._count_label.setText(f"已选 {sel} / {tot}")

    def _toggle_popup(self) -> None:
        if self.popup.isVisible():
            self.popup.hide()
            return
        btn = self.toggle_btn
        self.popup.setFixedWidth(max(340, btn.width()))
        gpos = btn.mapToGlobal(btn.rect().bottomLeft())
        self.popup.move(gpos)
        self.popup.show()
        self.popup.raise_()
