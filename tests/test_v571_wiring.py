# -*- coding: utf-8 -*-
"""v5.71 主窗口接线回归测试

v5.69 的 test_v569_abnormal.py 只覆盖 data_processor / abnormal_scanner 层，
主窗口这一侧（页签、自动扫描、定时复扫、弹窗、状态栏、按钮绑定、企业名称显示）
一行都没测。这里补齐，防止再次出现 QDateTime 那样的"启动即崩"或半截接线。

运行： QT_QPA_PLATFORM=offscreen C:/Python38/python.exe tests/test_v571_wiring.py
"""
import os
import sys
import unittest
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from PyQt5.QtWidgets import (QApplication, QPushButton, QTableWidget,  # noqa: E402
                            QHeaderView)
from PyQt5.QtCore import QTimer  # noqa: E402

import main_window as mw  # noqa: E402
from multi_account_api import GZMultiAccountClient  # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv)
LONG_NAME = '山东冠洲鼎鑫板材科技有限公司'


class TestLoginDialogNameDisplay(unittest.TestCase):
    """#33 企业名称显示不全：长企业名必须有完整 tooltip，名称列不能再被平分挤窄"""

    def setUp(self):
        self._patch = mock.patch.object(mw, 'load_accounts', return_value=[
            {'name': LONG_NAME, 'password': 'Gzgfah@163.com'},
            {'name': '冠县恒润热电有限公司', 'password': 'x'},
        ])
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    @staticmethod
    def _account_table(dialog):
        for t in dialog.findChildren(QTableWidget):
            hdr = t.horizontalHeaderItem(2)
            if t.columnCount() == 3 and hdr is not None and hdr.text() == '登录状态':
                return t
        return None

    def test_long_name_has_full_tooltip(self):
        d = mw.LoginDialog()
        t = self._account_table(d)
        self.assertIsNotNone(t, '未找到登录页账户表格')
        tip = t.item(0, 0).toolTip()
        self.assertIn(LONG_NAME, tip, 'tooltip 必须含企业全称')
        self.assertNotEqual(tip, '双击可修改企业账号名称', '仍是旧文案')
        d.close()

    def test_name_column_stretch_others_autosize(self):
        d = mw.LoginDialog()
        t = self._account_table(d)
        self.assertEqual(t.horizontalHeader().sectionResizeMode(0),
                         QHeaderView.ResizeMode.Stretch)
        self.assertEqual(t.horizontalHeader().sectionResizeMode(1),
                         QHeaderView.ResizeMode.ResizeToContents)
        self.assertEqual(t.horizontalHeader().sectionResizeMode(2),
                         QHeaderView.ResizeMode.ResizeToContents)
        d.close()


class TestAccountManageDialog(unittest.TestCase):
    """账户管理对话框同样要有全称 tooltip + 自动换行 + 自适应行高"""

    def test_full_name_tooltip_and_wordwrap(self):
        d = mw.AccountManageDialog([
            {'name': LONG_NAME, 'password': 'p'},
            {'name': '冠县恒润热电有限公司', 'password': 'q'},
        ])
        self.assertTrue(d.table.wordWrap())
        self.assertIn(LONG_NAME, d.table.item(0, 0).toolTip())
        self.assertEqual(d.table.horizontalHeader().sectionResizeMode(0),
                         QHeaderView.ResizeMode.Stretch)
        self.assertEqual(d.table.horizontalHeader().sectionResizeMode(1),
                         QHeaderView.ResizeMode.ResizeToContents)
        # 增删账户走 _load_table 重载，行高自适应不能被漏掉
        d.accounts.append({'name': LONG_NAME, 'password': 'r'})
        d._load_table()
        self.assertEqual(d.table.rowCount(), 3)
        self.assertIn(LONG_NAME, d.table.item(2, 0).toolTip())
        d.close()


class TestMainWindowAbnormalWiring(unittest.TestCase):
    """v5.69 主窗口接线：页签/控件/定时器/按钮/弹窗/状态栏口径"""

    @classmethod
    def setUpClass(cls):
        cls.win = mw.MainWindow(GZMultiAccountClient())

    @classmethod
    def tearDownClass(cls):
        for t in cls.win.findChildren(QTimer):
            t.stop()
        cls.win.close()

    def setUp(self):
        self.win._abnormal_scan_running = False
        self.win._abnormal_worker = None
        self.win._abnormal_scan_pending_retries = 0
        self.win.multi_client.clients = {}
        self.win.abnormal_status_label.setText('')

    def test_abnormal_tab_registered(self):
        titles = [self.win.right_panel.tabText(i)
                  for i in range(self.win.right_panel.count())]
        self.assertTrue(any('异常记录' in t for t in titles),
                        f'异常记录页签未注册: {titles}')

    def test_core_widgets_exist(self):
        for attr in ('abnormal_store', 'abnormal_status_label', 'abnormal_table',
                     'abnormal_ent_combo', 'abnormal_type_combo',
                     'abnormal_start_dt', 'abnormal_end_dt',
                     'abnormal_scan_timer'):
            self.assertTrue(hasattr(self.win, attr), f'缺少控件/属性 {attr}')

    def test_auto_rescan_timer_is_30min(self):
        self.assertEqual(self.win.abnormal_scan_timer.interval(), 30 * 60 * 1000)

    def test_toolbar_buttons_bound(self):
        texts = [b.text() for b in self.win.findChildren(QPushButton)]
        for label in ('🔄 立即扫描', '🔍 查询', '📥 导出Excel', '📄 导出CSV'):
            self.assertIn(label, texts, f'缺少按钮 {label}')

        def btn(label):
            return next(b for b in self.win.findChildren(QPushButton)
                        if b.text() == label)

        # PyQt 信号连接时已绑定原 bound method，事后 patch 实例属性不会影响连接，
        # 因此用 receivers() 验证每个按钮确实挂上了槽
        for label in ('🔄 立即扫描', '🔍 查询', '📥 导出Excel', '📄 导出CSV'):
            self.assertGreaterEqual(btn(label).receivers(btn(label).clicked), 1,
                                    f'{label} 未绑定槽函数')
        for name in ('_start_abnormal_scan', '_refresh_abnormal_table',
                     '_export_abnormal'):
            self.assertTrue(callable(getattr(self.win, name, None)),
                            f'缺少可调用的 {name}')

    def test_scan_finished_popup_and_status_wording(self):
        records = [
            {'type': '超标', 'ent': '甲公司'},
            {'type': '故障', 'ent': '甲公司'},
            {'type': '超标', 'ent': '乙公司'},
        ]
        with mock.patch.object(mw.QMessageBox, 'information') as box:
            self.win._on_abnormal_scan_finished(records, 2, None)
            box.assert_called_once()
            text = box.call_args[0][2]
            self.assertIn('共发现 3 条', text)
            self.assertIn('其中新增 2 条', text)
            self.assertIn('含此前已记录项', text, '必须说明明细口径')
        status = self.win.abnormal_status_label.text()
        self.assertTrue(status.startswith('✅ 扫描完成'),
                        f'状态栏被刷新表格覆盖或丢失: {status}')
        self.assertIn('新增 2 条', status)

    def test_no_popup_when_nothing_new(self):
        with mock.patch.object(mw.QMessageBox, 'information') as box:
            self.win._on_abnormal_scan_finished(
                [{'type': '超标', 'ent': '甲公司'}], 0, None)
            box.assert_not_called()
        self.assertTrue(self.win.abnormal_status_label.text().startswith('✅ 扫描完成'))

    def test_scan_error_no_popup(self):
        with mock.patch.object(mw.QMessageBox, 'information') as box:
            self.win._on_abnormal_scan_finished([], 0, '网络超时')
            box.assert_not_called()
        self.assertTrue(self.win.abnormal_status_label.text().startswith('❌ 扫描失败'))

    def test_start_scan_retries_when_not_logged_in(self):
        """#3 修复：未登录时短间隔重试，不再静默等 30 分钟"""
        with mock.patch.object(mw.QTimer, 'singleShot') as ss:
            self.win._start_abnormal_scan()
            ss.assert_called_once()
            self.assertEqual(ss.call_args[0][0], 5000)
            self.assertEqual(ss.call_args[0][1], self.win._start_abnormal_scan)
        self.assertFalse(self.win._abnormal_scan_running)
        self.assertEqual(self.win._abnormal_scan_pending_retries, 1)

    def test_start_scan_gives_up_after_6_retries(self):
        with mock.patch.object(mw.QTimer, 'singleShot') as ss:
            self.win._abnormal_scan_pending_retries = 6
            self.win._start_abnormal_scan()
            ss.assert_not_called()

    def test_start_scan_launches_worker_when_ready(self):
        fake_worker = mock.MagicMock()
        self.win.multi_client.clients = {'甲公司': object()}
        self.win._abnormal_scan_pending_retries = 3
        with mock.patch.object(mw, 'AbnormalScanWorker', return_value=fake_worker) as ctor:
            self.win._start_abnormal_scan()
            ctor.assert_called_once()
            fake_worker.start.assert_called_once()
        self.assertEqual(self.win._abnormal_scan_pending_retries, 0,
                         '登录就绪后应重置重试计数')
        self.assertTrue(self.win._abnormal_scan_running)
        # 还原，避免影响后续用例
        self.win._abnormal_scan_running = False
        self.win._abnormal_worker = None
        self.win.multi_client.clients = {}


if __name__ == '__main__':
    unittest.main(verbosity=2)
