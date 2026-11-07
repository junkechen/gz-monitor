# -*- coding: utf-8 -*-
"""v5.75 异常标记状态只读（来源官网「日常工作 → 数据标记」）

需求背景：用户反馈软件里的"标记已处理/标记未处理"是本地状态，容易与环保
平台不一致造成"环保标记错误"。要求只保留标记状态展示，状态以官网
「日常工作 → 数据标记」为准，软件内不可修改。

官网 history 接口的 state_{code}/status_{code} 就是数据标记结果，
（如 state=2 + status='非甲烷总烃故障'），据此判定 已标记 / 待标记。
"""
import os
import sys
import csv
import tempfile
import shutil
import unittest
from datetime import datetime
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from PyQt5.QtWidgets import QApplication, QPushButton  # noqa: E402
from PyQt5.QtCore import QTimer  # noqa: E402

import main_window as mw  # noqa: E402
from abnormal_scanner import (  # noqa: E402
    AbnormalStore, _classify_rows, _is_marked, _mark_text, _warning_records,
    TYPE_EXCEED, TYPE_FAULT,
)
from multi_account_api import GZMultiAccountClient  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


class TestMarkDetection(unittest.TestCase):

    def test_marked_when_state_or_status_present(self):
        self.assertTrue(_is_marked('2', '非甲烷总烃故障'))
        self.assertTrue(_is_marked('1', ''))
        self.assertTrue(_is_marked('', '停产检修'))
        self.assertTrue(_is_marked('F', ''))
        self.assertEqual(_mark_text('2', '非甲烷总烃故障'), '2 / 非甲烷总烃故障')

    def test_unmarked_for_empty_or_normal(self):
        for s, t in (('', ''), ('0', ''), ('N', None), (None, None), ('0', '0')):
            self.assertFalse(_is_marked(s, t), f'{s}/{t}')
            self.assertEqual(_mark_text(s, t), '')

    def test_classify_rows_carries_marked(self):
        rows = [
            {'DateTime': '2026-11-07 07:00',
             'val_383': '0.8', 'state_383': '0', 'status_383': '',
             'val_525': '85', 'state_525': '0', 'status_525': ''},
            {'DateTime': '2026-11-07 08:00',
             'val_383': '0.804', 'state_383': '2', 'status_383': '非甲烷总烃故障',
             'val_525': '-9999', 'state_525': '0', 'status_525': ''},
        ]
        recs = _classify_rows(rows, ['383', '525'], '测试企业', '100', '排口1',
                              '2026-11-07 09:00:00')
        fault = next(r for r in recs if r['type'] == TYPE_FAULT)
        self.assertTrue(fault['marked'])
        self.assertIn('非甲烷总烃故障', fault['mark_text'])
        # 软件自行判定的数据缺失没有官网标记
        missing = next(r for r in recs if r['code'] == '525')
        self.assertFalse(missing['marked'])

    def test_warning_records_unmarked(self):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        out = _warning_records([{'datetime': now, 'ent_name': 'A',
                                 'param': '非甲烷总烃', 'value': 60}], hours=24)
        self.assertEqual(len(out), 1)
        self.assertFalse(out[0]['marked'])


class TestStoreMarked(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, 'a.json')
        self.store = AbnormalStore(self.path)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @staticmethod
    def _rec(time='2026-11-07 08:00', state='2', status='故障', **kw):
        base = {'time': time, 'ent': 'A', 'subname': 'P', 'subid': '1',
                'param': '非甲烷总烃', 'code': '383', 'type': TYPE_FAULT,
                'value': '1.2', 'unit': 'mg/m³', 'std': '50', 'desc': '',
                'state_raw': state, 'status_raw': status,
                'detected_at': time + ':05', 'source': '24h扫描'}
        base.update(kw)
        return base

    def test_auto_marked_on_add(self):
        self.store.add_records([self._rec()])
        self.assertTrue(self.store.records[0]['marked'])
        self.assertEqual(self.store.unmarked_count(), 0)

    def test_query_by_marked(self):
        self.store.add_records([
            self._rec(),
            self._rec(time='2026-11-07 09:00', state='0', status=''),
        ])
        self.assertEqual(len(self.store.query(marked=True)), 1)
        self.assertEqual(len(self.store.query(marked=False)), 1)
        self.assertEqual(len(self.store.query()), 2)

    def test_legacy_handled_records_do_not_break(self):
        """v5.73 的本地 handled 字段不应影响只读标记，且不再被写出"""
        import json
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump({'records': [dict(self._rec(), handled=True,
                                        handled_by='张三')]}, f,
                      ensure_ascii=False)
        store = AbnormalStore(self.path)
        self.assertTrue(store.records[0]['marked'])
        store.add_records([self._rec(time='2026-11-07 10:00')])
        self.assertNotIn('handled', store.records[1])

    def test_no_manual_mark_api(self):
        self.assertFalse(hasattr(self.store, 'mark_handled'),
                         '不应保留本地标记能力')


class TestAbnormalUiReadOnly(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.win = mw.MainWindow(GZMultiAccountClient())
        cls.tmpdir = tempfile.mkdtemp()
        cls.win.abnormal_store = AbnormalStore(os.path.join(cls.tmpdir, 'a.json'))

    @classmethod
    def tearDownClass(cls):
        for t in cls.win.findChildren(QTimer):
            t.stop()
        cls.win.close()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        self.win.abnormal_store.records = []
        self.win.abnormal_store._index = {}
        self.win._abnormal_current = None
        now = datetime.now()
        self.now_str = now.strftime('%Y-%m-%d %H:%M')

    def _rec(self, marked=True, minutes_ago=5):
        from datetime import timedelta
        ts = (datetime.now() - timedelta(minutes=minutes_ago)).strftime('%Y-%m-%d %H:%M')
        state, status = ('2', '非甲烷总烃故障') if marked else ('0', '')
        return {'time': ts, 'ent': 'A', 'subname': 'P', 'subid': '1',
                'param': '非甲烷总烃', 'code': '383', 'type': TYPE_FAULT,
                'value': '1.2', 'unit': 'mg/m³', 'std': '50', 'desc': '',
                'state_raw': state, 'status_raw': status,
                'marked': marked, 'mark_text': '2 / 非甲烷总烃故障' if marked else '',
                'detected_at': ts + ':05', 'source': '24h扫描'}

    def test_no_manual_mark_buttons(self):
        texts = [b.text() for b in self.win.findChildren(QPushButton)]
        self.assertNotIn('✅ 标记已处理', texts)
        self.assertNotIn('↩ 标记未处理', texts)
        self.assertFalse(hasattr(self.win, '_mark_abnormal_handled'))
        self.assertFalse(hasattr(self.win, '_show_abnormal_context_menu'))

    def test_header_is_readonly_mark(self):
        hdr = [self.win.abnormal_table.horizontalHeaderItem(i).text()
               for i in range(self.win.abnormal_table.columnCount())]
        self.assertIn('官网标记', hdr)
        self.assertNotIn('处理状态', hdr)

    def test_mark_filter_combo_items(self):
        combo = self.win.abnormal_marked_combo
        self.assertEqual([combo.itemData(i) for i in range(combo.count())],
                         ['', 'unmarked', 'marked'])

    def test_table_shows_mark_state(self):
        self.win.abnormal_store.add_records([self._rec(True),
                                             self._rec(False, 6)])
        self.win._refresh_abnormal_table()
        texts = [self.win.abnormal_table.item(r, 5).text()
                 for r in range(self.win.abnormal_table.rowCount())]
        self.assertIn('✅ 已标记', texts)
        self.assertIn('⏳ 待标记', texts)

    def test_badge_counts_unmarked(self):
        self.win.abnormal_store.add_records([self._rec(True), self._rec(False, 6)])
        self.win._update_abnormal_tab_badge()
        idx = self.win.right_panel.indexOf(self.win.abnormal_tab)
        self.assertEqual(self.win.right_panel.tabText(idx), '⚠️ 异常记录 (1)')

    def test_export_contains_mark_columns(self):
        self.win.abnormal_store.add_records([self._rec(True)])
        out = os.path.join(self.tmpdir, 'out.csv')
        with mock.patch.object(mw.QFileDialog, 'getSaveFileName',
                               return_value=(out, '')), \
                mock.patch.object(mw.QMessageBox, 'information'):
            self.win._export_abnormal('csv')
        with open(out, 'r', encoding='utf-8-sig') as f:
            header = next(csv.reader(f))
        self.assertIn('官网标记状态', header)
        self.assertIn('官网标记内容', header)
        self.assertNotIn('处理时间', header)


if __name__ == '__main__':
    unittest.main(verbosity=2)
