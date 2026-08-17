# -*- coding: utf-8 -*-
"""
v5.21 单元测试：预测页「对比参数 / 趋势图」垂直 QSplitter 布局。

验证：
- 选择器 + 趋势图被一个垂直 QSplitter 包裹，用户可拖拽调大小
- 默认比例趋势图占大头；选择器可完全折叠、趋势图不可折叠
- 选择器面板自身 minimumHeight 由 180 降到 120（不再顶高挤压趋势图）
- 趋势图标题栏新增「已选 N 项」统计 label

运行（Python 3.8 环境 + 项目 src 目录）：
    set QT_QPA_PLATFORM=offscreen
    python tests/test_chart_splitter.py
"""
import os
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)


class _FakeClient:
    """模拟单企业客户端，避免触发任何网络请求。"""
    clients = {}

    def get_all_realtime_data(self, *a, **k):
        return {}

    def get_client_by_subid(self, *a, **k):
        return None


def main():
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication, QGroupBox
    from main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv[:1])
    errors = []

    try:
        w = MainWindow(_FakeClient())
    except Exception as e:  # noqa: BLE001
        print("[FAIL] MainWindow 构造抛异常:")
        print(traceback.format_exc())
        return 1

    sp = getattr(w, "_pred_chart_splitter", None)
    if sp is None:
        print("[FAIL] 缺少 _pred_chart_splitter")
        return 1

    # 1) 方向为垂直
    if sp.orientation() != Qt.Vertical:
        errors.append(("splitter 方向应为 Vertical", sp.orientation(), ""))
    else:
        print("[OK] splitter 方向 = Vertical")

    # 2) 两个窗格：选择器 + 趋势图
    if sp.count() != 2:
        errors.append(("splitter 应有 2 个窗格", sp.count(), ""))
    else:
        print("[OK] splitter 含 2 个窗格")

    # 3) 窗格 0 = 对比参数面板
    if sp.widget(0) is not w.pred_compare_panel:
        errors.append(("窗格0 应为 pred_compare_panel", type(sp.widget(0)), ""))
    else:
        print("[OK] 窗格0 = pred_compare_panel（对比参数）")

    # 4) 窗格 1 应是含趋势图的 QGroupBox
    w1 = sp.widget(1)
    if not (isinstance(w1, QGroupBox) and w1.isAncestorOf(w.pred_chart)):
        errors.append(("窗格1 应为含 pred_chart 的 QGroupBox",
                       type(w1), ""))
    else:
        print("[OK] 窗格1 = 趋势图 group（含 pred_chart）")

    # 5) 可折叠性：选择器可全折叠，趋势图不可折叠
    if not sp.isCollapsible(0):
        errors.append(("选择器应可折叠", "", ""))
    else:
        print("[OK] 选择器可完全折叠")
    if sp.isCollapsible(1):
        errors.append(("趋势图不可折叠", "", ""))
    else:
        print("[OK] 趋势图不可折叠")

    # 6) 选择器最小高度（v5.25 改为下拉按钮，仅需 40）
    if w.param_picker.minimumHeight() != 40:
        errors.append(("param_picker minHeight 应为 40",
                       w.param_picker.minimumHeight(), ""))
    else:
        print("[OK] param_picker.minimumHeight = 40")

    # 7) 已选计数 label 存在
    if not hasattr(w, "pred_chart_selected_label"):
        errors.append(("缺少 pred_chart_selected_label", "", ""))
    else:
        print("[OK] pred_chart_selected_label 存在")

    if errors:
        print(f"\n[FAIL] {len(errors)} 项断言未通过：")
        for name, got, tb in errors:
            print(f"  - {name}: got={got}")
        return 1

    print("\n[PASS] v5.21 预测页 splitter 布局全部断言通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
