# -*- coding: utf-8 -*-
"""
冒烟测试：无头（offscreen）实例化 MainWindow，验证启动不崩溃。

背景：v5.19 因 _init_ui() 调用 _pred_chart_mode 时该属性尚未初始化，
导致登录后创建主窗口即 AttributeError 崩溃。此测试用空客户端构造
MainWindow，跑通 __init__ 全链路（含 _init_ui / _setup_warning /
_setup_menu / _refresh_data），用于回归守护。

运行（必须用 Python 3.8 环境 + 项目 src 目录）：
    set QT_QPA_PLATFORM=offscreen
    python tests/smoke_main_window.py
"""
import os
import sys
import logging
import traceback

# 无头运行，避免需要真实显示器
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# 屏蔽 matplotlib 字体查找的 DEBUG 刷屏，保持测试输出可读
logging.getLogger("matplotlib").setLevel(logging.WARNING)

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)


class _FakeClient:
    """模拟单企业客户端，避免触发任何网络请求。"""
    clients = {}  # 空：_refresh_data 应因无可刷新企业而早退

    def get_all_realtime_data(self, *a, **k):
        return {}

    def get_client_by_subid(self, *a, **k):
        return None


def main():
    from PyQt5.QtWidgets import QApplication
    from main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv[:1])

    errors = []

    # 1) 构造主窗口（核心：必须不抛 AttributeError）
    try:
        w = MainWindow(_FakeClient())
    except Exception as e:  # noqa: BLE001
        errors.append(("MainWindow.__init__", repr(e), traceback.format_exc()))
        print("[FAIL] MainWindow 构造抛异常：")
        print(traceback.format_exc())
        return 1

    # 2) 关键属性在位性检查（防止再次出现"用前未初始化"）
    required_attrs = [
        "_pred_chart_mode", "_pred_chart_normalize", "_pred_chart_loading",
        "_pred_chart_dirty", "_pred_chart_visible", "_prediction_dirty",
        "_last_pred_horizon", "_refresh_last_flush", "_refresh_timer_coalesce",
        "_hist_worker", "_hist_results", "_history_cache", "_rt_diff",
        "pred_mode_combo", "realtime_table",
        # v5.20：横向滚动 ListWidget 已替换为 ParamPickerPanel
        "param_picker",
        "refresh_timer", "prediction_timer",
    ]
    missing = [a for a in required_attrs if not hasattr(w, a)]
    if missing:
        errors.append(("缺失属性", ", ".join(missing), ""))
        print(f"[FAIL] 关键属性缺失: {missing}")
    else:
        print("[OK] 全部关键属性已初始化")

    # 2.5) v5.20 验证：param_picker 是 ParamPickerPanel 类型 + 关键子组件齐全
    try:
        from pred_param_selector import ParamPickerPanel
        if isinstance(w.param_picker, ParamPickerPanel):
            print("[OK] param_picker 是 ParamPickerPanel 类型（v5.20 双栏选择器）")
        else:
            errors.append(("param_picker 类型错误", f"got {type(w.param_picker)}", ""))
            print("[FAIL] param_picker 不是 ParamPickerPanel 类型")
        for sub in ("category_list", "param_list", "search_edit",
                    "status_label", "splitter"):
            has = hasattr(w.param_picker, sub)
            print(f"  - param_picker.{sub}: {'OK' if has else 'MISSING'}")
            if not has:
                errors.append((f"param_picker 缺子组件 {sub}", "", ""))
    except Exception as e:  # noqa: BLE001
        errors.append(("param_picker 检查", repr(e), traceback.format_exc()))
        print(f"[FAIL] param_picker 检查异常: {e}")

    # 3) 尝试一次预测图绘制入口（不依赖网络数据，应安全降级）
    try:
        if hasattr(w, "_draw_pred_chart_multi"):
            w._draw_pred_chart_multi([], w._pred_chart_mode)
            print("[OK] _draw_pred_chart_multi([], mode) 调用安全")
    except Exception as e:  # noqa: BLE001
        errors.append(("_draw_pred_chart_multi", repr(e), traceback.format_exc()))
        print(f"[WARN] _draw_pred_chart_multi 抛异常（非致命，记录）: {e}")

    if errors:
        print(f"\n=== 冒烟测试未通过，共 {len(errors)} 处问题 ===")
        for name, msg, _tb in errors:
            print(f"  - {name}: {msg}")
        return 1

    print("\n=== 冒烟测试通过：MainWindow 可无头构造，启动崩溃已修复 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
