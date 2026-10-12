# -*- coding: utf-8 -*-
"""
v5.49 排放单位与排放量计算 —— 单元测试

背景：服务端接口只返回浓度（val/cvt），既不返回参数单位也不返回排放量。
param_units 模块补上这两块：
  1. 排放单位：code -> 单位（mg/m³、mg/L、%…）
  2. 排放量：  浓度 × 流量，废气 /1e6、废水 /1e3 -> kg/h

覆盖：
  1. 单位表覆盖全部已知 code，含字符串 code（SO2/NOx/PM）
  2. 单位格式（废气 mg/m³、废水 mg/L、pH 无量纲）
  3. 排放量计算正确性（废气/废水两条换算路径）
  4. 非浓度参数（pH/温度/流速）不可计算排放量
  5. 流量 code 识别（废气 210 优先于废水 492/494）
  6. 边界：None/NaN/空串/非法值
  7. 日排放量换算（×24h）
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep + 'src')

from param_units import (
    PARAM_UNITS, FLOW_CODES, EMISSION_UNIT,
    normalize_code, get_param_unit, is_concentration_param,
    get_concentration_divisor, calc_emission_rate, find_flow_code,
    format_emission_rate,
)
from data_processor import CODE_TO_NAME


class TestParamUnits(unittest.TestCase):

    # ── 1. 覆盖度 ────────────────────────────────────────────────────────
    def test_a_all_codes_have_units(self):
        """CODE_TO_NAME 里的每个 code 都应有单位（避免界面显示空白）"""
        missing = [c for c in CODE_TO_NAME if c not in PARAM_UNITS]
        self.assertEqual(missing, [],
                         f"以下参数缺少单位定义: {missing}")

    def test_b_string_codes_covered(self):
        """字符串 code（SO2/NOx/PM）也应有单位"""
        for code in ('SO2', 'NOx', 'PM'):
            self.assertEqual(get_param_unit(code), 'mg/m³')

    def test_c_normalize_code(self):
        """code 归一化：210 / '210' / 210.0 应等价"""
        self.assertEqual(normalize_code(210), '210')
        self.assertEqual(normalize_code('210'), '210')
        self.assertEqual(normalize_code(210.0), '210')
        self.assertEqual(normalize_code(None), '')

    # ── 2. 单位格式 ──────────────────────────────────────────────────────
    def test_d_waste_gas_units(self):
        """废气浓度参数单位应为 mg/m³"""
        for code in ('201', '203', '207', '220', '299', '383'):
            self.assertEqual(get_param_unit(code), 'mg/m³', f"{code} 单位不符")

    def test_e_waste_water_units(self):
        """废水浓度参数单位应为 mg/L"""
        for code in ('311', '316'):
            self.assertEqual(get_param_unit(code), 'mg/L', f"{code} 单位不符")

    def test_f_non_concentration_units(self):
        """非浓度参数单位各自独立"""
        self.assertEqual(get_param_unit('302'), '无量纲')   # pH
        self.assertEqual(get_param_unit('209'), '%')        # 含氧量
        self.assertEqual(get_param_unit('210'), 'm³/h')     # 烟气流量
        self.assertEqual(get_param_unit('525'), '℃')        # 温度
        self.assertEqual(get_param_unit('211'), 'm/s')      # 流速
        self.assertEqual(get_param_unit('495'), 'm³')       # 累计流量

    def test_g_unknown_code(self):
        """未知 code 返回空串（调用方应显示 --）"""
        self.assertEqual(get_param_unit('99999'), '')

    # ── 3. 排放量计算 ────────────────────────────────────────────────────
    def test_h_waste_gas_emission(self):
        """废气：浓度(mg/m³) × 流量(m³/h) / 1e6 = kg/h"""
        # 100 mg/m³ × 10000 m³/h = 1e6 mg/h = 1 kg/h
        v = calc_emission_rate(100.0, 10000.0, '203')
        self.assertAlmostEqual(v, 1.0, places=6)

    def test_i_waste_water_emission(self):
        """废水：浓度(mg/L) × 流量(m³/h) / 1e3 = kg/h"""
        # 200 mg/L × 50 m³/h = 10000 mg/L·m³/h = 10 kg/h
        v = calc_emission_rate(200.0, 50.0, '316')
        self.assertAlmostEqual(v, 10.0, places=6)

    def test_j_emission_unit_constant(self):
        """排放量单位常量应为 kg/h"""
        self.assertEqual(EMISSION_UNIT, 'kg/h')

    def test_k_divisors(self):
        """换算分母：废气 1e6、废水 1e3"""
        self.assertEqual(get_concentration_divisor('203'), 1e6)
        self.assertEqual(get_concentration_divisor('316'), 1e3)
        self.assertIsNone(get_concentration_divisor('302'))    # pH 无分母

    # ── 4. 非浓度参数不可计算 ────────────────────────────────────────────
    def test_l_non_concentration_not_computable(self):
        """pH/温度/流速/流量本身不可计算排放量"""
        for code in ('302', '525', '211', '210', '495', '209', '527', '526'):
            self.assertFalse(is_concentration_param(code),
                             f"{code} 不应被视为浓度参数")
            self.assertIsNone(calc_emission_rate(5.0, 100.0, code),
                              f"{code} 不应产出排放量")

    def test_m_concentration_recognized(self):
        """浓度参数应被正确识别"""
        for code in ('201', '203', '207', '311', '316', 'SO2', 'NOx', 'PM'):
            self.assertTrue(is_concentration_param(code))

    # ── 5. 流量 code 识别 ────────────────────────────────────────────────
    def test_n_flow_code_priority(self):
        """废气流量(210)优先于废水流量(492/494)"""
        self.assertEqual(find_flow_code(['201', '210', '492']), '210')
        self.assertEqual(find_flow_code(['316', '492', '494']), '492')
        self.assertEqual(find_flow_code(['316', '494']), '494')
        self.assertIsNone(find_flow_code(['201', '203']))
        self.assertIsNone(find_flow_code([]))

    def test_o_cumulative_flow_excluded(self):
        """累计流量(495)不能用作瞬时流量乘数"""
        self.assertNotIn('495', FLOW_CODES)

    # ── 6. 边界与健壮性 ──────────────────────────────────────────────────
    def test_p_none_and_nan_inputs(self):
        """None / NaN / 空串 输入必须安全返回 None"""
        self.assertIsNone(calc_emission_rate(None, 100.0, '203'))
        self.assertIsNone(calc_emission_rate(50.0, None, '203'))
        self.assertIsNone(calc_emission_rate(float('nan'), 100.0, '203'))
        self.assertIsNone(calc_emission_rate(50.0, float('nan'), '203'))

    def test_q_invalid_string_inputs(self):
        """字符串脏数据不应抛异常"""
        self.assertIsNone(calc_emission_rate('abc', '100', '203'))
        self.assertIsNone(calc_emission_rate('50', '--', '203'))

    def test_r_zero_values(self):
        """零值输入应正常计算（结果为 0），不报错"""
        self.assertEqual(calc_emission_rate(0.0, 100.0, '203'), 0.0)

    def test_s_string_numbers(self):
        """数字字符串应可正常计算（接口返回常为 str）"""
        v = calc_emission_rate('100', '10000', '203')
        self.assertAlmostEqual(v, 1.0, places=6)

    # ── 7. 格式化 ────────────────────────────────────────────────────────
    def test_t_format_emission_rate(self):
        """排放量格式化：有效值 3 位小数，无效值 --"""
        self.assertEqual(format_emission_rate(1.0), '1.000')
        self.assertEqual(format_emission_rate(0.12345), '0.123')
        self.assertEqual(format_emission_rate(None), '--')
        self.assertEqual(format_emission_rate('abc'), '--')
        self.assertEqual(format_emission_rate(float('nan')), '--')

    def test_u_daily_emission_conversion(self):
        """日排放量 = 小时排放量 × 24"""
        hourly = calc_emission_rate(100.0, 10000.0, '203')   # 1 kg/h
        self.assertAlmostEqual(hourly * 24, 24.0, places=6)  # 24 kg/天


if __name__ == '__main__':
    unittest.main(verbosity=2)
