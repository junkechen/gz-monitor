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
    format_emission_rate, calc_emission_mass, extract_emission_mass,
)
from data_processor import CODE_TO_NAME


class TestParamUnits(unittest.TestCase):

    # ── 1. 覆盖度 ────────────────────────────────────────────────────────
    def test_a_all_codes_have_units(self):
        """CODE_TO_NAME 里的每个 code 都应有单位（避免界面显示空白）"""
        missing = [c for c in CODE_TO_NAME if c not in PARAM_UNITS]
        self.assertEqual(missing, [],
                         f"以下参数缺少单位定义: {missing}")

    def test_a2_server_mapping_matches_code(self):
        """CODE_TO_NAME 必须与服务端实时接口返回的 name 一致（v5.52 实证）

        服务端 `GetEnterpriseRealtimeData` 每项自带 C0001_ITEM_CODE +
        C0001_ITEM_NAME，是 code->name 的权威来源。探测结果见
        docs/code_mapping_probe.txt（冠县恒润热电，subid=1789「1-2号机组」
        与 subid=9910「恒润热电排污口」）。

        此处把 201/203/207 的映射锁死，防止被 docs/数据接口文档.md 2.5 节
        的错误描述（原写 201=非甲烷总烃/203=二氧化硫/207=氮氧化物）带偏。
        """
        # 服务端实测返回值（去掉单位后缀后与代码名等价）
        SERVER_MAP = {
            '201': '二氧化硫', '203': '氮氧化物', '207': '颗粒物',
            '209': '氧气',     '210': '流量',     '211': '流速',
            '525': '烟气温度', '526': '烟气压力', '527': '烟气湿度',
            '301': '水温',     '302': 'PH',       '311': '氨氮',
            '316': '化学需氧量', '494': '流量',
        }
        # 服务端名与代码名的等价关系（命名差异，非映射差异）
        # 按 code 指定，因为「流量」一名对应 210(代码名烟气流量) 与
        # 494(代码名流量) 两个不同参数，不能共用一个全局映射。
        EQUIV = {
            '209': {'氧气': '烟气含氧量'},
            '302': {'PH': 'pH值'},
            '526': {'千帕': 'kPa'},
            '210': {'流量': '烟气流量'},
        }

        for code, srv_name in SERVER_MAP.items():
            code_name = CODE_TO_NAME.get(code)
            self.assertIsNotNone(code_name, f"code {code} 不在 CODE_TO_NAME 中")
            expected = EQUIV.get(code, {}).get(srv_name, srv_name)
            self.assertEqual(
                code_name, expected,
                f"code {code}: 服务端={srv_name} 代码={code_name}，映射不一致")

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
        """非浓度参数单位各自独立（v5.52：流量单位按服务端口径改为 m³）"""
        self.assertEqual(get_param_unit('302'), '无量纲')   # pH
        self.assertEqual(get_param_unit('209'), '%')        # 含氧量
        self.assertEqual(get_param_unit('210'), 'm³')       # 烟气流量（期间累计）
        self.assertEqual(get_param_unit('525'), '℃')        # 温度
        self.assertEqual(get_param_unit('211'), 'm/s')      # 流速
        self.assertEqual(get_param_unit('495'), 'm³')       # 累计流量
        self.assertEqual(get_param_unit('492'), 'm³')       # 废水流量
        self.assertEqual(get_param_unit('494'), 'm³')       # 流量

    def test_f2_flow_units_are_cumulative(self):
        """流量参数单位必须是 m³（期间累计），不能是 m³/h（v5.52 实证）"""
        for code in ('210', '492', '494', '495'):
            self.assertEqual(get_param_unit(code), 'm³',
                             f"{code} 单位应为 m³（服务端口径）")

    def test_g_unknown_code(self):
        """未知 code 返回空串（调用方应显示 --）"""
        self.assertEqual(get_param_unit('99999'), '')

    # ── 3. 排放量计算 ────────────────────────────────────────────────────
    def test_h_waste_gas_emission(self):
        """废气：实测浓度(mg/m³) × 期间累计流量(m³) / 1e6 = kg"""
        # 100 mg/m³ × 10000 m³ = 1e6 mg = 1 kg
        v = calc_emission_rate(100.0, 10000.0, '203')
        self.assertAlmostEqual(v, 1.0, places=6)

    def test_i_waste_water_emission(self):
        """废水：实测浓度(mg/L) × 期间累计流量(m³) / 1e3 = kg"""
        # 200 mg/L × 50 m³ = 10000 mg/L·m³ = 10 kg
        v = calc_emission_rate(200.0, 50.0, '316')
        self.assertAlmostEqual(v, 10.0, places=6)

    def test_j_emission_unit_constant(self):
        """排放量单位常量应为 kg（期间质量，非 kg/h）

        v5.50 修正：经与网页端核对，网页「排放量(kg)」列用的是期间累计流量
        （如日累计 127021 m³），故单位为 kg 而非 kg/h。
        """
        self.assertEqual(EMISSION_UNIT, 'kg')

    def test_j2_matches_web_values(self):
        """公式必须与网页端显示值一致（2026-10-13 截图实证）

        截图数据：
          冠县恒润热电：SO2 13.7 mg/m³ × 127021 m³ / 1e6 = 1.74 kg
                        NOx 6.82 × 127021 / 1e6 = 0.866 kg
          山东冠洲VOCs：非甲烷总烃 1.05 × 117370 / 1e6 = 0.12 kg
                        甲烷     0.45 × 117370 / 1e6 = 0.05 kg
        """
        self.assertAlmostEqual(
            calc_emission_rate(13.7, 127021, '203'), 1.74, places=2)
        self.assertAlmostEqual(
            calc_emission_rate(6.82, 127021, '203'), 0.866, places=3)
        self.assertAlmostEqual(
            calc_emission_rate(1.05, 117370, '383'), 0.12, places=2)
        self.assertAlmostEqual(
            calc_emission_rate(0.45, 117370, '299'), 0.05, places=2)

    def test_j3_mass_alias(self):
        """calc_emission_mass 应与 calc_emission_rate 等价（语义化别名）"""
        self.assertEqual(calc_emission_mass(100.0, 10000.0, '203'),
                         calc_emission_rate(100.0, 10000.0, '203'))

    def test_j4_uses_measured_not_corrected(self):
        """排放量必须用**实测值**，不能用折算值（v5.51 实证）

        网页端 2026-10-13 截图，顶层流量明确为 127021 m³：
          SO2 实测 13.7 -> 1.740 kg (网页 1.74)   ✓
          SO2 折算 14.5 -> 1.842 kg (网页 1.84)   ✗
          NOx 实测 6.82 -> 0.866 kg (网页 0.866)  ✓
          NOx 折算 7.17 -> 0.911 kg (网页 0.911)  ✗
        若误用折算值，结果会系统性偏高约 6%，此处锁定该口径。
        """
        flow = 127021
        # 实测口径应与网页一致
        self.assertAlmostEqual(calc_emission_rate(13.7, flow, '203'),
                               1.74, places=2)
        self.assertAlmostEqual(calc_emission_rate(6.82, flow, '203'),
                               0.866, places=3)
        # 折算口径应与网页明显不符（防止回归到折算）
        self.assertNotAlmostEqual(calc_emission_rate(14.5, flow, '203'),
                                  1.74, places=2)
        self.assertNotAlmostEqual(calc_emission_rate(7.17, flow, '203'),
                                  0.866, places=3)

    def test_j5_hourly_rows_consistent(self):
        """逐小时数据：同一小时两参数反推流量应一致（2026-10-05 截图）

        12 行小时数据中，用实测口径反推的流量在 SO2 与 NOx 间
        偏差绝大多数 <0.5%（个别行为排放量 3 位有效数字舍入所致），
        证明公式与取值口径正确。
        """
        rows = [
            (11.5, 1.55, 1.79, 0.242),
            (16.0, 2.12, 2.07, 0.275),
            (14.5, 1.88, 2.22, 0.287),
            (20.1, 2.63, 2.22, 0.291),
            (17.2, 2.08, 2.50, 0.302),
            (13.2, 1.75, 2.14, 0.284),
            (13.8, 1.91, 2.09, 0.288),
            (15.6, 2.00, 1.78, 0.233),
            (13.9, 1.77, 2.16, 0.275),
            (15.3, 1.94, 1.85, 0.235),
            (19.1, 2.52, 1.61, 0.212),
        ]
        ok = 0
        for so2_c, so2_e, nox_c, nox_e in rows:
            f_so2 = so2_e / (so2_c / 1e6)
            f_nox = nox_e / (nox_c / 1e6)
            if abs(f_so2 - f_nox) / f_so2 < 0.01:   # 偏差 <1%
                ok += 1
        self.assertGreaterEqual(ok, 10,
                                f"仅 {ok}/11 行流量一致，公式或口径可能有误")

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

    def test_u_period_emission_no_24x(self):
        """期间排放量不应再乘 24（v5.50 修正）

        接口 val_{flow} 返回的是**期间累计流量**（如日累计 127021 m³），
        浓度 × 累计流量 / 1e6 即为该期间排放质量，无需按 24h 折算。
        v5.49 曾误乘 24，与网页端口径不符。
        """
        daily = calc_emission_rate(13.7, 127021, '203')
        self.assertAlmostEqual(daily, 1.74, places=2)   # 非 41.77
        self.assertNotAlmostEqual(daily * 24, 1.74, places=2)

    # ── 8. 服务端排放量字段提取 ──────────────────────────────────────────
    def test_v_extract_from_server_pf_field(self):
        """命中 pf_{code} 字段时应返回服务端权威值"""
        row = {'val_203': '13.7', 'pf_203': '1.74'}
        self.assertEqual(extract_emission_mass(row, '203'), 1.74)

    def test_w_extract_fallback_candidates(self):
        """各候选字段名均应能命中"""
        cases = [
            ({'pf_203': '1.5'}, 1.5),
            ({'pfl_203': '2.5'}, 2.5),
            ({'flow_203': '3.5'}, 3.5),
            ({'emission_203': '4.5'}, 4.5),
            ({'pf203': '5.5'}, 5.5),
        ]
        for row, expected in cases:
            self.assertEqual(extract_emission_mass(row, '203'), expected,
                             f"未命中字段 {list(row.keys())[0]}")

    def test_x_extract_none_when_absent(self):
        """无任何候选字段时返回 None（调用方回退计算）"""
        row = {'val_203': '13.7', 'cvt_203': '14.5'}
        self.assertIsNone(extract_emission_mass(row, '203'))

    def test_y_extract_rejects_invalid(self):
        """空值/占位符/非数字/NaN 均应被拒绝"""
        for bad in ('', '--', '/', None, 'abc', float('nan')):
            self.assertIsNone(extract_emission_mass({'pf_203': bad}, '203'),
                              f"无效值 {bad!r} 被误接受")

    def test_z_extract_code_normalization(self):
        """code 归一化后提取（'203.0' 应命中 pf_203）"""
        row = {'pf_203': '1.74'}
        self.assertEqual(extract_emission_mass(row, '203.0'), 1.74)
        self.assertEqual(extract_emission_mass(row, 203), 1.74)

    def test_z2_extract_non_dict_safe(self):
        """非 dict 输入不应抛异常"""
        self.assertIsNone(extract_emission_mass(None, '203'))
        self.assertIsNone(extract_emission_mass('str', '203'))
        self.assertIsNone(extract_emission_mass({}, None))


if __name__ == '__main__':
    unittest.main(verbosity=2)
