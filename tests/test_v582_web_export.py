# -*- coding: utf-8 -*-
"""v5.82 用 4 份冠洲官网导出核对数据逻辑（真实文件回归）

样本：
  总排口（废水，COD/氨氮，mg/L）：11-12 小时(00-06)、11-11 分钟(07:00-23:50)
  VOCs总排口（废气，非甲烷总烃，mg/m³）：11-12 小时(00-06)、11-01~11-11 日

覆盖：
  1. 废水参数名归一（旧正则漏 mg/L 导致数据整个失效）
  2. 日导出 t→kg、小时/分钟 kg 原样
  3. 部分天识别与隔离（不得计入日均基准）
  4. 完整 11 天基准（含峰值天不被剔除）
  5. 去 pandas 依赖
  6. 服务端排放量自动发现可达 + 量级校验放宽
  7. 废水/废气换算分母
"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import param_units as pu          # noqa: E402
import web_daily_import as wdi    # noqa: E402

DL = os.path.join(os.path.expanduser('~'), 'Downloads')
FILES = {
    'zong_h': os.path.join(DL, '历史数据_山东冠洲股份有限公司总排口_2026-11-12+00+至+2026-11-12+23.xls'),
    'zong_m': os.path.join(DL, '历史数据_山东冠洲股份有限公司总排口_2026-11-11+07+至+2026-11-11+23.xls'),
    'vocs_h': os.path.join(DL, '历史数据_山东冠洲股份有限公司VOCs总排口_2026-11-12+00+至+2026-11-12+23.xls'),
    'vocs_d': os.path.join(DL, '历史数据_山东冠洲股份有限公司VOCs总排口_2026-11-01+至+2026-11-11.xls'),
}
ENT = '山东冠洲股份有限公司'


def _have(key):
    return os.path.exists(FILES[key])


class TestNormParam(unittest.TestCase):
    def test_wastewater_mg_per_l_stripped(self):
        """旧正则漏 mg/L，'化学需氧量(mg/L)' 会原样成 key 导致匹配失败。"""
        self.assertEqual(wdi._norm_param('化学需氧量(mg/L)'), '化学需氧量')
        self.assertEqual(wdi._norm_param('氨氮(mg/L)'), '氨氮')
        self.assertEqual(wdi._norm_param('非甲烷总烃(mg/m3)'), '非甲烷总烃')
        self.assertEqual(wdi._norm_param('碳氢化合物(总烃)(mg/m3)'), '碳氢化合物总烃')


class TestParseExport(unittest.TestCase):
    @unittest.skipUnless(_have('vocs_d'), '缺官网日导出样例')
    def test_daily_ton_to_kg(self):
        parsed = wdi.parse_export(FILES['vocs_d'])
        key = f'{ENT}|VOCs总排口|非甲烷总烃'
        self.assertIn(key, parsed)
        rec = parsed[key]
        self.assertEqual(rec['unit_src'], 't')
        self.assertEqual(len(rec['values_kg']), 11)
        self.assertAlmostEqual(rec['values_kg']['2026-11-01'], 2.5, places=4)
        self.assertAlmostEqual(rec['values_kg']['2026-11-02'], 3.39, places=4)
        self.assertEqual(rec['partial_days'], {})

    @unittest.skipUnless(_have('zong_m'), '缺官网分钟导出样例')
    def test_wastewater_keys_and_partial_day(self):
        parsed = wdi.parse_export(FILES['zong_m'])
        key = f'{ENT}|总排口|化学需氧量'
        self.assertIn(key, parsed, f'废水参数 key 未归一: {list(parsed)}')
        rec = parsed[key]
        self.assertEqual(rec['unit_src'], 'kg')
        self.assertEqual(rec['values_kg'], {})          # 部分天不进基准
        self.assertEqual(rec['granularity'], 'minute')
        p = rec['partial_days']['2026-11-11']
        self.assertEqual(p['hours'], 17)                # 07-23 共 17 小时
        self.assertAlmostEqual(p['kg'], 2.359, places=3)
        self.assertEqual(rec['rows'], 102)              # 102 个 10 分钟桶

    @unittest.skipUnless(_have('vocs_h') and _have('zong_h'), '缺小时导出样例')
    def test_hour_partial_days(self):
        for fkey, outlet, param in (
                ('vocs_h', 'VOCs总排口', '非甲烷总烃'),
                ('zong_h', '总排口', '化学需氧量')):
            parsed = wdi.parse_export(FILES[fkey])
            rec = parsed[f'{ENT}|{outlet}|{param}']
            self.assertEqual(rec['values_kg'], {})
            self.assertEqual(rec['partial_days']['2026-11-12']['hours'], 7)


class TestStoreBaseline(unittest.TestCase):
    @unittest.skipUnless(all(_have(k) for k in FILES), '缺官网导出样例')
    def test_baseline_only_full_days_and_keeps_peak(self):
        st = wdi.WebDailyStore(os.path.join(tempfile.mkdtemp(), 'store.json'))
        for f in FILES.values():
            st.merge(wdi.parse_export(f))
        vals, dates = st.get_series(ENT, 'VOCs总排口', '非甲烷总烃',
                                    '2026-11-01', '2026-11-30')
        self.assertEqual(len(vals), 11)                 # 部分天未混入
        self.assertAlmostEqual(sum(vals) / len(vals), 3.3436, places=3)
        # 11-09 的 6.97 kg 是真实峰值天，必须保留（旧 IQR 会误剔除）
        self.assertIn(6.97, vals)
        # 废水两份都是部分天 -> 不参与基准
        v2, _ = st.get_series(ENT, '总排口', '化学需氧量')
        self.assertEqual(len(v2), 0)

    @unittest.skipUnless(_have('vocs_d'), '缺官网日导出样例')
    def test_full_day_overrides_partial(self):
        """先导入部分天、再导入完整日，同日应从 partial_days 移除。"""
        st = wdi.WebDailyStore(os.path.join(tempfile.mkdtemp(), 'store.json'))
        st.merge(wdi.parse_export(FILES['vocs_d']))
        key = f'{ENT}|VOCs总排口|非甲烷总烃'
        # 手工注入一个 11-01 的部分天记录
        st.series[key].setdefault('partial_days', {})['2026-11-11'] = {
            'kg': 0.1, 'hours': 7, 'granularity': 'hour'}
        st.merge(wdi.parse_export(FILES['vocs_d']))
        self.assertNotIn('2026-11-11', st.series[key]['partial_days'])

    def test_get_series_excludes_partial_even_if_present(self):
        """兼容旧版 store：values_kg 里残留的部分天也要被排除。"""
        st = wdi.WebDailyStore(os.path.join(tempfile.mkdtemp(), 'store.json'))
        key = f'{ENT}|总排口|化学需氧量'
        st.series[key] = {
            'values_kg': {'2026-11-11': 2.359},
            'partial_days': {'2026-11-11': {'kg': 2.359, 'hours': 17,
                                            'granularity': 'minute'}},
        }
        vals, _ = st.get_series(ENT, '总排口', '化学需氧量')
        self.assertEqual(vals, [])


class TestNoPandas(unittest.TestCase):
    @unittest.skipUnless(_have('vocs_d'), '缺官网日导出样例')
    def test_parse_without_pandas(self):
        """屏蔽 pandas 后仍能解析（v5.82 去掉隐藏依赖）。"""
        import builtins
        real_import = builtins.__import__

        def guard(name, *args, **kwargs):
            if name == 'pandas' or name.startswith('pandas.'):
                raise ImportError('pandas blocked by test')
            return real_import(name, *args, **kwargs)

        builtins.__import__ = guard
        try:
            parsed = wdi.parse_export(FILES['vocs_d'])
            self.assertIn(f'{ENT}|VOCs总排口|非甲烷总烃', parsed)
        finally:
            builtins.__import__ = real_import


class TestParamUnits(unittest.TestCase):
    def test_divisors(self):
        # 废水 mg/L -> 1000；废气 mg/m³ -> 1e6
        self.assertAlmostEqual(pu.calc_emission_rate(4.82, 26, '316'), 0.12532, places=5)
        self.assertAlmostEqual(pu.calc_emission_rate(0.807, 94645, '383'), 0.07638, places=5)
        self.assertAlmostEqual(pu.calc_emission_rate(1.81, 119649, '383',
                                                     hours=1 / 60), 0.00361, places=5)

    def test_auto_discover_reachable(self):
        """候选字段名未命中时应走自动发现（旧版 raw is None 直接 return）。"""
        row = {'val_383': 1.0, 'val_210': 100000.0, 'emis_383': 0.1}
        self.assertAlmostEqual(pu.extract_emission_mass(row, '383', '210'), 0.1)

    def test_auto_discover_tolerance_for_minute_integral(self):
        """分钟积分排放量可数倍于公式值（v5.79 实测 7.8 倍），不应被误杀。"""
        row = {'val_383': 1.0, 'val_210': 100000.0, 'emis_383': 0.78}
        self.assertAlmostEqual(pu.extract_emission_mass(row, '383', '210'), 0.78)

    def test_standard_value_not_mistaken(self):
        """标准值 50 比公式值大数百倍，必须排除。"""
        row = {'val_383': 1.0, 'val_210': 100000.0, 'standard_383': 50.0}
        self.assertIsNone(pu.extract_emission_mass(row, '383', '210'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
