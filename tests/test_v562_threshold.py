# -*- coding: utf-8 -*-
"""v5.62 回归测试：元组阈值不应导致预测抛 TypeError。

背景：self.thresholds 中部分参数存的是 (下限, 上限) 元组，
小时预测直接 `threshold > 0` 比较 → TypeError，整个排放口预测被跳过。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'src'))

from data_processor import (  # noqa: E402
    predict_future_hours, predict_daily_emission, check_threshold,
    _norm_threshold,
)


class TestTupleThreshold(unittest.TestCase):

    def test_norm_threshold(self):
        self.assertEqual(_norm_threshold((0, 200)), 200.0)
        self.assertEqual(_norm_threshold([None, 50]), 50.0)
        self.assertEqual(_norm_threshold(30), 30.0)
        self.assertIsNone(_norm_threshold(None))
        self.assertIsNone(_norm_threshold(('a', 'b')))

    def test_hourly_accepts_tuple_threshold(self):
        vals = [120 + i * 0.5 for i in range(40)]
        res = predict_future_hours(vals, horizon=3, threshold=(0, 200),
                                   accumulate_feedback=False,
                                   apply_correction=False)
        self.assertEqual(len(res), 4)
        self.assertTrue(all(r['predicted'] is not None for r in res))
        # 元组上限 200 与直接传 200 的结果应一致
        res2 = predict_future_hours(vals, horizon=3, threshold=200,
                                    accumulate_feedback=False,
                                    apply_correction=False)
        self.assertEqual([r['predicted'] for r in res],
                         [r['predicted'] for r in res2])

    def test_daily_accepts_tuple_threshold(self):
        vals = [100 + i for i in range(30)]
        d = predict_daily_emission(vals, horizon_days=3, threshold=(0, 200),
                                   apply_correction=False)
        self.assertIsNotNone(d['predicted'])
        self.assertEqual(len(d['future_daily']), 3)

    def test_check_threshold_tuple(self):
        th = {'SO2': (0, 200)}
        self.assertFalse(check_threshold(150, 'SO2', th))
        self.assertTrue(check_threshold(250, 'SO2', th))
        self.assertFalse(check_threshold(250, 'NOx', th))


if __name__ == '__main__':
    unittest.main(verbosity=2)
