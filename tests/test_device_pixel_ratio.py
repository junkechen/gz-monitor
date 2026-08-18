# -*- coding: utf-8 -*-
"""
回归测试：HoverFigureCanvas 的 Win7 高分屏兼容修复。

背景：
    GZ_Monitor 在 Win7 高分屏（125%/150% 系统 DPI）下"开始预测出图"时闪退。
    根因：matplotlib 3.7 的 FigureCanvasQTAgg._update_pixel_ratio 直接读取
    Qt 的 devicePixelRatioF()；Win7 高分屏下该值为 1.25/1.5，导致 paintEvent
    中 copy_from_bbox 的 bbox / QImage 尺寸出现分数或越界，触发原生段错误。
    （Win10 标准 100% DPI 下该值为 1.0，故不受影响。）

    修复：覆盖 _update_pixel_ratio，强制 device_pixel_ratio = 1.0，并在
    __init__ 中 setDevicePixelRatio(1.0)。

    本测试在无头(offscreen)下验证：构造后、以及模拟屏幕 DPI 变化触发
    _update_pixel_ratio 后，device_pixel_ratio 始终为 1.0，从而从根上消除
    Win7 原生崩溃。

运行：
    set QT_QPA_PLATFORM=offscreen
    python tests/test_device_pixel_ratio.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def main():
    from PyQt5.QtWidgets import QApplication
    from matplotlib.figure import Figure
    from chart_widget import HoverFigureCanvas

    app = QApplication.instance() or QApplication(sys.argv[:1])

    fig = Figure(figsize=(7.6, 3.8), dpi=80)
    canvas = HoverFigureCanvas(fig)

    errors = []

    # 1) 构造后 device_pixel_ratio 必须为 1.0
    dpr = getattr(canvas, "_device_pixel_ratio", None)
    if dpr != 1.0:
        errors.append(f"构造后 _device_pixel_ratio={dpr!r}，期望 1.0")
    try:
        qt_dpr = canvas.devicePixelRatio()
    except Exception as e:  # noqa: BLE001
        qt_dpr = None
        errors.append(f"读取 Qt devicePixelRatio 抛异常: {e!r}")
    if qt_dpr is not None and qt_dpr != 1.0:
        errors.append(f"Qt devicePixelRatio={qt_dpr!r}，期望 1.0")

    # 2) 模拟屏幕 DPI 变化触发 _update_pixel_ratio，仍须保持 1.0
    try:
        canvas._update_pixel_ratio()
    except Exception as e:  # noqa: BLE001
        errors.append(f"调用 _update_pixel_ratio 抛异常: {e!r}")
    if getattr(canvas, "_device_pixel_ratio", None) != 1.0:
        errors.append(
            f"_update_pixel_ratio 后 _device_pixel_ratio="
            f"{getattr(canvas, '_device_pixel_ratio', None)!r}，期望 1.0")

    # 3) 验证属性 device_pixel_ratio 也返回 1.0（paintEvent 用它换算尺寸）
    try:
        prop = canvas.device_pixel_ratio
    except Exception as e:  # noqa: BLE001
        prop = None
        errors.append(f"读取属性 device_pixel_ratio 抛异常: {e!r}")
    if prop != 1.0:
        errors.append(f"属性 device_pixel_ratio={prop!r}，期望 1.0")

    if errors:
        print("=== test_device_pixel_ratio 未通过 ===")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("[OK] HoverFigureCanvas.device_pixel_ratio 已锁定为 1.0（Win7 高分屏兼容）")
    print("=== test_device_pixel_ratio 通过 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
