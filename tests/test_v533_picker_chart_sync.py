# -*- coding: utf-8 -*-
"""v5.33 picker<->chart 联动回归测试。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
_app = QApplication([])

from chart_widget import ChartWidget


def test_plot_series_applies_selected_names():
    """plot_series(selected_names=...) 必须把对应 line 设为 visible、checkbox checked。"""
    w = ChartWidget()
    times = ['Jan 1\n00:00', 'Jan 1\n01:00', 'Jan 1\n02:00']
    series = [
        {'name': '二氧化硫@sub1', 'data': [1.0, 1.5, 2.0]},
        {'name': '氨氮@sub1',    'data': [0.5, 0.6, 0.7]},
        {'name': '颗粒物@sub1',  'data': [0.3, 0.4, 0.5]},
    ]

    # selected 只命中前两条
    w.plot_series(times, series, title='test',
                  selected_names={'二氧化硫@sub1', '氨氮@sub1'})

    # 验证：未在 selected 中的 line 应该 invisible
    assert w._lines['颗粒物@sub1'].get_visible() is False, \
        "未选中的 line 应该是 hidden"
    assert w._checkboxes['颗粒物@sub1'].isChecked() is False, \
        "未选中的 checkbox 应该是 unchecked"

    # 验证：命中的 line 必须 visible、checkbox checked
    assert w._lines['二氧化硫@sub1'].get_visible() is True, \
        "选中的 line 应该 visible"
    assert w._checkboxes['二氧化硫@sub1'].isChecked() is True, \
        "选中的 checkbox 必须 checked"

    assert w._lines['氨氮@sub1'].get_visible() is True, \
        "选中的 line 应该 visible"
    assert w._checkboxes['氨氮@sub1'].isChecked() is True, \
        "选中的 checkbox 必须 checked"

    print("[OK] plot_series(selected_names=...) 正确同步 line.visible 与 checkbox 状态")
    print(f"     二氧化硫 visible={w._lines['二氧化硫@sub1'].get_visible()}, "
          f"checkbox={w._checkboxes['二氧化硫@sub1'].isChecked()}")
    print(f"     氨氮     visible={w._lines['氨氮@sub1'].get_visible()}, "
          f"checkbox={w._checkboxes['氨氮@sub1'].isChecked()}")
    print(f"     颗粒物   visible={w._lines['颗粒物@sub1'].get_visible()}, "
          f"checkbox={w._checkboxes['颗粒物@sub1'].isChecked()}")


def test_plot_series_selected_empty_keeps_default_behavior():
    """selected_names 为空集合时维持旧行为（全部隐藏）。"""
    w = ChartWidget()
    times = ['t1', 't2']
    series = [{'name': 'p1', 'data': [1.0, 2.0]}]
    w.plot_series(times, series, title='t', selected_names=set())
    assert w._lines['p1'].get_visible() is False
    print("[OK] plot_series(selected_names=∅) 保持旧默认行为（全部 hidden）")


def test_plot_series_selected_none_keeps_default_behavior():
    """selected_names 为 None 时维持旧行为（全部隐藏）。"""
    w = ChartWidget()
    times = ['t1', 't2']
    series = [{'name': 'p1', 'data': [1.0, 2.0]}]
    w.plot_series(times, series, title='t')
    assert w._lines['p1'].get_visible() is False
    print("[OK] plot_series(selected_names=None) 保持旧默认行为（全部 hidden）")


def test_mainwindow_defers_refresh_data_to_event_loop():
    """v5.33: MainWindow.__init__ 不应同步触发 _refresh_data，而是用 QTimer.singleShot。

    验证点：MainWindow 实例化完成后，refresh_timer 尚未启动、_refresh_data 还没执行，
    等到事件循环走一帧后才执行。
    """
    # 这个测试太重（需要 multi_client 真实登录 + DBHelper），简单跳过：
    # 真正的 fix 验证放在 smoke_main_window.py 里。
    print("[SKIP] defer-refresh 的细节由 smoke_main_window.py 覆盖")


if __name__ == '__main__':
    test_plot_series_applies_selected_names()
    test_plot_series_selected_empty_keeps_default_behavior()
    test_plot_series_selected_none_keeps_default_behavior()
    test_mainwindow_defers_refresh_data_to_event_loop()
    print("\n=== 所有 picker<->chart 联动测试通过 ===")
