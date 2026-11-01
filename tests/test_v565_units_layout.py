# -*- coding: utf-8 -*-
"""v5.65 回归测试：历史表列布局与单位标注。

要求：
  1. 浓度类参数 → 「X实测(mg/m³)」+「X排放量(kg)」，热电厂再加「X折算(mg/m³)」
  2. 过程参数（流量/温度等）**不生成**排放量/折算列
  3. 表头不出现「(mg/m³)(mg/m³)」这类重复单位
"""
import os
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'src'))

from PyQt5.QtWidgets import QApplication, QTableWidget  # noqa: E402

_app = QApplication.instance() or QApplication([])
import main_window as mw  # noqa: E402


ROWS = [{'DateTime': '2026-11-01', 'val_383': 11.7, 'val_299': 1.08,
         'val_210': 15869, 'val_525': 128.5}]
CODES = '383,299,210,525'


def _headers(thermal: bool):
    w = mw.MainWindow.__new__(mw.MainWindow)
    w.history_table = QTableWidget()
    w._history_is_thermal_power = thermal
    w._display_history_table(list(ROWS), [], CODES)
    return [w.history_table.horizontalHeaderItem(i).text()
            for i in range(w.history_table.columnCount())]


class TestHistoryHeaderLayout(unittest.TestCase):

    def test_normal_headers(self):
        hdr = _headers(False)
        self.assertIn('非甲烷总烃实测(mg/m³)', hdr)
        self.assertIn('非甲烷总烃排放量(kg)', hdr)
        self.assertIn('烟气流量实测(m³)', hdr)
        self.assertIn('烟气温度实测(℃)', hdr)
        # 过程参数不应有排放量列
        self.assertFalse(any(h.startswith('烟气流量') and '排放量' in h for h in hdr))
        self.assertFalse(any(h.startswith('烟气温度') and '排放量' in h for h in hdr))
        # 不应出现重复单位
        self.assertFalse(any(h.count('mg/m³') > 1 for h in hdr))

    def test_thermal_headers(self):
        hdr = _headers(True)
        self.assertIn('非甲烷总烃实测(mg/m³)', hdr)
        self.assertIn('非甲烷总烃折算(mg/m³)', hdr)
        self.assertIn('非甲烷总烃排放量(kg)', hdr)
        # 过程参数只有实测列
        self.assertFalse(any(h.startswith('烟气流量') and '折算' in h for h in hdr))
        self.assertFalse(any(h.startswith('烟气温度') and '折算' in h for h in hdr))

    def test_no_duplicated_unit(self):
        for thermal in (False, True):
            for h in _headers(thermal):
                self.assertLessEqual(h.count('mg/m³'), 1, f"表头单位重复: {h}")
                self.assertLessEqual(h.count('kg'), 1, f"表头单位重复: {h}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
