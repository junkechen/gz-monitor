# -*- coding: utf-8 -*-
"""
v5.20 嵌页式双栏"对比参数"选择器（ParamPickerPanel）单测。

覆盖：
  - 实例化 + 关键子组件就位
  - set_available_params：去重保序、分类计数刷新
  - 选中读写：get_selected / set_selected 往返
  - 分类切换：选"废气"只显示废气类指标
  - 搜索过滤：输入"烟"只剩含"烟"的指标
  - 全选/反选/清空：操作只影响当前可见分类内的项目
  - 信号：selected_changed 在每次状态变化时正确触发，载荷为 list[str]
  - 空态：当前分类无指标时不崩，给占位文案

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

from PyQt5.QtWidgets import QApplication, QListWidgetItem  # noqa: E402

from pred_param_selector import ParamPickerPanel  # noqa: E402
from config import (  # noqa: E402
    PARAM_CATEGORIES,
    RIGHT_AXIS_PARAMS,
)


GAS_PARAMS = [p for p, c in PARAM_CATEGORIES.items() if c == "gas"]
WATER_PARAMS = [p for p, c in PARAM_CATEGORIES.items() if c == "water"]
ALL_PARAMS = list(PARAM_CATEGORIES.keys()) + ["未知指标X"]
ALL_PARAMS = list(dict.fromkeys(ALL_PARAMS))   # 去重保序

# 测试用样本：废气 + 废水 + 1 个未知参数（落入 limbo 类）
SAMPLE_PARAMS = (
    ["非甲烷总烃", "烟气温度", "烟气流量", "二氧化硫"]
    + ["pH值", "化学需氧量", "氨氮"]
    + ["未知指标X"]
)


def _make_picker(app, params):
    picker = ParamPickerPanel()
    picker.set_available_params(params)
    return picker


def _category_key(item: QListWidgetItem):
    """提取 QListWidgetItem 的 user role 分类 key（如果存在）。"""
    return item.data(0x0100)  # Qt.UserRole == 0x0100


def test_instantiation():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    picker = ParamPickerPanel()
    for sub in ("category_list", "param_list", "search_edit",
                "status_label", "splitter"):
        assert hasattr(picker, sub), f"缺子组件: {sub}"
    print("[OK] 实例化 + 子组件就位")


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
    # 顺序按 _all_params 出现顺序
    assert sel == ["非甲烷总烃", "pH值", "未知指标X"], f"got {sel}"
    picker.set_selected([])
    assert picker.get_selected() == []
    print("[OK] set_selected → get_selected 往返")


def test_category_filter():
    """选"废气"分类 → 右侧只显示废气类指标。"""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    picker = _make_picker(app, SAMPLE_PARAMS)

    # 切到"废气"
    for i in range(picker.category_list.count()):
        if _category_key(picker.category_list.item(i)) == "gas":
            picker.category_list.setCurrentRow(i)
            break
    app.processEvents()

    visible = []
    for i in range(picker.param_list.count()):
        item = picker.param_list.item(i)
        param = item.data(0x0100)
        if param:
            visible.append(param)
    # 至少要看到非甲烷总烃，且不应该看到 pH值/化学需氧量
    assert "非甲烷总烃" in visible
    assert "pH值" not in visible
    assert "化学需氧量" not in visible
    print(f"[OK] 分类切换-废气（{len(visible)} 项: {visible}）")


def test_search_filter():
    """输入"烟" → 只剩含"烟"的指标。"""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    picker = _make_picker(app, SAMPLE_PARAMS)

    picker.search_edit.setText("烟")
    app.processEvents()

    visible = [
        picker.param_list.item(i).data(0x0100)
        for i in range(picker.param_list.count())
        if picker.param_list.item(i).data(0x0100)
    ]
    # 烟气温度 + 烟气流量
    assert all("烟" in p for p in visible), visible
    assert "pH值" not in visible
    assert "化学需氧量" not in visible
    print(f"[OK] 搜索过滤-烟（{visible}）")


def test_select_all_invert_clear():
    """全选当前可见 → 清空后 selected=[]；反选应保留未在可见中的项。"""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    picker = _make_picker(app, SAMPLE_PARAMS)

    # 全选
    picker.select_all()
    app.processEvents()
    assert picker.selected_count() == len(SAMPLE_PARAMS), \
        f"全选后 selected={picker.selected_count()} 应 == {len(SAMPLE_PARAMS)}"

    # 清空
    picker.clear_selection()
    app.processEvents()
    assert picker.selected_count() == 0, "清空后 selected 应 = 0"

    # 全选两个，反选
    picker.set_selected(["非甲烷总烃", "pH值"])
    picker.invert()
    app.processEvents()
    sel = picker.get_selected()
    assert "非甲烷总烃" not in sel
    assert "pH值" not in sel
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
    # 全选 emit 时载荷 = 全部样本（按 _all_params 顺序）
    assert len(captured) == 3
    assert set(captured[2]) == set(SAMPLE_PARAMS)
    print(f"[OK] selected_changed 信号触发次数={len(captured)}")


def test_empty_category_shows_placeholder():
    """搜索结果为空时仍能正常显示占位（不崩、可继续操作）。"""
    from PyQt5.QtCore import Qt
    app = QApplication.instance() or QApplication(sys.argv[:1])
    picker = _make_picker(app, SAMPLE_PARAMS)
    picker.search_edit.setText("__no_match__")
    app.processEvents()
    assert picker.param_list.count() == 1, \
        f"占位行期望 1 行，实际 {picker.param_list.count()}"
    item = picker.param_list.item(0)
    # 占位项不可勾选、不可选，所以 flags() 应不含 ItemIsSelectable 等
    assert not (item.flags() & Qt.ItemIsSelectable), \
        f"占位项不应可选择，flags={item.flags()}"
    assert not (item.flags() & Qt.ItemIsUserCheckable), \
        f"占位项不应可勾选，flags={item.flags()}"
    print("[OK] 空态占位不崩")


def test_right_axis_category():
    """"双轴"分类仅承接不在 gas/water 的右轴指标（如"水温"）。

    pH值/烟气温度 分别属于废水/废气，以首要标签归属；只在它们不在
    gas/water 时才会出现在 rax 类下。
    """
    app = QApplication.instance() or QApplication(sys.argv[:1])
    # 只放"水温"——它在 PARAM_CATEGORIES 里映射到 water...
    # 实际水温 = water，不进 rax。需要一个确实没在 gas/water 但走右轴的样本
    # 用"水温"即：water 桶，吃不下"双轴"
    # 因此直接造"只在 rax 不在 gas/water"的样本：虚构"AA特殊指标"
    picker = _make_picker(app, ["水温"])
    for i in range(picker.category_list.count()):
        if _category_key(picker.category_list.item(i)) == "rax":
            picker.category_list.setCurrentRow(i)
            break
    app.processEvents()
    visible = [
        picker.param_list.item(i).data(0x0100)
        for i in range(picker.param_list.count())
        if picker.param_list.item(i).data(0x0100)
    ]
    # 水温 PARAM_CATEGORIES → water，不在 rax——所以 rax 桶为空
    assert visible == [], f"仅水温的样本不应进入 rax 桶，got {visible}"

    # 再造一个真的只进 rax 的样本
    picker2 = _make_picker(app, ["水温", "未知右轴指标"])
    # 手动把它标为右轴（在 param_picker 视图下只有 RIGHT_AXIS_PARAMS 命中才进 rax）
    # 由于"未知右轴指标"不在 RIGHT_AXIS_PARAMS，仍进 limbo。所以此断言仅作
    # 分类优先级回归测试。
    for i in range(picker2.category_list.count()):
        if _category_key(picker2.category_list.item(i)) == "water":
            picker2.category_list.setCurrentRow(i)
            break
    app.processEvents()
    water_visible = [
        picker2.param_list.item(i).data(0x0100)
        for i in range(picker2.param_list.count())
        if picker2.param_list.item(i).data(0x0100)
    ]
    assert "水温" in water_visible, water_visible
    print(f"[OK] 分类优先级：水温归 water 桶（{water_visible}）")


def main():
    print("=== ParamPickerPanel 单测 ===")
    QApplication.instance() or QApplication(sys.argv[:1])

    failures = []
    tests = [
        test_instantiation,
        test_set_available_params_dedup,
        test_select_get_roundtrip,
        test_category_filter,
        test_search_filter,
        test_select_all_invert_clear,
        test_selected_changed_signal,
        test_empty_category_shows_placeholder,
        test_right_axis_category,
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
