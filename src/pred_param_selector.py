# -*- coding: utf-8 -*-
"""
v5.20 预测页面优化：嵌页式双栏"对比参数"选择器

设计目标（来源：用户需求）
1. 提供清晰的指标分类（废气/废水/双轴/已选/其他），替代原本横向滚动的扁平列表
2. 提供按名称的实时模糊搜索
3. 与主页面同处一个布局，支持窗口大小变化时自适应缩放（左右两栏共用 splitter 比例）
4. 保留原有全选/反选/清空操作，保证后端调用契约不变
5. 选中状态变化发出 selected_changed(list[str]) 信号，下游无需改动

实现策略
- 左侧 QListWidget（不可多选，单选作分组切换）  → category_list
- 右侧 QListWidget（可多选，复选框）              → param_list
- 顶部 QLineEdit 模糊搜索                          → search_edit
- 底部 统计 + 全选/反选/清空                         → status_label / btn_x3
- 不依赖 QStackedWidget，分类切换时直接修改右侧数据源，更省内存

设计权衡
- "已选"分类不存储新数据，仅在切换时把选中项提到顶部；选项本身从 category_all/gas/water 继承
- "其他"分类按需展示（服务端返回了但没列入 PARAM_CATEGORIES 的）
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
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config import (
    CATEGORY_DISPLAY,
    CATEGORY_ORDER,
    COLORS,
    PARAM_CATEGORIES,
    RIGHT_AXIS_PARAMS,
)


class ParamPickerPanel(QWidget):
    """嵌页式"对比参数"双栏选择器。

    Signals
    -------
    selected_changed(list[str])  选中指标列表发生变化（增减）
    """

    selected_changed = pyqtSignal(list)

    # 类级常量：空态占位文案
    _EMPTY_TIP = "（当前分类下无匹配指标）"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._all_params: List[str] = []          # 当前可用的全部指标（按出现顺序）
        self._selected: Set[str] = set()          # 当前已选指标的快速查找 set
        self._current_category = "all"           # 当前分类 key
        self._suppress_item_changed = False       # 阻止 itemChanged 回环
        self._build_ui()

    # ── 公开 API ─────────────────────────────────────────────────────────
    def set_available_params(self, params: Iterable[str]) -> None:
        """设置当前可用指标列表。会重新构建数据并保留旧选中状态。

        Args:
            params: 服务端真实可见的指标名集合（任意顺序，重复会被去重保序）
        """
        seen: Set[str] = set()
        ordered: List[str] = []
        for p in params:
            if not p:
                continue
            if p in seen:
                continue
            seen.add(p)
            ordered.append(p)
        self._all_params = ordered
        # 丢掉已不存在的选中项
        self._selected = {p for p in self._selected if p in seen}
        # 重新构建左侧分类计数 & 切回"全部"
        self._refresh_categories()
        self._refresh_right_list()

    def get_selected(self) -> List[str]:
        """返回当前已选指标列表（按出现顺序，便于测试与一致 UI 渲染）"""
        return [p for p in self._all_params if p in self._selected]

    def set_selected(self, params: Iterable[str]) -> None:
        """外部设定已选指标（如重置/导入方案），会清空现有选中。"""
        target = set(params)
        self._selected = {p for p in target if p in set(self._all_params)}
        self._suppress_item_changed = True
        try:
            self._refresh_right_list()
        finally:
            self._suppress_item_changed = False
        self._refresh_status()
        self.selected_changed.emit(self.get_selected())

    def selected_count(self) -> int:
        return len(self._selected)

    def total_count(self) -> int:
        return len(self._all_params)

    # ── 外部按钮驱动（保持与原 QListWidget 全选/反选/清空按钮的视觉位置） ──
    def select_all(self) -> None:
        self._on_select_all()

    def invert(self) -> None:
        self._on_invert()

    def clear_selection(self) -> None:
        self._on_clear()

    # ── UI 构建 ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # ── 第 1 行：搜索框 + 操作按钮 + 计数 ────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(8)
        top.setContentsMargins(0, 0, 0, 0)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 输入关键字过滤（如 烟气·pH·温度）")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumWidth(160)
        self.search_edit.setStyleSheet(self._input_style())
        self.search_edit.textChanged.connect(self._on_search_changed)
        top.addWidget(self.search_edit, 1)

        self.select_all_btn = QPushButton("全选")
        self.invert_btn = QPushButton("反选")
        self.clear_btn = QPushButton("清空")
        for btn in (self.select_all_btn, self.invert_btn, self.clear_btn):
            btn.setFixedHeight(26)
            btn.setStyleSheet(self._btn_style())
            top.addWidget(btn)
        self.select_all_btn.clicked.connect(self._on_select_all)
        self.invert_btn.clicked.connect(self._on_invert)
        self.clear_btn.clicked.connect(self._on_clear)

        self.status_label = QLabel("已选 0 / 0")
        self.status_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 12px; padding: 0 4px;"
        )
        self.status_label.setMinimumWidth(110)
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.status_label)

        root.addLayout(top)

        # ── 第 2 行：左侧分类 + 右侧指标（用一个内嵌 splitter，让用户可拖） ──
        from PyQt5.QtWidgets import QSplitter

        body = QHBoxLayout()
        body.setSpacing(0)
        body.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(4)

        # 左侧分类列表
        self.category_list = QListWidget(self.splitter)
        self.category_list.setFixedWidth(170)
        self.category_list.setStyleSheet(self._left_list_style())
        self.category_list.setSelectionMode(QListWidget.SingleSelection)
        self.category_list.currentRowChanged.connect(self._on_category_changed)

        # 右侧指标列表
        self.param_list = QListWidget(self.splitter)
        self.param_list.setStyleSheet(self._right_list_style())
        self.param_list.setSelectionMode(QListWidget.NoSelection)  # 用 item 的 check 状态
        self.param_list.itemChanged.connect(self._on_item_changed)

        self.splitter.addWidget(self.category_list)
        self.splitter.addWidget(self.param_list)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        # 初始 1:3 比例
        self.splitter.setSizes([170, 530])

        # 把 splitter 嵌入到 root（用 wrapper 让 root 对它 stretch）
        body.addWidget(self.splitter, 1)

        root.addLayout(body, 1)

        # 整体 size policy 让 panel 可被外层 splitter 压高/拉高
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(120)

        # 空态初始化分类与右侧
        self._refresh_categories()
        self._refresh_right_list()

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
            f" font-size: 12px; padding: 0 10px; }}"
            f" QPushButton:hover {{ background: {COLORS['secondary']}; }}"
        )

    @staticmethod
    def _left_list_style() -> str:
        return (
            f"QListWidget {{ background: {COLORS['bg_card']}; color: {COLORS['text_primary']};"
            f" border: 1px solid {COLORS['border']}; border-radius: 4px;"
            f" outline: 0; padding: 4px 2px; }}"
            f" QListWidget::item {{ padding: 8px 10px; border-radius: 3px;"
            f"   font-size: 12px; }}"
            f" QListWidget::item:hover {{ background: {COLORS['bg_input']}; }}"
            f" QListWidget::item:selected {{ background: {COLORS['secondary']};"
            f"   color: white; font-weight: bold; }}"
        )

    @staticmethod
    def _right_list_style() -> str:
        return (
            f"QListWidget {{ background: {COLORS['bg_input']}; color: {COLORS['text_primary']};"
            f" border: 1px solid {COLORS['border']}; border-top-right-radius: 4px;"
            f" border-bottom-right-radius: 4px;"
            f" border-top-left-radius: 0; border-bottom-left-radius: 0;"
            f" outline: 0; padding: 4px; }}"
            f" QListWidget::item {{ padding: 6px 8px; border-radius: 3px;"
            f"   font-size: 12px; }}"
            f" QListWidget::item:hover {{ background: {COLORS['bg_card']}; }}"
            f" QListWidget::item:selected {{ background: transparent; color: inherit; }}"
        )

    # ── 分类与列表刷新 ─────────────────────────────────────────────────
    def _category_counts(self) -> Dict[str, int]:
        """返回每个分类下的指标数量（不考虑搜索 / 选中过滤）。"""
        counts = {key: 0 for key, _ in CATEGORY_ORDER}
        for p in self._all_params:
            cat = self._classify(p)
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def _classify(self, param: str) -> str:
        """把单个指标分到对应桶。"已选"不属独立桶，切换时才过滤。

        优先级（用户语义）：
          1. gas / water（首要标签 — 用户最常用）
          2. rax —— 仅兜底，捕获"没在 gas/water 但走右轴"的指标（如水温）
          3. limbo —— 没有任何映射的扩展指标
        """
        cat = PARAM_CATEGORIES.get(param)
        if cat in ("gas", "water"):
            return cat
        if param in RIGHT_AXIS_PARAMS:
            return "rax"
        return "limbo"

    def _refresh_categories(self) -> None:
        """把左侧分类列表刷新一遍，并在文字后加计数。"""
        counts = self._category_counts()
        selected_count = len(self._selected)

        self._suppress_item_changed = True
        try:
            self.category_list.clear()
            for idx, (key, label) in enumerate(CATEGORY_ORDER):
                # 已选项在前一项计数就用 selected_count
                if key == "sel":
                    text = f"{label} ({selected_count})"
                else:
                    text = f"{label} ({counts.get(key, 0)})"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, key)
                self.category_list.addItem(item)
            # 默认选中"全部"
            if self.category_list.count() > 0:
                # 把 current_row 同步到 _current_category
                target_row = 0
                for i in range(self.category_list.count()):
                    if self.category_list.item(i).data(Qt.UserRole) == self._current_category:
                        target_row = i
                        break
                self.category_list.setCurrentRow(target_row)
        finally:
            self._suppress_item_changed = False

    def _refresh_right_list(self) -> None:
        """根据当前分类 + 搜索词，重新构建右侧指标列表。"""
        self._suppress_item_changed = True
        try:
            self.param_list.clear()
            params_in_category = self._filter_by_category(self._current_category)
            params_after_search = self._filter_by_search(params_in_category)

            if not params_after_search:
                # 空态占位（不可选）
                empty = QListWidgetItem(self._EMPTY_TIP)
                empty.setFlags(Qt.NoItemFlags)
                empty.setForeground(QColor(COLORS["text_secondary"]))
                self.param_list.addItem(empty)
                self._refresh_status()
                return

            for p in params_after_search:
                item = QListWidgetItem(p)
                # 显示一行：指标名 + (标签)
                tag = self._param_tag(p)
                if tag:
                    item.setText(f"{p}    {tag}")
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if p in self._selected else Qt.Unchecked)
                # 让 QListWidget 把整行当作可点击区域
                item.setData(Qt.UserRole, p)
                self.param_list.addItem(item)
        finally:
            self._suppress_item_changed = False
        self._refresh_status()

    def _filter_by_category(self, category: str) -> List[str]:
        if category == "sel":
            return [p for p in self._all_params if p in self._selected]
        if category == "all":
            return list(self._all_params)
        # gas / water / rax / limbo
        return [p for p in self._all_params if self._classify(p) == category]

    def _filter_by_search(self, params: List[str]) -> List[str]:
        q = (self.search_edit.text() or "").strip().lower()
        if not q:
            return params
        return [p for p in params if q in p.lower()]

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

    def _refresh_status(self) -> None:
        total = len(self._all_params)
        sel = len(self._selected)
        visible = self.param_list.count()
        if visible == 0 or (visible == 1 and not self.param_list.item(0).data(Qt.UserRole)):
            self.status_label.setText(f"已选 {sel} / {total}")
        else:
            self.status_label.setText(f"已选 {sel} / {total}  ·  当前显示 {visible}")

    # ── 槽函数 ──────────────────────────────────────────────────────────
    def _on_search_changed(self, _text: str) -> None:
        self._refresh_right_list()

    def _on_category_changed(self, current_row: int) -> None:
        if self._suppress_item_changed:
            return
        if current_row < 0:
            return
        item = self.category_list.item(current_row)
        if not item:
            return
        key = item.data(Qt.UserRole)
        self._current_category = key
        self._refresh_right_list()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._suppress_item_changed:
            return
        param = item.data(Qt.UserRole)
        if not param:
            return  # 空态占位行
        if item.checkState() == Qt.Checked:
            self._selected.add(param)
        else:
            self._selected.discard(param)
        # 切换到"已选"分类时，需刷新左侧计数 / 选项内容
        # 简化：每次都更新左侧计数 + status（廉价）
        self._refresh_categories()
        self._refresh_status()
        self.selected_changed.emit(self.get_selected())

    def _on_select_all(self) -> None:
        # 只对当前分类可见项生效，避免误选
        self._suppress_item_changed = True
        try:
            for i in range(self.param_list.count()):
                it = self.param_list.item(i)
                param = it.data(Qt.UserRole)
                if not param:
                    continue
                if it.checkState() != Qt.Checked:
                    it.setCheckState(Qt.Checked)
                self._selected.add(param)
        finally:
            self._suppress_item_changed = False
        self._refresh_categories()
        self._refresh_status()
        self.selected_changed.emit(self.get_selected())

    def _on_invert(self) -> None:
        self._suppress_item_changed = True
        try:
            for i in range(self.param_list.count()):
                it = self.param_list.item(i)
                param = it.data(Qt.UserRole)
                if not param:
                    continue
                new_state = (
                    Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked
                )
                it.setCheckState(new_state)
                if new_state == Qt.Checked:
                    self._selected.add(param)
                else:
                    self._selected.discard(param)
        finally:
            self._suppress_item_changed = False
        self._refresh_categories()
        self._refresh_status()
        self.selected_changed.emit(self.get_selected())

    def _on_clear(self) -> None:
        self._suppress_item_changed = True
        try:
            for i in range(self.param_list.count()):
                it = self.param_list.item(i)
                param = it.data(Qt.UserRole)
                if not param or it.checkState() == Qt.Unchecked:
                    continue
                it.setCheckState(Qt.Unchecked)
        finally:
            self._suppress_item_changed = False
        self._selected.clear()
        self._refresh_categories()
        self._refresh_status()
        self.selected_changed.emit(self.get_selected())
