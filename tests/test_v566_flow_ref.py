# -*- coding: utf-8 -*-
"""v5.66 回归测试：日预测的"当日累计流量"口径。

背景：小时数据里 val_flow 是"该小时通过量"，日均值无物理意义。
计算限值封顶与预警反推必须用**当日累计流量**(Σ 逐时流量)，
否则流量被低估 N 倍 → 预测被错误封顶、浓度反推虚高导致误报红色预警。
"""
import os
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'src'))

from PyQt5.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication([])
from main_window import PredictionWorker  # noqa: E402


ROWS = [
    {'DateTime': '2026-11-01 01:00', 'val_316': 20.0, 'val_494': 10.0},
    {'DateTime': '2026-11-01 02:00', 'val_316': 20.0, 'val_494': 20.0},
    {'DateTime': '2026-11-01 03:00', 'val_316': 20.0, 'val_494': 30.0},
]


class TestDailyFlowSum(unittest.TestCase):

    def test_flowsum_recorded(self):
        agg = PredictionWorker._aggregate_hour_rows_to_daily(ROWS)[0]
        self.assertAlmostEqual(agg['flowsum_494'], 60.0)

    def test_emission_sum(self):
        agg = PredictionWorker._aggregate_hour_rows_to_daily(ROWS)[0]
        # (20*10 + 20*20 + 20*30)/1000 = 1.2 kg
        self.assertAlmostEqual(agg['emis_316'], 1.2, places=6)

    def test_concentration_backcalc(self):
        """排放量 ÷ 当日累计流量 → 浓度，应与实测浓度一致。"""
        agg = PredictionWorker._aggregate_hour_rows_to_daily(ROWS)[0]
        conc = agg['emis_316'] * 1000 / agg['flowsum_494']
        self.assertAlmostEqual(conc, 20.0, places=6)
        # 若误用小时均值(20)会得到 60 mg/L，虚高 3 倍
        wrong = agg['emis_316'] * 1000 / agg['val_494']
        self.assertAlmostEqual(wrong, 60.0, places=6)


if __name__ == '__main__':
    unittest.main(verbosity=2)
