# -*- coding: utf-8 -*-
"""
v5.25 视觉回归：渲染 ParamPickerPanel 下拉多选形态，输出 PNG。

用途：
- 人工复核"对比参数 (N) ▾"按钮 + 展开浮层（搜索 + 分组勾选 + 全选/清空）
- 当 pred_param_selector.py 改动后，可视觉对比截图变化
- 输出至 tests/screenshots/（git 忽略）

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


def _grab(widget, name):
    app = QApplication.instance()
    widget.repaint()
    for _ in range(10):
        app.processEvents()
    pixmap = widget.grab()
    out = os.path.join(SCREENSHOT_DIR, name + ".png")
    pixmap.save(out, "PNG")
    print(f"[OK] 截图已存 {out} ({pixmap.width()}x{pixmap.height()})")


def main():
    app = QApplication.instance() or QApplication(sys.argv[:1])

    picker = ParamPickerPanel()
    picker.set_available_params(SAMPLE)
    picker.set_selected(["非甲烷总烃", "pH值", "化学需氧量"])
    picker.resize(900, 40)
    picker.show()
    for _ in range(8):
        app.processEvents()

    # 1) 收起态：仅一个按钮「对比参数 (N) ▾」
    _grab(picker, "panel_collapsed")

    # 2) 展开浮层：搜索 + 分组勾选 + 全选/清空
    picker._toggle_popup()
    for _ in range(8):
        app.processEvents()
    try:
        _grab(picker.popup, "panel_popup")
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 浮层截图失败（offscreen 限制，非致命）: {e}")

    # 3) 展开 + 搜索"烟"
    try:
        picker.search_edit.setText("烟")
        for _ in range(8):
            app.processEvents()
        _grab(picker.popup, "panel_popup_search")
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 浮层搜索态截图失败（非致命）: {e}")

    print("\n=== 已生成下拉选择器截图，存于 tests/screenshots/ ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
