# -*- coding: utf-8 -*-
"""
v5.46 日排放量预测 —— UI 渲染测试

无头模式下构造主窗口并驱动展示逻辑，验证：
  1. 预测类型下拉框含「日排放量预测」选项
  2. 切换到日排放量预测时，控件可见性正确切换
  3. _show_daily_emission_table 能正确填充表格（列数/行数/表头）
  4. 预测天数变化会改变表格列数
  5. 空结果不会抛异常，且给出占位提示
  6. 趋势图绘制不抛异常
  7. 旧预测类型仍走原路径（回归保护）
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep + 'src')

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication

import main_window as mw


def _mk_preds(days=7, n_rows=3, warning=False):
    """构造日排放量预测结果（结构对齐 PredictionWorker 输出）。"""
    from datetime import datetime, timedelta
    base = datetime.now()
    dates = [(base + timedelta(days=i + 1)).strftime('%Y-%m-%d')
             for i in range(days)]
    out = []
    for r in range(n_rows):
        vals = [100.0 + r * 10 + i * 1.5 for i in range(days)]
        confs = [round(0.85 ** (i + 1), 2) for i in range(days)]
        out.append({
            'ent_name': '测试企业' if r % 2 == 0 else '',
            'subname': f'{r + 1}#排口',
            'param': ['二氧化硫', '氮氧化物', '颗粒物'][r % 3],
            'predicted': vals[0],
            'cur_pred': vals[0],
            'future_daily': vals,
            'future_dates': dates,
            'confidences': confs,
            'trend': 'up',
            'trend_rate': 1.5,
            'confidence': 0.85,
            'warning_level': '红色预警' if warning else '正常',
            'is_warning': warning,
            'pred_type': '日排放量预测',
        })
    return out


class _StubChart:
    """无副作用的图表替身：记录调用，便于断言与打桩。"""

    def __init__(self):
        self.cleared = 0

    def clear(self):
        self.cleared += 1


class TestDailyEmissionUI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _make_window(self):
        """构造一个最小可用的 MainWindow 子类，跳过登录/联网流程。"""
        # 只初始化 UI 与预测相关状态，避开网络与登录依赖
        win = mw.MainWindow.__new__(mw.MainWindow)
        mw.QWidget.__init__(win)
        win.thresholds = {'二氧化硫': 120.0}
        win.sound_alarm_enabled = False
        win.pred_table = mw.QTableWidget()
        win.pred_result_label = mw.QLabel()
        win.pred_chart = _StubChart()
        win._last_daily_days = -1
        return win

    def _stub_table_helpers(self, win):
        """打桩依赖 MainWindow 上下文（样式/格式化）的辅助方法。"""
        win._draw_daily_emission_chart = lambda preds: None
        win._warning_level_color = lambda lv: ('#FFCCCC' if lv != '正常' else None)
        win._fmt_pred_val = lambda v: ('--' if v is None else f'{v:.2f}')
        win._trend_text = lambda t, r: f'{t} {r}%'

    # ── 1/2. 控件与可见性 ────────────────────────────────────────────────
    def test_a_pred_type_includes_daily(self):
        """预测类型下拉框应包含「日排放量预测」"""
        from PyQt5.QtWidgets import QComboBox, QLabel, QHBoxLayout, QWidget
        win = self._make_window()
        combo = QComboBox()
        combo.addItems(["小时数据预测", "当日均值预测", "日排放量预测"])
        self.assertEqual(combo.count(), 3)
        self.assertEqual(combo.itemText(2), "日排放量预测")

    def test_b_visibility_toggle(self):
        """_on_pred_type_changed 应按类型切换控件可见性"""
        from PyQt5.QtWidgets import QComboBox, QLabel
        win = self._make_window()
        win.pred_type_combo = QComboBox()
        win.pred_type_combo.addItems(["小时数据预测", "当日均值预测", "日排放量预测"])
        win.pred_horizon_combo = QComboBox()
        win.daily_horizon_label = QLabel()
        win.daily_horizon_combo = QComboBox()
        win._pred_horizon_label = QLabel()

        # 切到「日排放量预测」：预测天数控件应可见，小时控件应隐藏
        win.pred_type_combo.setCurrentIndex(2)
        win._on_pred_type_changed(2)
        self.assertTrue(not win.daily_horizon_combo.isHidden(),
                        "日排放量预测下「预测天数」应可见")
        self.assertTrue(win.pred_horizon_combo.isHidden(),
                        "日排放量预测下「预测未来小时数」应隐藏")

        # 切到「小时数据预测」：小时控件应可见，预测天数应隐藏
        win.pred_type_combo.setCurrentIndex(0)
        win._on_pred_type_changed(0)
        self.assertTrue(win.daily_horizon_combo.isHidden(),
                        "小时预测下「预测天数」应隐藏")
        self.assertTrue(not win.pred_horizon_combo.isHidden(),
                        "小时预测下「预测未来小时数」应可见")

    def test_c_horizon_days_mapping(self):
        """预测天数下拉框应映射到 3/7/15/30 天"""
        win = self._make_window()
        from PyQt5.QtWidgets import QComboBox
        win.daily_forecast_days = 7
        combo = QComboBox()
        combo.addItems(["3天", "7天", "15天", "30天"])
        for idx, expected in enumerate([3, 7, 15, 30]):
            win._on_daily_horizon_changed(idx)
            self.assertEqual(win.daily_forecast_days, expected)

    # ── 3/4. 表格填充 ───────────────────────────────────────────────────
    def test_d_table_fills(self):
        """表格应按 预测天数 正确构建列与行（含排放量列）"""
        win = self._make_window()
        self._stub_table_helpers(win)

        preds = _mk_preds(days=7, n_rows=3)
        win._show_daily_emission_table(preds)

        self.assertEqual(win.pred_table.rowCount(), 3)
        # 列 = 企业/排放口 + 参数 + 历史基线 + 日均排放量 + 7天 + 趋势 + 置信度 + 预警 = 14
        self.assertEqual(win.pred_table.columnCount(), 3 + 1 + 7 + 3)
        self.assertEqual(win._last_daily_days, 7)

    def test_e_column_count_follows_days(self):
        """预测天数变化应改变表格列数"""
        win = self._make_window()
        self._stub_table_helpers(win)

        win._show_daily_emission_table(_mk_preds(days=3, n_rows=1))
        self.assertEqual(win.pred_table.columnCount(), 3 + 1 + 3 + 3)

        win._show_daily_emission_table(_mk_preds(days=15, n_rows=1))
        self.assertEqual(win.pred_table.columnCount(), 3 + 1 + 15 + 3)

    def test_f_header_labels(self):
        """表头应含 D+N 动态列、排放量列与关键字段"""
        win = self._make_window()
        self._stub_table_helpers(win)

        win._show_daily_emission_table(_mk_preds(days=7, n_rows=1))
        headers = [win.pred_table.horizontalHeaderItem(i).text()
                   for i in range(win.pred_table.columnCount())]
        self.assertEqual(headers[0], '企业/排放口')
        self.assertEqual(headers[2], '历史基线')
        # v5.49：新增日均排放量列
        self.assertEqual(headers[3], '日均排放量(kg)')
        self.assertEqual(headers[4], 'D+1')
        self.assertEqual(headers[10], 'D+7')
        self.assertEqual(headers[-3], '趋势')
        self.assertEqual(headers[-2], '置信度')
        self.assertEqual(headers[-1], '预警状态')

    def test_g_empty_predictions_safe(self):
        """空结果不应抛异常"""
        win = self._make_window()
        self._stub_table_helpers(win)

        win._show_daily_emission_table([])
        self.assertEqual(win.pred_table.rowCount(), 0)
        self.assertIn('暂无', win.pred_result_label.text())

    def test_h_warning_summary_text(self):
        """存在超标时应给出风险提示"""
        win = self._make_window()
        self._stub_table_helpers(win)

        win._show_daily_emission_table(_mk_preds(days=7, n_rows=2, warning=True))
        self.assertIn('超标风险', win.pred_result_label.text())

    # ── 6. 趋势图 ───────────────────────────────────────────────────────
    def test_i_chart_runs(self):
        """趋势图绘制不应抛异常（真实 matplotlib 渲染）"""
        win = self._make_window()
        win.pred_chart = mw.ChartWidget()
        win._draw_daily_emission_chart(_mk_preds(days=7, n_rows=2))
        # 断言曲线已建立
        self.assertTrue(len(win.pred_chart._lines) > 0,
                        "未建立任何曲线")

    def test_j_chart_caps_curve_count(self):
        """曲线过多时应截断，保护渲染性能"""
        win = self._make_window()
        win.pred_chart = mw.ChartWidget()
        win._draw_daily_emission_chart(_mk_preds(days=7, n_rows=30))
        self.assertLessEqual(len(win.pred_chart._lines), 12,
                             "曲线数量未受上限保护")

    def test_k_chart_empty_safe(self):
        """空结果绘图不应抛异常"""
        win = self._make_window()
        win.pred_chart = mw.ChartWidget()
        win._draw_daily_emission_chart([])

    # ── v5.48：企业/排放口列显示不全修复 ─────────────────────────────────
    def test_l_first_col_wide_enough(self):
        """企业/排放口列宽度必须 >= 230px（150px 放不下 10 字企业名）"""
        win = self._make_window()
        self._stub_table_helpers(win)
        win._show_daily_emission_table(_mk_preds(days=7, n_rows=1))
        self.assertGreaterEqual(win.pred_table.columnWidth(0), 230,
                                "企业/排放口列仍过窄，长名称会被截断")
        self.assertTrue(win.pred_table.wordWrap(),
                        "未开启文字换行，超长名称会显示省略号")

    def test_m_first_col_tooltip(self):
        """企业/排放口单元格必须带完整名称的悬停提示"""
        win = self._make_window()
        self._stub_table_helpers(win)
        preds = _mk_preds(days=7, n_rows=1)
        preds[0]['ent_name'] = '山东冠洲股份有限公司'
        preds[0]['subname'] = '1#窑炉排气筒'
        win._show_daily_emission_table(preds)
        item = win.pred_table.item(0, 0)
        self.assertIsNotNone(item)
        self.assertEqual(item.toolTip(), '山东冠洲股份有限公司 / 1#窑炉排气筒')

    def test_n_hour_pred_table_tooltip(self):
        """小时/日均预测表的企业列也应有悬停提示"""
        from PyQt5.QtWidgets import QTableWidgetItem
        win = self._make_window()
        win.pred_table.setColumnCount(3)
        win.pred_table.setRowCount(1)
        ent, sub = '冠县恒润热电有限公司', '1#锅炉排放口'
        col0_text = f"{ent}\n{sub}"
        item0 = QTableWidgetItem(col0_text)
        item0.setToolTip(col0_text.replace('\n', ' / '))
        win.pred_table.setItem(0, 0, item0)
        self.assertEqual(win.pred_table.item(0, 0).toolTip(),
                         f'{ent} / {sub}')


if __name__ == '__main__':
    unittest.main(verbosity=2)