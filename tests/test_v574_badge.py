# -*- coding: utf-8 -*-
"""v5.74 异常记录页签角标：日常在其他页签也能看到未处理数量"""
import os
import sys
import tempfile
import shutil
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from PyQt5.QtWidgets import QApplication  # noqa: E402
from PyQt5.QtCore import QTimer  # noqa: E402

import main_window as mw  # noqa: E402
from abnormal_scanner import AbnormalStore, TYPE_EXCEED, TYPE_FAULT  # noqa: E402
from multi_account_api import GZMultiAccountClient  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)
TITLE = '⚠️ 异常记录'


def _rec(time, rtype=TYPE_EXCEED, code='383'):
    return {'time': time, 'ent': '测试企业', 'subname': '排口1', 'subid': '100',
            'param': '非甲烷总烃', 'code': code, 'type': rtype, 'value': '55',
            'unit': 'mg/m³', 'std': '50', 'desc': '', 'state_raw': '1',
            'status_raw': '', 'detected_at': time + ':05', 'source': '24h扫描'}


class TestAbnormalTabBadge(unittest.TestCase):

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
        self.win._update_abnormal_tab_badge()

    def _tab(self):
        return self.win.right_panel.indexOf(self.win.abnormal_tab)

    def test_no_unhandled_no_badge(self):
        self.assertEqual(self.win.right_panel.tabText(self._tab()), TITLE)
        self.assertEqual(self.win.right_panel.tabToolTip(self._tab()),
                         '暂无未处理异常')

    def test_badge_shows_count(self):
        self.win.abnormal_store.add_records([
            _rec('2026-11-07 08:00'),
            _rec('2026-11-07 09:00', TYPE_FAULT),
            _rec('2026-11-07 10:00', code='525'),
        ])
        self.win._update_abnormal_tab_badge()
        self.assertEqual(self.win.right_panel.tabText(self._tab()),
                         f'{TITLE} (3)')
        self.assertIn('未处理异常 3 条',
                      self.win.right_panel.tabToolTip(self._tab()))

    def test_badge_clears_after_all_handled(self):
        self.win.abnormal_store.add_records([_rec('2026-11-07 08:00')])
        self.win._update_abnormal_tab_badge()
        self.assertIn('(1)', self.win.right_panel.tabText(self._tab()))

        recs = list(self.win.abnormal_store.records)
        self.assertEqual(self.win.abnormal_store.mark_handled(recs, True), 1)
        self.win._update_abnormal_tab_badge()
        self.assertEqual(self.win.right_panel.tabText(self._tab()), TITLE)

    def test_partial_handle_keeps_remaining_count(self):
        self.win.abnormal_store.add_records([
            _rec('2026-11-07 08:00'),
            _rec('2026-11-07 09:00', TYPE_FAULT),
        ])
        self.win.abnormal_store.mark_handled(
            [self.win.abnormal_store.records[0]], True)
        self.win._update_abnormal_tab_badge()
        self.assertEqual(self.win.right_panel.tabText(self._tab()),
                         f'{TITLE} (1)')

    def test_refresh_table_updates_badge(self):
        """切页/查询触发的表格刷新也要同步角标"""
        self.win.abnormal_store.add_records([_rec('2026-11-07 08:00')])
        self.win.abnormal_start_dt.setDateTime(
            self.win.abnormal_start_dt.dateTime().addDays(-2))
        self.win._refresh_abnormal_table()
        self.assertEqual(self.win.right_panel.tabText(self._tab()),
                         f'{TITLE} (1)')


if __name__ == '__main__':
    unittest.main(verbosity=2)
