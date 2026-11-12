# -*- coding: utf-8 -*-
"""v5.84：服务端日排放量字段 ex_{code} 是吨单位，须正确吨→kg 且不被量纲守卫丢弃。

根因：日数据接口(index=2)返回的「排放量」列字段为 ex_{code}，单位是**吨**
（实测 2026-11-02 日行 ex_383="0.00339" = 3.39 kg，正是官网日导出值）。
旧版 EMISSION_FIELD_CANDIDATES 不含 ex_，落到 detect_server_emission，
因 0.00339/公式值(2.029) ≈ 1.67e-3 落在 [0.1,10] 之外被拒绝，回退到
「浓度×流量」——峰值天（11-02）被低估 40%。
v5.84：将 ex_{code} 加入候选（首位），其下方吨→kg 分支（ratio∈[1e-4,1e-2] → ×1000）
即可正确换算；分钟粒度 ex_383="0" 须跳过（v<=0 continue），回退到公式计算。

用桩行验证：日行吨字段→3.39kg、分钟行 ex_="0"→回退公式、小时行 kg 字段原样。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from param_units import extract_emission_mass


class TestDayEmissionTon(unittest.TestCase):
    def test_day_ex_field_ton_to_kg(self):
        # 日行：ex_383 是吨，应换算为 kg = 3.39
        row = {'DateTime': '2026-11-02', 'val_383': '0.901', 'val_210': '2252293',
               'ex_383': '0.00339'}
        m = extract_emission_mass(row, '383', '210')
        self.assertIsNotNone(m)
        self.assertAlmostEqual(m, 3.39, places=4)

    def test_day_ex_field_kg_unchanged(self):
        # 日行即便 ex_ 恰好是 kg（ratio≈1），也原样返回
        row = {'DateTime': '2026-11-03', 'val_383': '2.24', 'val_210': '1000000',
               'ex_383': '2.24'}
        m = extract_emission_mass(row, '383', '210')
        self.assertAlmostEqual(m, 2.24, places=4)

    def test_minute_ex_zero_not_returned_as_zero(self):
        # 分钟行 ex_383="0" 必须跳过（v<=0 continue），返回 None（交由调用方回退公式），
        # 而绝不能把排放当成 0.0（v5.84 修复前的回归：ex_ 入候选后会返回 0.0）。
        row = {'DateTime': '2026-11-02 00:00:00', 'val_383': '1.81',
               'val_210': '119649', 'ex_383': '0'}
        m = extract_emission_mass(row, '383', '210')
        self.assertIsNone(m)

    def test_hour_ex_field_kg(self):
        # 小时行 ex_383 是 kg（ratio≈1），原样返回
        row = {'DateTime': '2026-11-02 00', 'val_383': '1.48', 'val_210': '28771',
               'ex_383': '0.042'}
        m = extract_emission_mass(row, '383', '210')
        self.assertAlmostEqual(m, 0.042, places=4)


if __name__ == '__main__':
    unittest.main()
