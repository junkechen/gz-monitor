# -*- coding: utf-8 -*-
"""v5.78 官网日数据导入（排放量 t → kg）与基准采用

背景：客户端 index=2 日数据接口始终返回空（历史 258 次），小时聚合受平滑/
缺数影响，与官网导出不一致。改为支持导入官网导出的历史数据文件，读取
「排放量(t)」列并 ×1000 转 kg，作为日排放量预测基准。
"""
import os
import sys
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import web_daily_import as wdi  # noqa: E402

SAMPLE = os.path.join(
    os.path.expanduser('~'), 'Downloads',
    '历史数据_山东冠洲鼎鑫板材科技有限公司鼎鑫彩涂4#_2026-11-02+至+2026-11-08.xls')


class TestParseExport(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(SAMPLE):
            self.skipTest('样例导出文件不存在（用户下载目录）')
        self.parsed = wdi.parse_export(SAMPLE)

    def test_params_detected(self):
        keys = list(self.parsed.keys())
        for p in ('非甲烷总烃', '甲烷', '碳氢化合物总烃'):
            self.assertTrue(any(p in k for k in keys), f'缺少参数 {p}: {keys}')

    def test_ton_converted_to_kg(self):
        key = next(k for k in self.parsed if '非甲烷总烃' in k)
        rec = self.parsed[key]
        self.assertEqual(len(rec['dates']), 7)
        vals = [rec['values_kg'][d] for d in rec['dates']]
        self.assertAlmostEqual(vals[0], 1.82, places=3)      # 0.00182 t
        self.assertAlmostEqual(vals[5], 5.97, places=3)      # 11-07 峰值
        self.assertAlmostEqual(sum(vals), 12.96, places=2)
        self.assertAlmostEqual(sum(vals) / 7, 1.8514, places=3)

    def test_summary_rows_ignored(self):
        key = next(k for k in self.parsed if '非甲烷总烃' in k)
        for d in self.parsed[key]['dates']:
            self.assertRegex(d, r'^\d{4}-\d{2}-\d{2}$')


class TestStore(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = wdi.WebDailyStore(os.path.join(self.tmp, 'w.json'))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _rec(self, ent='A', sub='P', param='非甲烷总烃', days=None):
        days = days or {'2026-11-02': 1.82, '2026-11-03': 1.03,
                        '2026-11-07': 5.97}
        return {f"{ent}|{sub}|{param}": {
            'ent': ent, 'subname': sub, 'param': param, 'unit_src': 't',
            'values_kg': dict(days), 'dates': sorted(days)}}

    def test_merge_and_persist(self):
        self.assertEqual(self.store.merge(self._rec()), 3)
        store2 = wdi.WebDailyStore(self.store.path)
        self.assertEqual(store2.matched_count(), 1)
        vals, dates = store2.get_series('A', 'P', '非甲烷总烃')
        self.assertEqual(dates, ['2026-11-02', '2026-11-03', '2026-11-07'])
        self.assertAlmostEqual(sum(vals), 8.82, places=2)

    def test_merge_updates_existing(self):
        self.store.merge(self._rec())
        self.store.merge(self._rec(days={'2026-11-08': 1.04}))
        vals, dates = self.store.get_series('A', 'P', '非甲烷总烃')
        self.assertEqual(len(dates), 4)

    def test_date_range_filter(self):
        self.store.merge(self._rec())
        vals, dates = self.store.get_series('A', 'P', '非甲烷总烃',
                                            '2026-11-03', '2026-11-07')
        self.assertEqual(dates, ['2026-11-03', '2026-11-07'])
        self.assertAlmostEqual(sum(vals), 7.0, places=2)

    def test_unknown_series_empty(self):
        self.assertEqual(self.store.get_series('X', 'Y', 'Z'), ([], []))


class TestWorkerPrefersImported(unittest.TestCase):
    """worker 日分支应优先使用导入的官网序列作为基准"""

    def test_worker_baseline_uses_imported(self):
        import datetime as _dt
        sys.path.insert(0, os.path.join(os.path.dirname(
            os.path.abspath(__file__))))
        from test_daily_emission_worker import _make_worker
        from web_daily_import import WebDailyStore

        today = _dt.date.today()
        days = [(today - _dt.timedelta(days=i)).strftime('%Y-%m-%d')
                for i in range(7, 2, -1)]          # 5 天
        vals_kg = [2.0, 4.0, 6.0, 8.0, 10.0]       # 均值 6.0
        tmp = tempfile.mkdtemp()
        store = WebDailyStore(os.path.join(tmp, 'w.json'))
        store.merge({'测试企业|1#排口|二氧化硫': {
            'ent': '测试企业', 'subname': '1#排口', 'param': '二氧化硫',
            'unit_src': 't', 'dates': days,
            'values_kg': dict(zip(days, vals_kg))}})

        old = wdi._GLOBAL_STORE
        wdi._GLOBAL_STORE = store
        try:
            worker, _ = _make_worker('日排放量预测', daily_forecast_days=3)
            cap = []
            worker.prediction_done.connect(lambda p: cap.append(p))
            worker.run()
        finally:
            wdi._GLOBAL_STORE = old
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertTrue(cap and cap[-1], '未产出预测结果')
        so2 = next(p for p in cap[-1] if p['param'] == '二氧化硫')
        self.assertAlmostEqual(so2['baseline_value'], 6.0, places=3)
        self.assertEqual(so2['data_source'], '官网导入')
        self.assertEqual(so2['baseline_days'], 5)


class TestUiButton(unittest.TestCase):

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

    def test_button_present_and_bound(self):
        btn = self.win.import_web_daily_btn
        self.assertIn('导入官网日数据', btn.text())
        self.assertGreaterEqual(btn.receivers(btn.clicked), 1)
        self.assertTrue(callable(getattr(self.win, '_import_web_daily', None)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
