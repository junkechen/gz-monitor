# -*- coding: utf-8 -*-
"""
v5.53 回归测试：修复用户反馈的 4 个问题

1) 排放量显示 "--"（无数字）
   根因：实时表里「补充参数」（实时接口未返回、由最近 2 小时历史补齐的行）
   写入 filtered_params 时**漏了 'code' 字段**，导致 find_flow_code 找不到流量行、
   flow_value 恒为 None，所有浓度参数排放量都算不出来。
2) 运行 1 分钟后闪退
   根因：预测定时器 60s 触发 `_on_prediction_worker_done` 槽，槽内无异常护栏；
   PyQt5 会把槽内未捕获异常转成 qFatal → abort() 直接杀进程（crash.log 无 CLEAN_EXIT）。
   同时多线程共享 dict 缓存存在并发读写风险。
3) 历史表格文字显示不全
4) 左侧排放口名称显示不全

运行：C:/Python38/python.exe tests/test_v553_fixes.py
"""
import os
import sys
import inspect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import main_window as mw
from param_units import calc_emission_rate, format_emission_rate


# ── 1. 补充参数必须带 code ──────────────────────────────────────────────────
def test_supplement_param_carries_code():
    """_show_sub_realtime 补充历史参数时必须写 'code'，否则流量匹配失败。"""
    src = inspect.getsource(mw.MainWindow._show_sub_realtime)
    assert "'code': code," in src, (
        "v5.53 修复要求补充参数 dict 含 'code' 字段；"
        "缺失会导致流量参数匹配不上、排放量全为 '--'。"
    )
    print("[OK] 补充参数已携带 code 字段")


# ── 2. 流量兜底 + 非法流量保护 ───────────────────────────────────────────────
def test_flow_fallback_and_guard():
    src = inspect.getsource(mw.MainWindow._show_sub_realtime)
    assert "hist_latest.get(flow_code)" in src, (
        "v5.53 要求：排口无流量行时用补充历史数据兜底取流量"
    )
    assert "flow_value <= 0" in src, (
        "v5.53 要求：-9999/0 等无效流量不得参与排放量计算"
    )
    print("[OK] 流量兜底与无效值保护已就位")


def test_history_flow_guard():
    src = inspect.getsource(mw.MainWindow._display_history_table)
    assert "return v if v > 0 else None" in src, (
        "v5.53 要求：历史表流量同样过滤 -9999/0"
    )
    print("[OK] 历史表流量无效值保护已就位")


def test_emission_formula_with_cumulative_flow():
    """网页口径复核：16.0 mg/m³ × 142431 m³ / 1e6 = 2.279 kg"""
    v = calc_emission_rate(16.0, 142431, '201')
    assert abs(v - 2.278896) < 1e-6, v
    assert format_emission_rate(v) == '2.279', format_emission_rate(v)
    # 非浓度参数不可算
    assert calc_emission_rate(16.0, 142431, '525') is None
    print("[OK] 排放量公式与累计流量口径复核通过")


# ── 3. 槽函数异常护栏（防 qFatal 闪退）────────────────────────────────────────
def test_prediction_done_slot_has_guard():
    """预测完成槽必须有 BaseException 护栏，否则 PyQt5 直接 abort。"""
    src = inspect.getsource(mw.MainWindow._on_prediction_worker_done)
    assert "except BaseException" in src, "预测完成槽缺少 BaseException 护栏"
    assert "_on_prediction_worker_done_impl" in src, "预测完成槽未委托到 impl"
    print("[OK] 预测完成槽已加异常护栏")


def test_slot_guard_swallows_exception():
    """护栏真的能吞掉异常（不向外抛）。"""
    class Dummy:
        logger = None

        def _on_prediction_worker_done_impl(self, *a, **k):
            raise ValueError("模拟绘图异常")

    d = Dummy()
    # 不应抛出
    mw.MainWindow._on_prediction_worker_done(d, [], '小时数据预测', True)
    print("[OK] 护栏成功吞掉槽内异常")


def test_other_slots_guarded():
    guarded = [
        '_on_tab_changed',
        '_on_sub_selected',
        '_on_hist_result',
        '_on_hist_fetch_finished',
        '_on_refresh_worker_finished',
        '_auto_update_prediction',
        '_auto_refresh_prediction',
    ]
    for name in guarded:
        fn = getattr(mw.MainWindow, name, None)
        assert fn is not None, f"缺少方法 {name}"
        src = inspect.getsource(fn)
        assert 'except BaseException' in src or 'except Exception' in src, (
            f"{name} 缺少异常护栏"
        )
    print("[OK] 关键信号槽均带异常护栏")


# ── 4. 缓存线程锁 ───────────────────────────────────────────────────────────
def test_cache_lock_passed_to_worker():
    """PredictionWorker 必须拿到共享缓存锁，避免并发读写 dict 崩溃。"""
    params = inspect.signature(mw.PredictionWorker.__init__).parameters
    assert 'cache_lock' in params, "PredictionWorker 缺少 cache_lock 参数"
    src_run = inspect.getsource(mw.PredictionWorker.run)
    assert '_cache_lock' in src_run, "PredictionWorker.run 未使用缓存锁"
    print("[OK] 预测 worker 已接入缓存锁")


def test_mainwindow_has_cache_lock():
    src = inspect.getsource(mw.MainWindow.__init__)
    assert 'self._cache_lock' in src, "MainWindow 未初始化 _cache_lock"
    print("[OK] MainWindow 已初始化共享缓存锁")


# ── 5. 表格显示（文字/名称不截断）───────────────────────────────────────────
def test_history_table_wraps_text():
    src = inspect.getsource(mw.MainWindow._display_history_table)
    assert 'setWordWrap(True)' in src, "历史表未开启文字换行"
    assert 'ResizeToContents' in src, "历史表未按内容自适应列宽"
    assert 'resizeRowsToContents()' in src, "历史表未按内容自适应行高"
    print("[OK] 历史表格已开启换行/自适应")


def test_realtime_and_sub_list_wrap_text():
    rt = inspect.getsource(mw.MainWindow._show_sub_realtime)
    assert 'resizeRowsToContents()' in rt, "实时表未按内容自适应行高"
    init_ui = inspect.getsource(mw.MainWindow._init_ui)
    assert 'self.sub_list.setWordWrap(True)' in init_ui, "排放口列表未开启换行"
    upd = inspect.getsource(mw.MainWindow._update_sub_list)
    assert 'setToolTip' in upd, "排放口名称缺少 Tooltip"
    assert 'resizeRowsToContents()' in upd, "排放口列表未按内容自适应行高"
    print("[OK] 实时表/排放口列表显示策略已修正")


if __name__ == '__main__':
    test_supplement_param_carries_code()
    test_flow_fallback_and_guard()
    test_history_flow_guard()
    test_emission_formula_with_cumulative_flow()
    test_prediction_done_slot_has_guard()
    test_slot_guard_swallows_exception()
    test_other_slots_guarded()
    test_cache_lock_passed_to_worker()
    test_mainwindow_has_cache_lock()
    test_history_table_wraps_text()
    test_realtime_and_sub_list_wrap_text()
    print("\n=== v5.53 修复回归测试全部通过 ===")