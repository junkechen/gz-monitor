# -*- coding: utf-8 -*-
"""v5.76 历史基准 = 参与时段的日排放平均值（与网页核对）

用户反馈：软件显示的历史基准与网页查询有差异。原因：
1. 界面/导出显示的是 predicted（基线 × 自学习偏差），不是纯日均；
2. 0 排放天（停产/达标零排放）被当作无效值丢弃，导致平均值偏高。
修复后 baseline 为纯算术平均，并回填参与天数/合计供核对。
"""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from data_processor import (  # noqa: E402
    predict_daily_emission, set_custom_baseline, _compute_daily_baseline,
)


class TestBaselineDetail(unittest.TestCase):

    def tearDown(self):
        set_custom_baseline({})

    def _run(self, vals, dates, **kw):
        return predict_daily_emission(
            vals, horizon_days=2, dates=dates, baseline_mode='custom',
            accumulate_feedback=False, apply_correction=False, **kw)

    def test_range_baseline_is_daily_average(self):
        set_custom_baseline({'range_enabled': True,
                             'range_start': '2026-10-01 08:30',
                             'range_end': '2026-10-03 18:00'})
        res = self._run([10.0, 20.0, 30.0, 40.0],
                        ['2026-09-30', '2026-10-01', '2026-10-02', '2026-10-03'])
        self.assertAlmostEqual(res['baseline'], 30.0)   # (20+30+40)/3
        self.assertEqual(res['baseline_days'], 3)
        self.assertAlmostEqual(res['baseline_total'], 90.0)

    def test_zero_emission_day_counted(self):
        """0 排放是有效真实值，必须计入日均（旧实现丢弃 → 均值偏高）"""
        set_custom_baseline({'range_enabled': True,
                             'range_start': '2026-10-01 00:00',
                             'range_end': '2026-10-03 23:59'})
        res = self._run([0.0, 10.0, 20.0],
                        ['2026-10-01', '2026-10-02', '2026-10-03'])
        self.assertAlmostEqual(res['baseline'], 10.0)

    def test_baseline_not_polluted_by_calibration(self):
        """自学习偏差只影响预测值，不影响"历史基准"展示值"""
        set_custom_baseline({'range_enabled': True,
                             'range_start': '2026-10-01 00:00',
                             'range_end': '2026-10-03 23:59'})
        with mock.patch('prediction_calibrator.get_correction',
                        return_value=(1.5, 1.0)):
            res = predict_daily_emission(
                [10.0, 20.0, 30.0], horizon_days=2,
                dates=['2026-10-01', '2026-10-02', '2026-10-03'],
                baseline_mode='custom', accumulate_feedback=False,
                apply_correction=True)
        self.assertAlmostEqual(res['baseline'], 20.0)
        self.assertAlmostEqual(res['predicted'], 30.0)   # 20 × 1.5

    def test_detail_out_param_other_modes(self):
        detail = {}
        base, label = _compute_daily_baseline(
            [5.0, 15.0], ['2026-11-06', '2026-11-07'], 'prev_day', detail)
        self.assertAlmostEqual(base, 15.0)
        self.assertEqual(detail['days'], 2)
        self.assertAlmostEqual(detail['total'], 20.0)


class TestDailyTableShowsBaseline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        import main_window as mw
        from multi_account_api import GZMultiAccountClient
        cls._app = QApplication.instance() or QApplication(sys.argv)
        cls.win = mw.MainWindow(GZMultiAccountClient())

    @classmethod
    def tearDownClass(cls):
        from PyQt5.QtCore import QTimer
        for t in cls.win.findChildren(QTimer):
            t.stop()
        cls.win.close()

    def test_table_uses_baseline_value_not_calibrated(self):
        p = {'ent_name': '测试企业', 'subname': '排口1', 'param': '非甲烷总烃',
             'pred_type': '日排放量预测', 'predicted': 15.0,
             'baseline_value': 10.0, 'baseline_days': 3,
             'baseline_total': 30.0, 'baseline_label': '时段...',
             'future_daily': [11.0, 12.0],
             'future_dates': ['2026-11-08', '2026-11-09'],
             'confidences': [0.8, 0.7], 'trend': 'stable', 'trend_rate': 0,
             'confidence': 0.8, 'warning_level': '正常', 'is_emission': True,
             'last_actual': 9.5, 'last_actual_date': '2026-11-07'}
        self.win._show_daily_emission_table([p])
        txt = self.win.pred_table.item(0, 2).text()
        self.assertTrue(txt.startswith('10'), f'应显示纯日均 10，实际 {txt}')
        tip = self.win.pred_table.item(0, 2).toolTip()
        self.assertIn('参与天数：3 天', tip)
        self.assertIn('日均', tip)


if __name__ == '__main__':
    unittest.main(verbosity=2)
