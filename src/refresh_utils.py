# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 刷新/差量/轴分类 工具模块（三项优化共享层）

提供：
  - TableDiff    : QTableWidget 差量渲染引擎（仅对变化的单元格 setItem）
  - classify_axis: 根据参数名判断走左轴(浓度)还是右轴(twinx)
  - make_throttle: 轻量节流装饰器（合并高频刷新请求）

本模块为零/低依赖的自研纯 Python + PyQt5 组件，Windows 7 兼容。
"""

import time
from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt5.QtCore import Qt


class TableDiff:
    """QTableWidget 差量渲染引擎。

    维护一个快照 ``_prev``，键为 ``(row, col)``，值为 ``(text, fg_color_hex)``。
    渲染时仅对签名变化的单元格调用 ``table.setItem``，并在外层用
    ``setUpdatesEnabled(False/True)`` 包裹，避免闪烁与全量重写带来的卡顿。

    差量比对签名：``sig = (item.text(), item.foreground().color().name())``
    """

    def __init__(self, table: QTableWidget):
        self._table = table
        self._prev = {}
        self._prev_shape = (0, 0)

    def render(self, rows, col_count, make_item_fn, full_reset=False):
        """差量渲染二维内容。

        Args:
            rows: 二维内容列表，``rows[r][c]`` 为该单元格的值（任意可哈希对象）。
            col_count: 列数。
            make_item_fn: 回调 ``make_item_fn(r, c, val) -> QTableWidgetItem``。
            full_reset: 是否强制全量重绘（形状变化或强制重置时传 True）。

        Returns:
            ``(changed, total)``：实际发生变化的单元格数 / 总单元格数。
        """
        table = self._table
        new_shape = (len(rows), col_count)

        # 形状变化或强制重置 -> 全量 setItem 并重置快照
        if full_reset or new_shape != self._prev_shape:
            table.setUpdatesEnabled(False)
            try:
                table.setRowCount(new_shape[0])
                table.setColumnCount(col_count)
                self._prev = {}
                for r in range(new_shape[0]):
                    for c in range(col_count):
                        val = rows[r][c] if (r < len(rows) and c < len(rows[r])) else ""
                        item = make_item_fn(r, c, val)
                        if item is not None:
                            table.setItem(r, c, item)
                            self._prev[(r, c)] = (
                                item.text(),
                                item.foreground().color().name(),
                            )
                        else:
                            self._prev[(r, c)] = None
            finally:
                table.setUpdatesEnabled(True)
            self._prev_shape = new_shape
            return (new_shape[0] * col_count, new_shape[0] * col_count)

        # 差量更新：逐格比对签名，仅变化者 setItem
        changed = 0
        total = new_shape[0] * col_count
        table.setUpdatesEnabled(False)
        try:
            for r in range(new_shape[0]):
                for c in range(col_count):
                    val = rows[r][c] if (r < len(rows) and c < len(rows[r])) else ""
                    item = make_item_fn(r, c, val)
                    sig = None
                    if item is not None:
                        sig = (item.text(), item.foreground().color().name())
                    if sig != self._prev.get((r, c)):
                        if item is not None:
                            table.setItem(r, c, item)
                        self._prev[(r, c)] = sig
                        changed += 1
                    else:
                        # 未变化：不写表，丢弃临时 item（由 GC 回收）
                        del item
        finally:
            table.setUpdatesEnabled(True)
        self._prev_shape = new_shape
        return (changed, total)

    def render_empty(self, placeholder="暂无数据"):
        """渲染单行灰色"暂无数据"占位。"""
        table = self._table
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(1)
            table.setColumnCount(1)
            item = QTableWidgetItem(placeholder)
            item.setForeground(Qt.gray)
            item.setTextAlignment(Qt.AlignCenter)
            table.setItem(0, 0, item)
            self._prev = {(0, 0): (item.text(), item.foreground().color().name())}
            self._prev_shape = (1, 1)
        finally:
            table.setUpdatesEnabled(True)

    def reset(self):
        """主动清空快照（换表内容时调用）。"""
        self._prev = {}
        self._prev_shape = (0, 0)


def classify_axis(param_name):
    """根据参数名判断其数值轴归属。

    命中右轴参数集合（pH值 / 烟气温度 / 水温）返回 ``"right"``，
    其余（浓度 mg/L 等）返回 ``"left"``。常量从 config.RIGHT_AXIS_PARAMS 读取。

    Args:
        param_name: 监测参数显示名（如 "pH值"）。

    Returns:
        ``"left"`` 或 ``"right"``。
    """
    from config import RIGHT_AXIS_PARAMS
    return "right" if param_name in RIGHT_AXIS_PARAMS else "left"


def make_throttle(interval_ms):
    """返回一个节流装饰器工厂，确保被装饰函数两次实际调用间隔不少于 ``interval_ms``。

    使用 ``time.monotonic()`` 计时；用于合并高频刷新/重绘请求。
    典型用法：``@make_throttle(THROTTLE_MS)``。

    Args:
        interval_ms: 最小触发间隔（毫秒）。

    Returns:
        装饰器函数。
    """
    _last = [0.0]

    def throttle(fn):
        def wrapper(*args, **kwargs):
            now = time.monotonic() * 1000
            if now - _last[0] < interval_ms:
                return None
            _last[0] = now
            return fn(*args, **kwargs)
        wrapper.__name__ = getattr(fn, "__name__", "throttled")
        return wrapper
    return throttle
