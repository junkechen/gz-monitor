# -*- coding: utf-8 -*-
"""
v5.21 视觉回归：渲染预测页「对比参数 / 趋势图」splitter 三种状态，输出 PNG。

用途：人工复核 splitter 默认比例、选择器可折叠、选择器可拉大三种布局。
输出至 tests/screenshots/（git 忽略）。

运行（Python 3.8 环境 + 项目 src 目录）：
    set QT_QPA_PLATFORM=offscreen
    python tests/render_pred_layout.py
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

from main_window import MainWindow  # noqa: E402


SCREENSHOT_DIR = os.path.join(HERE, "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

SAMPLE = (
    ["非甲烷总烃", "烟气温度", "烟气流量", "二氧化硫", "氮氧化物", "颗粒物"]
    + ["pH值", "化学需氧量", "氨氮", "流量", "废水流量", "水温"]
    + ["自定义指标A"]
)


class _FakeClient:
    clients = {}

    def get_all_realtime_data(self, *a, **k):
        return {}

    def get_client_by_subid(self, *a, **k):
        return None


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

    w = MainWindow(_FakeClient())
    w.show()
    w.resize(1200, 820)
    # 切到预测 tab（right_panel 是局部变量，经 prediction_tab.parent() 取到 QTabWidget）
    tab = w.prediction_tab.parent()
    if tab is not None:
        tab.setCurrentIndex(2)
    # 填充示例指标，便于视觉复核选择器
    try:
        w.param_picker.set_available_params(SAMPLE)
        w.param_picker.set_selected(["非甲烷总烃", "pH值", "化学需氧量"])
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] 填充示例指标失败（非致命）: {e}")
    for _ in range(10):
        app.processEvents()

    sp = w._pred_chart_splitter

    # 1) 默认：趋势图占大头（≈140:600）
    sp.setSizes([140, 600])
    for _ in range(10):
        app.processEvents()
    _grab(w.pred_chart_section, "pred_layout_default")

    # 2) 选择器完全折叠
    sp.setSizes([0, 800])
    for _ in range(10):
        app.processEvents()
    _grab(w.pred_chart_section, "pred_layout_collapsed")

    # 3) 选择器被拉大
    sp.setSizes([420, 400])
    for _ in range(10):
        app.processEvents()
    _grab(w.pred_chart_section, "pred_layout_picker_big")

    print("\n=== 已生成 3 张预测页布局截图，存于 tests/screenshots/ ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
