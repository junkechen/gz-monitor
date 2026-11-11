# -*- coding: utf-8 -*-
"""v5.80 时间粒度与排放量换算（用官网分钟/小时/日三份导出核对）

用户提供的三份导出（鼎鑫 彩涂1-3#排放口，2026-11-02 起）证实：
  1. 分钟数据「流量(m3)」是 m³/h → 分钟排放量 = 浓度 × 流量/60 / 1e6
     （官网 00:00：1.81 × 119649/60/1e6 = 0.0036 ≈ 0.004 kg；
       不除 60 得 0.2166，高估 60 倍）
  2. 小时数据「流量(m3)」即该小时累计风量 → ×1
     （官网 00 时：2.06 × 110890/1e6 = 0.2284 ≈ 0.228 kg）
  3. 日排放量(t) = Σ 24 小时排放量(kg) / 1000
     （实测 Σ小时 = 9.569 kg，日值 9.570 kg）
  4. 小时排放量 ≈ Σ 60 分钟排放量（00 时：0.228 vs 0.227）
"""
import os
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from param_units import calc_emission_rate  # noqa: E402

_DL = os.path.join(os.path.expanduser('~'), 'Downloads')
F_HOUR = os.path.join(_DL, '历史数据_山东冠洲鼎鑫板材科技有限公司彩涂1-3#排放口_'
                           '2026-11-02+00+至+2026-11-11+23.xls')     # 实为小时
F_MIN = os.path.join(_DL, '历史数据_山东冠洲鼎鑫板材科技有限公司彩涂1-3#排放口_'
                          '2026-11-02+00+至+2026-11-03+00.xls')      # 实为分钟
F_DAY = os.path.join(_DL, '历史数据_山东冠洲鼎鑫板材科技有限公司彩涂1-3#排放口_'
                          '2026-11-01+至+2026-11-10.xls')            # 日


class TestTimeScale(unittest.TestCase):

    def test_minute_requires_divide_60(self):
        kg_min = calc_emission_rate(1.81, 119649, '383', hours=1 / 60)
        self.assertAlmostEqual(kg_min, 0.00361, places=4)   # 官网 0.004
        kg_hour = calc_emission_rate(1.81, 119649, '383')
        self.assertAlmostEqual(kg_hour, 0.2166, places=3)   # 不折算会高估
        self.assertGreater(kg_hour / kg_min, 59.0)

    def test_hour_scale_one(self):
        self.assertAlmostEqual(
            calc_emission_rate(2.06, 110890, '383'), 0.2284, places=3)

    def test_default_unchanged(self):
        """默认 hours=1，保持既有调用行为不变"""
        self.assertAlmostEqual(
            calc_emission_rate(10, 100, '201'), calc_emission_rate(10, 100, '201', hours=1.0))


class TestThreeGranularities(unittest.TestCase):
    """用真实导出核对三种粒度的换算关系"""

    @classmethod
    def setUpClass(cls):
        if not all(os.path.exists(p) for p in (F_HOUR, F_MIN, F_DAY)):
            raise unittest.SkipTest('官网导出样例缺失')
        import pandas as pd
        cls.pd = pd
        cls.h = pd.read_excel(F_HOUR, header=None).iloc[3:]
        cls.m = pd.read_excel(F_MIN, header=None).iloc[3:]
        cls.d = pd.read_excel(F_DAY, header=None).iloc[3:]

    def _sum(self, df, col, day):
        tot = 0.0
        for i in range(len(df)):
            t = str(df.iat[i, 2])
            if t.startswith(day):
                try:
                    tot += float(df.iat[i, col])
                except (ValueError, TypeError):
                    pass
        return tot

    def test_hour_values_match_formula(self):
        # 官网小时排放量 ≈ 浓度 × 流量 / 1e6
        diff = 0
        for i in range(len(self.h)):
            try:
                c = float(self.h.iat[i, 3])
                q = float(self.h.iat[i, 22])
                v = float(self.h.iat[i, 6])
            except (ValueError, TypeError):
                continue
            if q <= 0:
                continue
            if abs(v - calc_emission_rate(c, q, '383')) > max(0.02, v * 0.2):
                diff += 1
        self.assertLess(diff, 5, f'小时值与公式偏离 {diff} 行')

    def test_day_equals_sum_of_hours(self):
        day = '2026-11-02'
        hours_sum = self._sum(self.h, 6, day)
        day_val = self._sum(self.d, 6, day) * 1000      # 日导出单位为 t
        self.assertAlmostEqual(hours_sum, day_val, delta=0.02)

    def test_minute_row_matches_official(self):
        # 00:00 行：浓度 1.81、流量 119649、官网 0.004 kg
        r = next(i for i in range(len(self.m))
                 if str(self.m.iat[i, 2]).startswith('2026-11-02 00:00'))
        kg = calc_emission_rate(float(self.m.iat[r, 3]),
                                float(self.m.iat[r, 19]), '383', hours=1 / 60)
        self.assertAlmostEqual(kg, float(self.m.iat[r, 6]), delta=0.0015)

    def test_hour_equals_sum_of_minutes_in_first_hour(self):
        hour_val = float(self.h.iat[0, 6])              # 11-02 00 时
        m_sum, n = 0.0, 0
        for i in range(len(self.m)):
            if str(self.m.iat[i, 2]).startswith('2026-11-02 00:'):
                m_sum += float(self.m.iat[i, 6])
                n += 1
        self.assertEqual(n, 60)
        self.assertAlmostEqual(m_sum, hour_val, delta=0.01)


if __name__ == '__main__':
    unittest.main(verbosity=2)
