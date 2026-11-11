# -*- coding: utf-8 -*-
"""v5.77 用官网导出数据核对基准（单位 t→kg、含峰值天、缺数天不计 0）

依据用户提供的官网导出：
历史数据_山东冠洲鼎鑫板材科技有限公司鼎鑫彩涂4#_2026-11-02 至 2026-11-08.xls
非甲烷总烃 排放量(t) 逐日：
  11-02 0.00182 / 11-03 0.00103 / 11-04 0.00101 / 11-05 0.00106
  11-06 0.00103 / 11-07 0.00597 / 11-08 0.00104  累计 0.013 t
换算 kg（1 t = 1000 kg）：合计 12.96 kg，日均 1.851 kg/天。
旧版软件得到 0.997 kg/天（6 天合计 ÷ 7），差异来自：
  ① 11-07 缺数被按 0 计入；② 服务端排放量单位可能是吨。
"""
import os
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from data_processor import predict_daily_emission, set_custom_baseline  # noqa: E402
from param_units import extract_emission_mass, calc_emission_mass  # noqa: E402

# 官网导出值（吨）
WEB_T = [0.00182, 0.00103, 0.00101, 0.00106, 0.00103, 0.00597, 0.00104]
WEB_KG = [v * 1000 for v in WEB_T]
WEB_DATES = ['2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05',
             '2026-11-06', '2026-11-07', '2026-11-08']


class TestBaselineMatchesWebExport(unittest.TestCase):

    def tearDown(self):
        set_custom_baseline({})

    def test_7day_baseline_equals_web_average(self):
        """含 11-07 峰值：日均 = 12.96 / 7 = 1.851"""
        set_custom_baseline({'range_enabled': True,
                             'range_start': '2026-11-02 00:00',
                             'range_end': '2026-11-08 23:59'})
        r = predict_daily_emission(WEB_KG, horizon_days=3, dates=WEB_DATES,
                                   baseline_mode='custom',
                                   apply_correction=False,
                                   accumulate_feedback=False)
        self.assertAlmostEqual(r['baseline'], 1.8514, places=3)
        self.assertEqual(r['baseline_days'], 7)
        self.assertAlmostEqual(r['baseline_total'], 12.96, places=2)

    def test_peak_day_not_filtered_out(self):
        """11-07 的 5.97 kg 是真实短时峰值，不能被 IQR 当异常剔除"""
        set_custom_baseline({'range_enabled': True,
                             'range_start': '2026-11-02 00:00',
                             'range_end': '2026-11-08 23:59'})
        r = predict_daily_emission(WEB_KG, horizon_days=3, dates=WEB_DATES,
                                   baseline_mode='custom',
                                   apply_correction=False,
                                   accumulate_feedback=False)
        self.assertGreater(r['baseline_total'], 12.0,
                           '峰值天未计入 → 说明被异常值过滤掉了')


class TestEmissionUnitNormalization(unittest.TestCase):

    def test_ton_from_server_converted_to_kg(self):
        # 11-02：浓度 1.38，日流量 699920 → 换算 0.966 kg；
        # 服务端若返回 0.00182（吨），应归一化为 1.82 kg
        row = {'val_383': '1.38', 'val_210': '699920', 'pf_383': '0.00182'}
        kg = extract_emission_mass(row, '383', '210')
        self.assertAlmostEqual(kg, 1.82, places=3)

    def test_kg_field_kept_as_is(self):
        row = {'val_383': '1.38', 'val_210': '699920', 'pf_383': '0.966'}
        kg = extract_emission_mass(row, '383', '210')
        self.assertAlmostEqual(kg, 0.966, places=3)

    def test_no_flow_code_keeps_raw(self):
        row = {'val_383': '1.38', 'pf_383': '0.00182'}
        self.assertAlmostEqual(extract_emission_mass(row, '383'), 0.00182)


class TestHourAggregationMetadata(unittest.TestCase):

    def test_hours_count_and_emission_sum(self):
        from main_window import PredictionWorker
        rows = [{'DateTime': f'2026-11-02 {h:02d}:00',
                 'val_383': '1.38', 'val_210': '29000'} for h in range(24)]
        out = PredictionWorker._aggregate_hour_rows_to_daily(rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['hours_383'], 24)
        self.assertAlmostEqual(out[0]['emis_383'], 1.38 * 29000 * 24 / 1e6,
                               places=4)
        self.assertAlmostEqual(out[0]['flowsum_210'], 29000 * 24, places=1)

    def test_partial_day_hours_recorded(self):
        from main_window import PredictionWorker
        rows = [{'DateTime': f'2026-11-07 {h:02d}:00',
                 'val_383': '1.09', 'val_210': '21000'} for h in range(5)]
        out = PredictionWorker._aggregate_hour_rows_to_daily(rows)
        self.assertEqual(out[0]['hours_383'], 5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
