# -*- coding: utf-8 -*-
"""
回归测试：预测趋势图绘制链路（多排放口对比 + 双轴 + 归一化）。

背景：v5.23 的 HoverFigureCanvas 在 Win7 下稳定（用户实测 v5.23 不崩）；
后续 v5.24/v5.27 为"加固"加的 device_pixel_ratio 锁与尺寸守卫反而引入
出图原生崩溃，v5.29 已还原到 v5.23 状态。本测试在无头(offscreen)下实际跑通
ChartWidget.plot_series / clear / 双轴 / 归一化 全链路，确保绘制不抛异常、
绘制后 canvas 具备 renderer（否则"出图"后 paintEvent 早退等价于崩）。

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
    print("=== test_pred_chart_draw 通过 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
