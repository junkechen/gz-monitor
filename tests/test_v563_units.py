# -*- coding: utf-8 -*-
"""v5.63 回归测试：排放量口径与流量参数选择。

覆盖：
  1. pick_flow_code 按数据可用性选流量（492 无值时用 494）
  2. 历史表排放量单位标注为 kg（不再误标 mg/m³）
  3. 日预测异常值过滤时值与日期保持对齐
"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'src'))

from param_units import (  # noqa: E402
    pick_flow_code, find_flow_code, calc_emission_mass, is_concentration_param,
)
from data_processor import predict_daily_emission  # noqa: E402


class TestFlowPick(unittest.TestCase):

    def test_pick_494_when_492_empty(self):
        rows = [
            {'DateTime': '2026-11-01', 'val_492': None, 'val_494': 24.5,
             'val_495': 1921748.6},
            {'DateTime': '2026-11-02', 'val_492': '', 'val_494': 25.1,
             'val_495': 1921800.0},
        ]
        codes = ['301', '316', '492', '495', '494', '311', '302']
        self.assertEqual(find_flow_code(codes), '492')     # 旧逻辑
        self.assertEqual(pick_flow_code(rows, codes), '494')  # 新逻辑跳过空值

    def test_pick_keeps_492_when_has_value(self):
        rows = [{'val_492': 60.0, 'val_494': 2.5}]
        self.assertEqual(pick_flow_code(rows, ['492', '494']), '492')

    def test_gas_flow_210(self):
        rows = [{'val_210': 100.0}]
        self.assertEqual(pick_flow_code(rows, ['210', '209']), '210')

    def test_no_flow_param(self):
        self.assertIsNone(pick_flow_code([{'val_201': 1}], ['201', '203']))


class TestEmissionUnit(unittest.TestCase):

    def test_exhaust_gas_kg(self):
        # 16.35 mg/m³ × 128,600 m³ / 1e6 ≈ 2.10 kg（与网页端口径一致）
        v = calc_emission_mass(16.35, 128600, '203')
        self.assertAlmostEqual(v, 2.10261, places=4)

    def test_wastewater_kg(self):
        # 0.0133 mg/L × 64.4 m³ / 1e3 ≈ 0.00086 kg
        v = calc_emission_mass(0.0133, 64.4, '311')
        self.assertAlmostEqual(v, 0.00085652, places=8)

    def test_non_concentration_has_no_emission(self):
        for code in ('209', '210', '211', '525', '526', '527', '302'):
            self.assertFalse(is_concentration_param(code))
            self.assertIsNone(calc_emission_mass(10, 100, code))


class TestDailyAlignment(unittest.TestCase):

    def test_outlier_filter_keeps_dates_aligned(self):
        # 最后一天为异常尖峰；过滤后「上一天」应为正常值而非 900
        vals = [10, 12, 11, 13, 12, 14, 13, 15, 14, 16, 15, 17, 900]
        base = datetime.date(2026, 10, 1)
        dates = [(base + datetime.timedelta(days=i)).strftime('%Y-%m-%d')
                 for i in range(len(vals))]
        r = predict_daily_emission(vals, horizon_days=3, dates=dates,
                                   baseline_mode='prev_day',
                                   apply_correction=False)
        self.assertLess(r['predicted'], 30,
                        "异常尖峰应被过滤，基线不应接近 900")
        self.assertGreater(r['predicted'], 10)


if __name__ == '__main__':
    unittest.main(verbosity=2)
