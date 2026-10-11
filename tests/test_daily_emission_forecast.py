# -*- coding: utf-8 -*-
"""
v5.46 新增：日污染物排放量预测算法单元测试

覆盖 predict_daily_emission / forecast_daily_dates 的核心行为：
  1. 空数据 / 单点数据 的健壮性
  2. 平稳序列的基线准确性
  3. 上升/下降趋势的方向识别
  4. 异常值过滤生效
  5. 负值防护与限值封顶
  6. 置信度单调衰减
  7. 预测天数与日期列表长度一致
"""

import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep + 'src')

from data_processor import predict_daily_emission, forecast_daily_dates


class TestDailyEmissionForecast(unittest.TestCase):

    # ── 1. 健壮性 ────────────────────────────────────────────────────────
    def test_a_empty_input(self):
        """空数据：应返回安全默认值，不抛异常"""
        r = predict_daily_emission([])
        self.assertIsNone(r['predicted'])
        self.assertEqual(r['data_points'], 0)
        self.assertEqual(r['trend'], 'stable')
        self.assertEqual(r['method'], 'none')

    def test_b_all_none_input(self):
        """全 None 输入：等同于空数据"""
        r = predict_daily_emission([None, None, None])
        self.assertIsNone(r['predicted'])
        self.assertEqual(r['data_points'], 0)

    def test_c_single_point(self):
        """单点数据：应能给出基线，置信度被压低"""
        r = predict_daily_emission([100.0])
        self.assertEqual(r['data_points'], 1)
        self.assertAlmostEqual(r['predicted'], 100.0, places=2)
        self.assertEqual(len(r['future_daily']), 7)
        # 单点数据置信度必须很低
        self.assertLessEqual(r['confidence'], 0.5)

    # ── 2. 平稳序列 ──────────────────────────────────────────────────────
    def test_d_stable_series(self):
        """平稳序列：基线接近真实均值，趋势判定为 stable"""
        vals = [100.0] * 10
        r = predict_daily_emission(vals, horizon_days=7)
        self.assertAlmostEqual(r['predicted'], 100.0, delta=1.0)
        self.assertEqual(r['trend'], 'stable')
        self.assertEqual(r['trend_rate'], 0.0)
        self.assertEqual(r['confidence'], 1.0)   # 完整度1.0 + 稳定性1.0

    def test_e_stable_series_future_close_to_baseline(self):
        """平稳序列的未来预测应贴近基线"""
        vals = [50.0, 52.0, 48.0, 51.0, 49.0, 50.0, 50.0, 49.0]
        r = predict_daily_emission(vals, horizon_days=5)
        for v in r['future_daily']:
            self.assertTrue(45 <= v <= 55, f"预测值 {v} 偏离基线过大")

    # ── 3. 趋势识别 ──────────────────────────────────────────────────────
    def test_f_upward_trend(self):
        """持续上升序列：趋势判定为 up，且未来值递增"""
        vals = [100.0 + i * 5 for i in range(14)]
        r = predict_daily_emission(vals, horizon_days=5)
        self.assertEqual(r['trend'], 'up')
        self.assertGreater(r['trend_rate'], 0)
        self.assertGreater(r['future_daily'][-1], r['future_daily'][0])

    def test_g_downward_trend(self):
        """持续下降序列：趋势判定为 down，且未来值递减"""
        vals = [200.0 - i * 5 for i in range(14)]
        r = predict_daily_emission(vals, horizon_days=5)
        self.assertEqual(r['trend'], 'down')
        self.assertLess(r['trend_rate'], 0)
        self.assertLess(r['future_daily'][-1], r['future_daily'][0])

    # ── 4. 异常值过滤 ────────────────────────────────────────────────────
    def test_h_outlier_filtered(self):
        """混入极端尖峰时，基线不应被尖峰带偏"""
        vals = [100.0] * 12 + [99999.0]
        r = predict_daily_emission(vals, horizon_days=3)
        # 基线应仍在 100 附近，而非被尖峰拉高
        self.assertTrue(90 <= r['predicted'] <= 115,
                        f"尖峰未被有效过滤，基线={r['predicted']}")

    # ── 5. 数值安全 ──────────────────────────────────────────────────────
    def test_i_threshold_cap(self):
        """给定限值时，预测值必须被封顶（不超过限值×1.5）"""
        vals = [100.0 + i * 20 for i in range(14)]   # 强上升
        threshold = 150.0
        r = predict_daily_emission(vals, horizon_days=7, threshold=threshold)
        cap = threshold * 1.5
        for v in r['future_daily']:
            self.assertLessEqual(v, cap + 1e-6, f"预测值 {v} 超过封顶值 {cap}")

    def test_j_no_negative_prediction(self):
        """强下降序列下预测值不得为负"""
        vals = [100.0 - i * 10 for i in range(14)]
        r = predict_daily_emission(vals, horizon_days=7)
        for v in r['future_daily']:
            self.assertGreaterEqual(v, 0.0)

    # ── 6. 置信度衰减 ────────────────────────────────────────────────────
    def test_k_confidence_monotonic_decay(self):
        """置信度必须随外推天数单调不增"""
        vals = [100.0 + (i % 3) for i in range(14)]
        r = predict_daily_emission(vals, horizon_days=10)
        confs = r['confidences']
        self.assertEqual(len(confs), 10)
        for i in range(1, len(confs)):
            self.assertLessEqual(confs[i], confs[i - 1],
                                 f"第{i+1}天置信度反而升高")

    def test_l_confidence_bounds(self):
        """置信度必须落在 [0,1] 区间内"""
        r = predict_daily_emission([10.0, 100.0, 5.0, 90.0, 12.0, 88.0, 11.0],
                                   horizon_days=7)
        self.assertTrue(0.0 <= r['confidence'] <= 1.0)
        for c in r['confidences']:
            self.assertTrue(0.0 <= c <= 1.0)

    # ── 7. 长度一致性 ────────────────────────────────────────────────────
    def test_m_horizon_length(self):
        """预测天数应严格等于 horizon_days，且各数组等长"""
        for h in (1, 3, 7, 14):
            r = predict_daily_emission([100.0] * 10, horizon_days=h)
            self.assertEqual(len(r['future_daily']), h)
            self.assertEqual(len(r['confidences']), h)

    def test_n_forecast_dates(self):
        """日期列表长度与内容格式正确，且从明天开始"""
        from datetime import timedelta

        dates = forecast_daily_dates(7)
        self.assertEqual(len(dates), 7)
        for ds in dates:
            datetime.strptime(ds, '%Y-%m-%d')   # 格式可解析
        # 首日应为明天
        expected = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        self.assertEqual(dates[0], expected)

    # ── 8. horizon 边界 ──────────────────────────────────────────────────
    def test_o_zero_horizon_clamped(self):
        """horizon=0 应被纠正为 1，避免返回空预测"""
        r = predict_daily_emission([100.0] * 5, horizon_days=0)
        self.assertEqual(len(r['future_daily']), 1)

    def test_p_threshold_none_no_cap(self):
        """threshold=None 时不做封顶"""
        vals = [100.0 + i * 30 for i in range(14)]
        r = predict_daily_emission(vals, horizon_days=7, threshold=None)
        # 无封顶时，7 天后的值应显著高于首日
        self.assertGreater(r['future_daily'][-1], r['future_daily'][0] * 1.5)


if __name__ == '__main__':
    unittest.main(verbosity=2)