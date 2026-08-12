# -*- coding: utf-8 -*-
"""
v5.20 视觉回归：渲染 ParamPickerPanel 各种分类与状态，输出 PNG。

用途：
- 人工复核"嵌页式双栏选择器"在废气/废水/双轴/已选/搜索 各状态下的布局
- 当 main_window.py / pred_param_selector.py 改动后，可视觉对比截图变化
- 输出至 tests/screenshots/ 目录（git 忽略）

运行：
    set QT_QPA_PLATFORM=offscreen
    python tests/render_param_picker.py
"""
import os
import sys
import logging

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
logging.getLogger("matplotlib").setLevel(logging.WARNING)

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from PyQt5.QtWidgets import QApplication  # noqa: E402

from pred_param_selector import ParamPickerPanel  # noqa: E402


SCREENSHOT_DIR = os.path.join(HERE, "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

SAMPLE = (
    ["非甲烷总烃", "烟气温度", "烟气流量", "二氧化硫", "氮氧化物", "颗粒物"]
    + ["pH值", "化学需氧量", "氨氮", "流量", "废水流量", "水温"]
    + ["自定义指标A"]  # 落入 limbo
)


def _switch_to(picker, key):
    for i in range(picker.category_list.count()):
        if picker.category_list.item(i).data(0x0100) == key:
            picker.category_list.setCurrentRow(i)
            return True
    return False


def _grab(picker, name: str):
    """渲染前强制刷新两个 QListWidget 的 viewport，避免 offscreen 漏渲。"""
    app = QApplication.instance()
    for cat in (getattr(picker, "category_list", None),
                getattr(picker, "param_list", None)):
        if cat is not None:
            cat.viewport().update()
            cat.viewport().repaint()
            cat.repaint()
    picker.repaint()
    for _ in range(8):
        app.processEvents()
    pixmap = picker.grab()
    out = os.path.join(SCREENSHOT_DIR, name + ".png")
    pixmap.save(out, "PNG")
    print(f"[OK] 截图已存 {out} ({pixmap.width()}x{pixmap.height()})")


def main():
    app = QApplication.instance() or QApplication(sys.argv[:1])

    picker = ParamPickerPanel()
    picker.set_available_params(SAMPLE)
    picker.set_selected(["非甲烷总烃", "pH值", "化学需氧量"])
    picker.resize(900, 320)  # 给够高度以便所有项都可见
    picker.show()
    for _ in range(8):
        app.processEvents()

    # 默认（"全部"分类）
    _grab(picker, "panel_all")

    # 切到"废气"
    if _switch_to(picker, "gas"):
        _grab(picker, "panel_gas")

    # 切到"废水"
    if _switch_to(picker, "water"):
        _grab(picker, "panel_water")

    # 切到"已选"
    if _switch_to(picker, "sel"):
        _grab(picker, "panel_selected")

    # 切回"全部" + 加搜索"烟"
    _switch_to(picker, "all")
    picker.search_edit.setText("烟")
    for _ in range(8):
        app.processEvents()
    _grab(picker, "panel_search_y烟")

    # 清空搜索，模拟极端窄窗口（让 splitter 比例硬挤）
    picker.search_edit.setText("")
    picker.resize(500, 320)
    for _ in range(8):
        app.processEvents()
    _grab(picker, "panel_narrow")

    print("\n=== 已生成 6 张截图，全部存于 tests/screenshots/ ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
