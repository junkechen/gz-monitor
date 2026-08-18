# -*- coding: utf-8 -*-
"""
回归测试：预测趋势图绘制链路（多排放口对比 + 双轴 + 归一化）。

背景：v5.27 修复 Win7 高分屏下"开始预测出图"原生崩溃（device_pixel_ratio
非 1.0 导致 matplotlib QImage 尺寸越界）。本测试在无头(offscreen)下实际跑通
ChartWidget.plot_series / clear / 双轴 / 归一化 全链路，确保：
  1. device_pixel_ratio 始终为 1.0（修复核心）；
  2. 含多 series、right_series_list(双轴)、normalize 的绘制不抛异常；
  3. 绘制后 canvas 具备 renderer，下一次 paintEvent 不会因无 renderer 早退
     （即不会在"出图"后崩）。

运行：
    set QT_QPA_PLATFORM=offscreen
    python tests/test_pred_chart_draw.py
"""
import os
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def main():
    from PyQt5.QtWidgets import QApplication
    from chart_widget import ChartWidget

    app = QApplication.instance() or QApplication(sys.argv[:1])
    errors = []

    def safe(label, fn):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            errors.append((label, repr(e), traceback.format_exc()))

    w = ChartWidget()

    # 1) device_pixel_ratio 必须为 1.0
    if getattr(w.canvas, "_device_pixel_ratio", None) != 1.0:
        errors.append(("device_pixel_ratio",
                        f"{getattr(w.canvas, '_device_pixel_ratio', None)!r}", ""))

    times = ["08-18 01:00", "08-18 02:00", "08-18 03:00", "08-18 04:00"]

    # 2) 多排放口对比（多条曲线，默认不可见）
    safe("plot_series 多曲线", lambda: w.plot_series(
        times=times,
        series_list=[
            {"name": "企业A-排口1", "data": [1.0, 2.0, None, 3.0]},
            {"name": "企业B-排口2", "data": [2.0, None, 1.5, 2.5]},
        ],
        title="预测趋势图 — pH（各排放口对比）",
    ))

    # 3) 双轴（right_series_list）
    safe("plot_series 双轴", lambda: w.plot_series(
        times=times,
        series_list=[{"name": "左轴-流量", "data": [10, 20, 15, 25]}],
        right_series_list=[{"name": "右轴-浓度", "data": [0.1, 0.2, 0.15, 0.3]}],
        right_ylabel="浓度",
        title="预测趋势图 — 双轴",
    ))

    # 4) 归一化（全部缩放到 [0,1]）
    safe("plot_series 归一化", lambda: w.plot_series(
        times=times,
        series_list=[
            {"name": "A", "data": [100, 200, 150, 300]},
            {"name": "B", "data": [1, 2, 1.5, 3]},
        ],
        normalize=True,
        title="预测趋势图 — 归一化",
    ))

    # 5) 绘制后必须具备 renderer（否则下次 paintEvent 早退，等同于"出图后崩"）
    if not hasattr(w.canvas, "renderer"):
        errors.append(("renderer", "plot_series 后 canvas 无 renderer", ""))

    # 6) 清空
    safe("clear", lambda: w.clear())

    if errors:
        print("=== test_pred_chart_draw 未通过 ===")
        for name, msg, tb in errors:
            print(f"  - {name}: {msg}")
            if tb:
                print(tb)
        return 1

    print("[OK] 预测趋势图绘制全链路（多曲线/双轴/归一化/clear）无异常，renderer 已生成")
    print("[OK] canvas.device_pixel_ratio == 1.0（Win7 高分屏兼容）")
    print("=== test_pred_chart_draw 通过 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
