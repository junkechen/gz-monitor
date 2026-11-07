# -*- coding: utf-8 -*-
"""v5.73 异常处理状态（已处理/未处理）单元测试

需求：在日常工作与数据标记中能看到异常是否已经处理。
覆盖：存储层字段/标记/筛选/计数/向后兼容/重复扫描保留状态，
      主窗口表格列、筛选下拉、标记按钮接线与导出字段。
"""
import os
import sys
import json
import tempfile
import shutil
import unittest
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from PyQt5.QtWidgets import QApplication, QPushButton, QTableWidget  # noqa: E402
from PyQt5.QtCore import QTimer  # noqa: E402

import main_window as mw  # noqa: E402
from abnormal_scanner import (  # noqa: E402
    AbnormalStore, TYPE_EXCEED, TYPE_FAULT,
)
from multi_account_api import GZMultiAccountClient  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)


def _rec(**kw):
    base = dict(time='2026-11-07 08:00', ent='测试企业', subname='排口1',
                subid='100', param='非甲烷总烃', code='383',
                type=TYPE_EXCEED, value='55', unit='mg/m³', std='50',
                desc='', state_raw='1', status_raw='',
                detected_at='2026-11-07 08:05:00', source='24h扫描')
    base.update(kw)
    return base


class TestStoreHandled(unittest.TestCase):
    """存储层：处理状态字段、标记、筛选、计数"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, 'abnormal_records.json')
        self.store = AbnormalStore(self.path)
        self.store.add_records([
            _rec(time='2026-11-07 08:00'),
            _rec(time='2026-11-07 09:00', type=TYPE_FAULT),
            _rec(time='2026-11-07 10:00'),
        ])

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_new_records_default_unhandled(self):
        self.assertTrue(all(r['handled'] is False for r in self.store.records))
        self.assertEqual(self.store.unhandled_count(), 3)

    def test_mark_handled_and_persist(self):
        target = [r for r in self.store.records if r['time'] == '2026-11-07 08:00']
        n = self.store.mark_handled(target, True, operator='张工', note='已通知企业')
        self.assertEqual(n, 1)
        rec = target[0]
        self.assertTrue(rec['handled'])
        self.assertTrue(rec['handled_at'])
        self.assertEqual(rec['handled_by'], '张工')
        self.assertEqual(rec['handle_note'], '已通知企业')
        self.assertEqual(self.store.unhandled_count(), 2)
        # 落盘后重新加载保持
        store2 = AbnormalStore(self.path)
        hit = [r for r in store2.records if r['time'] == '2026-11-07 08:00'][0]
        self.assertTrue(hit['handled'])
        self.assertEqual(hit['handled_by'], '张工')

    def test_unmark(self):
        target = [self.store.records[0]]
        self.store.mark_handled(target, True)
        self.store.mark_handled(target, False)
        self.assertFalse(target[0]['handled'])
        self.assertEqual(target[0]['handled_at'], '')
        self.assertEqual(self.store.unhandled_count(), 3)

    def test_query_by_handled(self):
        self.store.mark_handled([self.store.records[0]], True)
        self.assertEqual(len(self.store.query(handled=True)), 1)
        self.assertEqual(len(self.store.query(handled=False)), 2)
        self.assertEqual(len(self.store.query()), 3)      # None=全部

    def test_rescan_keeps_handled_state(self):
        self.store.mark_handled([self.store.records[0]], True)
        # 同一异常再次被扫描到：去重不覆盖，处理状态必须保留
        added = self.store.add_records([_rec(time='2026-11-07 08:00')])
        self.assertEqual(added, 0)
        self.assertTrue(self.store.records[0]['handled'])

    def test_old_records_without_field_are_unhandled(self):
        # 旧版本文件没有 handled 字段
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump([_rec(time='2026-11-06 08:00')], f, ensure_ascii=False)
        store = AbnormalStore(self.path)
        self.assertEqual(store.unhandled_count(), 1)
        self.assertEqual(len(store.query(handled=False)), 1)


class TestAbnormalTabHandledUI(unittest.TestCase):
    """主窗口：处理状态列、筛选、标记按钮、导出字段"""

    @classmethod
    def setUpClass(cls):
        cls.win = mw.MainWindow(GZMultiAccountClient())

    @classmethod
    def tearDownClass(cls):
        for t in cls.win.findChildren(QTimer):
            t.stop()
        cls.win.close()

    def setUp(self):
        self.win.abnormal_store.records = []
        self.win.abnormal_store._index = {}
        self.win.abnormal_store.add_records([
            _rec(time='2026-11-07 08:00'),
            _rec(time='2026-11-07 09:00', type=TYPE_FAULT),
        ])
        self.win.abnormal_handled_combo.setCurrentIndex(0)
        self.win.abnormal_start_dt.setDateTime(
            self.win.abnormal_end_dt.dateTime().addDays(-2))
        self.win.abnormal_ent_combo.setCurrentIndex(0)
        self.win.abnormal_type_combo.setCurrentIndex(0)
        self.win._refresh_abnormal_table()

    def test_status_column_exists(self):
        headers = [self.win.abnormal_table.horizontalHeaderItem(i).text()
                   for i in range(self.win.abnormal_table.columnCount())]
        self.assertIn('处理状态', headers)
        idx = headers.index('处理状态')
        self.assertIn('未处理', self.win.abnormal_table.item(0, idx).text())

    def test_mark_selected_row(self):
        self.win.abnormal_table.selectRow(0)
        self.win._mark_abnormal_handled(True)
        headers = [self.win.abnormal_table.horizontalHeaderItem(i).text()
                   for i in range(self.win.abnormal_table.columnCount())]
        idx = headers.index('处理状态')
        self.assertIn('已处理', self.win.abnormal_table.item(0, idx).text())
        self.assertEqual(self.win.abnormal_store.unhandled_count(), 1)

    def test_mark_without_selection_prompts(self):
        self.win.abnormal_table.clearSelection()
        with mock.patch.object(mw.QMessageBox, 'information') as box:
            self.win._mark_abnormal_handled(True)
            box.assert_called_once()

    def test_handled_filter(self):
        self.win.abnormal_table.selectRow(0)
        self.win._mark_abnormal_handled(True)
        self.win.abnormal_handled_combo.setCurrentIndex(2)   # 已处理
        self.assertEqual(self.win.abnormal_table.rowCount(), 1)
        self.win.abnormal_handled_combo.setCurrentIndex(1)   # 未处理
        self.assertEqual(self.win.abnormal_table.rowCount(), 1)
        self.win.abnormal_handled_combo.setCurrentIndex(0)   # 全部
        self.assertEqual(self.win.abnormal_table.rowCount(), 2)

    def test_unhandled_label_and_status(self):
        self.assertIn('未处理', self.win.abnormal_status_label.text())
        self.assertIn('2', self.win.abnormal_unhandled_label.text())

    def test_mark_buttons_bound(self):
        buttons = {b.text(): b for b in self.win.findChildren(QPushButton)}
        for label in ('✅ 标记已处理', '↩ 标记未处理'):
            self.assertIn(label, buttons)
            self.assertGreaterEqual(buttons[label].receivers(buttons[label].clicked), 1)

    def test_export_includes_handle_fields(self):
        import csv
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, 'out.csv')
        try:
            self.win.abnormal_table.selectRow(0)
            self.win._mark_abnormal_handled(True)
            with mock.patch.object(mw.QFileDialog, 'getSaveFileName',
                                   return_value=(path, '')), \
                 mock.patch.object(mw.QMessageBox, 'information'):
                self.win._export_abnormal('csv')
            with open(path, encoding='utf-8-sig', newline='') as f:
                reader = csv.DictReader(f)
                header = reader.fieldnames or []
                rows = list(reader)
            for col in ('处理状态', '处理时间', '处理人', '处理备注'):
                self.assertIn(col, header)
            status = {r['处理状态'] for r in rows}
            self.assertIn('已处理', status)
            self.assertIn('未处理', status)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
