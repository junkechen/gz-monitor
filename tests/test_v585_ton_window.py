# -*- coding: utf-8 -*-
"""v5.85：放宽日粒度吨→kg 的判定窗口，兜住「日均浓度失真」导致的比值越界天。

根因：v5.84 的吨判定窗口为 ratio ∈ [1e-4, 1e-2]。绝大多数日行的
ex_{code}(吨) 与「val×flow/1e6」kg 估算值之比约 1e-3，能正确 ×1000。
但个别天（实测鼎鑫彩涂4# 2026-11-07）日均浓度 val_383 失真为 1.09
（真实约 11.78 mg/m³），把 kg 估算值压到 0.5525，而服务端 ex_383=0.00597 t
实为其真实 5.97 kg（=Σ小时排放量）。此时 ratio = 0.00597/0.5525 = 0.0108，
恰好 > 1e-2，旧窗口把它误判为「已是 kg」，5.97 kg 被读成 0.006 kg
（低估近千倍），使 6 日基线从 11.92 kg 塌到 ~6.0 kg。

合法 kg 值的 ratio 约 1（0.1~10），与吨区间（<1e-1）天然分离，
故窗口上限放到 1e-1 既兜住失真天，又不会把真 kg 误乘 1000。

用桩行验证：失真天 ratio=1.08e-2 仍 ×1000 → 5.97kg；普通天与 kg 天不变。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from param_units import extract_emission_mass, calc_emission_rate


class TestV585TonWindow(unittest.TestCase):
    def test_distorted_day_still_ton(self):
        # 鼎鑫彩涂4# 2026-11-07：val_383 失真(1.09) 压低 kg 估算值，
        # ratio=0.0108 越出旧 [1e-4,1e-2] 上界；v5.85 须识别为吨 → 5.97 kg
        row = {'DateTime': '2026-11-07', 'val_383': '1.09',
               'val_210': '506907', 'ex_383': '0.00597'}
        m = extract_emission_mass(row, '383', '210')
        self.assertIsNotNone(m)
        self.assertAlmostEqual(m, 5.97, places=4)
        # 显式确认 ratio 落在旧边界之外、新边界之内
        kg = calc_emission_rate('1.09', '506907', '383')
        ratio = 0.00597 / kg
        self.assertGreater(ratio, 1e-2)   # 旧窗口会漏掉
        self.assertLessEqual(ratio, 1e-1)  # 新窗口兜住

    def test_normal_day_ton_unchanged(self):
        # 普通日行 ratio≈1e-3，仍正确 ×1000
        row = {'DateTime': '2026-11-02', 'val_383': '1.38',
               'val_210': '699920', 'ex_383': '0.00182'}
        m = extract_emission_mass(row, '383', '210')
        self.assertAlmostEqual(m, 1.82, places=4)

    def test_kg_day_unchanged(self):
        # 日行若 ex_ 已是 kg（ratio≈1），原样返回，不被误乘
        row = {'DateTime': '2026-11-03', 'val_383': '2.24',
               'val_210': '1000000', 'ex_383': '2.24'}
        m = extract_emission_mass(row, '383', '210')
        self.assertAlmostEqual(m, 2.24, places=4)

    def test_hour_kg_unchanged(self):
        # 小时行 ex_ 是 kg（ratio≈1），原样返回
        row = {'DateTime': '2026-11-02 00', 'val_383': '1.48',
               'val_210': '28771', 'ex_383': '0.042'}
        m = extract_emission_mass(row, '383', '210')
        self.assertAlmostEqual(m, 0.042, places=4)


if __name__ == '__main__':
    unittest.main()
