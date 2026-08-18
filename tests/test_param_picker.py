# -*- coding: utf-8 -*-
"""
v5.25 下拉式多选"对比参数"选择器（ParamPickerPanel）单测。

覆盖：
  - 实例化 + 关键子组件就位（toggle_btn / popup / search_edit / _checkboxes）
  - set_available_params：去重保序、分类计数刷新
  - 选中读写：get_selected / set_selected 往返
  - 分类：_classify 优先级（gas/water 优先于 rax，未知归 limbo）
  - 搜索过滤：输入"烟"只剩含"烟"的勾选项可见
  - 全选/反选/清空：操作全局生效
  - 信号：selected_changed 在每次状态变化时正确触发，载荷为 list[str]
  - 空态：无可对比指标时不崩，给占位文案

运行：
    set QT_QPA_PLATFORM=offscreen
    python tests/test_param_picker.py
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

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from pred_param_selector import ParamPickerPanel  # noqa: E402


SAMPLE_PARAMS = (
    ["非甲烷总烃", "烟气温度", "烟气流量", "二氧化硫"]
    + ["pH值", "化学需氧量", "氨氮"]
    + ["未知指标X"]
)


def _make_picker(app, params):
    picker = ParamPickerPanel()
    picker.set_available_params(params)
    return picker


def test_instantiation():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    picker = ParamPickerPanel()
    for sub in ("toggle_btn", "popup", "search_edit", "_checkboxes"):
        assert hasattr(picker, sub), f"缺子组件: {sub}"
    print("[OK] 实例化 + 子组件就位")


def test_popup_is_top_level():
    """浮层必须是顶层窗口（parent=None）。

    回归锁：v5.25 曾把浮层设为 `QWidget(self)` + Qt.Popup，使其位于"隐藏的预测页签"
    内；打开预测页签时 Qt 为这个带顶层标志的子控件创建原生窗口而父级尚未窗口化，
    在 Win7 下直接段错误闪退。改为 parent=None 的顶层弹窗后，隐藏时不创建 HWND，
    仅点击展开时作为独立顶层窗口显示，彻底规避。
    """
    app = QApplication.instance() or QApplication(sys.argv[:1])
    picker = ParamPickerPanel()
    assert picker.popup.parent() is None, \
        f"浮层必须是顶层窗口(parent=None)，实际 parent={picker.popup.parent()}"
    assert picker.popup.windowFlags() & Qt.Popup == Qt.Popup, \
        "浮层应带 Qt.Popup 顶层标志"
    print("[OK] 浮层为顶层窗口(Qt.Popup, parent=None) — 规避 Win7 打开预测页签闪退")


def test_set_available_params_dedup():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    picker = _make_picker(app, ["A", "B", "A", "C", "B"])
    assert picker.total_count() == 3
    assert picker.get_selected() == []
    print("[OK] set_available_params 去重保序")


def test_select_get_roundtrip():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    picker = _make_picker(app, SAMPLE_PARAMS)
    picker.set_selected(["非甲烷总烃", "pH值", "未知指标X"])
    sel = picker.get_selected()
    assert sel == ["非甲烷总烃", "pH值", "未知指标X"], f"got {sel}"
    picker.set_selected([])
    assert picker.get_selected() == []
    print("[OK] set_selected → get_selected 往返")


def test_classify_priority():
    """分类优先级：gas/water 首要标签优先于 rax；未知归 limbo。"""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    picker = _make_picker(app, SAMPLE_PARAMS)
    # 烟气温度 既在 RIGHT_AXIS 也在 gas → 归 gas（不进 rax）
    assert picker._classify("烟气温度") == "gas"
    # pH值 既在 RIGHT_AXIS 也在 water → 归 water
    assert picker._classify("pH值") == "water"
    # 水温 既在 RIGHT_AXIS 也在 water → 归 water
    assert picker._classify("水温") == "water"
    # 未知指标不在任何映射 → limbo
    assert picker._classify("未知指标X") == "limbo"
    print("[OK] _classify 优先级（gas/water > rax > limbo）")


def test_search_filter():
    """输入"烟" → 仅含"烟"的勾选项可见。"""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    picker = _make_picker(app, SAMPLE_PARAMS)
    picker.popup.show()  # 浮层未显示时子控件 isVisible 恒为 False

    picker.search_edit.setText("烟")
    app.processEvents()

    visible = [p for p, cb in picker._checkboxes.items() if cb.isVisible()]
    assert visible, "搜索后应至少有一个可见项"
    assert all("烟" in p for p in visible), visible
    assert "pH值" not in visible
    assert "化学需氧量" not in visible
    print(f"[OK] 搜索过滤-烟（{visible}）")


def test_select_all_invert_clear():
    """全选 → 清空后 selected=[]；反选应反转全局。"""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    picker = _make_picker(app, SAMPLE_PARAMS)

    picker.select_all()
    app.processEvents()
    assert picker.selected_count() == len(SAMPLE_PARAMS), \
        f"全选后 selected={picker.selected_count()} 应 == {len(SAMPLE_PARAMS)}"

    picker.clear_selection()
    app.processEvents()
    assert picker.selected_count() == 0, "清空后 selected 应 = 0"

    picker.set_selected(["非甲烷总烃", "pH值"])
    picker.invert()
    app.processEvents()
    sel = picker.get_selected()
    assert "非甲烷总烃" not in sel
    assert "pH值" not in sel
    assert "二氧化硫" in sel  # 反选后应包含原未选中的
    print("[OK] 全选/清空/反选")


def test_selected_changed_signal():
    """selected_changed 信号在每次状态改变时正确触发。"""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    picker = _make_picker(app, SAMPLE_PARAMS)

    captured = []
    picker.selected_changed.connect(lambda s: captured.append(list(s)))

    picker.set_selected(["非甲烷总烃"])
    assert len(captured) == 1 and captured[0] == ["非甲烷总烃"]
    picker.clear_selection()
    assert len(captured) == 2 and captured[1] == []
    picker.select_all()
    assert len(captured) == 3
    assert set(captured[2]) == set(SAMPLE_PARAMS)
    print(f"[OK] selected_changed 信号触发次数={len(captured)}")


def test_empty_state():
    """无可用指标 / 搜索无匹配 时仍能正常显示占位（不崩）。"""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    picker = ParamPickerPanel()
    picker.set_available_params([])
    app.processEvents()
    assert picker._checkboxes == {}, "无指标时不应有勾选项"
    assert picker.get_selected() == []

    # 有指标但搜索无匹配 → 所有勾选项隐藏
    picker.set_available_params(SAMPLE_PARAMS)
    picker.popup.show()
    picker.search_edit.setText("__no_match__")
    app.processEvents()
    visible = [p for p, cb in picker._checkboxes.items() if cb.isVisible()]
    assert visible == [], f"无匹配时应全部隐藏，got {visible}"
    print("[OK] 空态/无匹配不崩")


def main():
    print("=== ParamPickerPanel 单测 ===")
    QApplication.instance() or QApplication(sys.argv[:1])

    failures = []
    tests = [
        test_instantiation,
        test_popup_is_top_level,
        test_set_available_params_dedup,
        test_select_get_roundtrip,
        test_classify_priority,
        test_search_filter,
        test_select_all_invert_clear,
        test_selected_changed_signal,
        test_empty_state,
    ]
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failures.append(t.__name__)
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] {t.__name__}: {type(e).__name__}: {e}")
            failures.append(t.__name__)

    if failures:
        print(f"\n=== 单测未通过：{len(failures)}/{len(tests)} ===")
        print(f"  失败项: {failures}")
        return 1
    print(f"\n=== 全部 {len(tests)} 项单测通过 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
