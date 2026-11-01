# -*- coding: utf-8 -*-
"""v5.58 回归：预测数据导出支撑（可选基线 + 自学习校准）。

覆盖：
  - predict_daily_emission 各 baseline_mode 均产出合法结果；
  - 自定义基线（set_custom_baseline）生效；
  - 自学习校准器：注入偏差样本后 get_correction 返回修正系数（零样本时为 (1.0,1.0)）。
"""
import os
import sys
import shutil
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from data_processor import (
    predict_daily_emission, _compute_daily_baseline, set_custom_baseline,
)
from prediction_calibrator import (
    record_sample, get_correction, get_stats, reset_calibration, _state_path,
)


def _make_history(n=40):
    """构造带日期的历史日排放量（含周末，便于工作日过滤）。"""
    base = datetime.date(2026, 1, 1)
    vals, dates = [], []
    for i in range(n):
        d = base + datetime.timedelta(days=i)
        vals.append(round(100 + 10 * (i % 7) + i * 0.5, 2))
        dates.append(d.strftime('%Y-%m-%d'))
    return vals, dates


def test_daily_baseline_modes():
    vals, dates = _make_history()
    for mode in ['auto', 'prev_day', 'last_10_workdays', 'all_history', 'custom']:
        r = predict_daily_emission(
            vals, horizon_days=7, dates=dates, baseline_mode=mode,
            accumulate_feedback=False, apply_correction=False)
        assert r.get('predicted') is not None, f"mode={mode} 预测值为空"
        assert len(r.get('future_daily', [])) == 7, f"mode={mode} 天数不对"
        assert isinstance(r.get('baseline_mode'), str) and r['baseline_mode']
    # 自定义默认配置（上一天+前10工作日）应与 auto 一致
    set_custom_baseline({'use_prev_day': True, 'use_last_n_workdays': 10,
                         'use_all_history': False})
    b1, l1 = _compute_daily_baseline(vals, dates, 'custom')
    b2, l2 = _compute_daily_baseline(vals, dates, 'auto')
    assert abs(b1 - b2) < 1e-6, "自定义默认应与 auto 一致"


def test_custom_baseline_3_workdays():
    vals, dates = _make_history()
    set_custom_baseline({'use_prev_day': False, 'use_last_n_workdays': 3,
                         'use_all_history': False})
    b, label = _compute_daily_baseline(vals, dates, 'custom')
    # 直接计算末尾3个工作日
    work = []
    for i, v in enumerate(vals):
        d = datetime.date(2026, 1, 1) + datetime.timedelta(days=i)
        if d.weekday() < 5:
            work.append(v)
    expected = sum(work[-3:]) / 3
    assert abs(b - expected) < 1e-6, f"自定义3工作日基线应={expected}, 实际={b}"
    assert '前3个工作日' in label


def test_calibration_zero_sample_neutral():
    reset_calibration()
    try:
        bias, conf = get_correction('小时', 1)
        assert (bias, conf) == (1.0, 1.0), "无样本应为中性 (1.0, 1.0)"
    finally:
        reset_calibration()


def test_calibration_learns_bias():
    reset_calibration()
    try:
        # 注入 20 个「实际偏低 10%」的样本
        for _ in range(20):
            record_sample('小时', 1, 100.0, 90.0, 0.8)
        # 触发重算（节流：强制 flush）
        from prediction_calibrator import flush_now
        flush_now()
        s = get_stats()
        assert s['samples'] == 20, f"样本数应为20, 实际={s['samples']}"
        bias, conf = get_correction('小时', 1)
        # 偏差比 = 90/100 = 0.9 → bias 应≈0.9（钳制内）
        assert 0.8 <= bias <= 1.0, f"bias 应≈0.9(修正偏高), 实际={bias}"
        assert s['groups'] >= 1, "应至少校准1组"
    finally:
        # 清理：避免污染仓库 data 目录
        reset_calibration()
        p = _state_path()
        for suffix in ('', '.tmp'):
            try:
                os.remove(p + suffix)
            except OSError:
                pass


if __name__ == '__main__':
    test_daily_baseline_modes()
    test_custom_baseline_3_workdays()
    test_calibration_zero_sample_neutral()
    test_calibration_learns_bias()
    print("ALL v5.58 PREDICTION TESTS PASSED")
