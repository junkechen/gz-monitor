# -*- coding: utf-8 -*-
"""v5.90 回归测试：实时预警三处致命缺陷修复。

背景（2026-11-28 用户反馈「冠洲股份废水氨氮持续上升却无任何提醒」）：
  1. 实时接口参数名带单位后缀（「氨氮(mg/L)」「PH」「非甲烷总烃(mg/m3)」），
     与 IMPORTANT_PARAMS / 阈值配置的无单位名不匹配 → 所有参数被 continue 跳过，
     实时预警从未执行任何检测（v5.18 起静默失效）。
  2. warning_system.py 模块级缺少 `from collections import deque`（只在 __init__
     内局部导入）→ check_and_alert 同值检测分支 NameError（被上层吞掉）。
  3. check_and_alert_predictions 中 effective_level 在迟滞逻辑中先使用后赋值
     → NameError（预测预警从未生效）。
  4. api_client.py（旧副本）get_realtime_data 引用未导入的 sys/os → NameError
     被多账户并发拉取的 except 吞掉。

本测试覆盖 1/2/3 的用户可见行为；4 由 py_compile + import 检查覆盖。
"""
import os
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'src'))

from warning_system import WarningSystem  # noqa: E402


def _ws() -> WarningSystem:
    ws = WarningSystem()
    # 测试不落盘：禁用历史文件写入（避免污染 data/warning_history.json）
    ws._save_history = lambda: None
    ws.warning_history = []
    return ws


ENT = '山东冠洲股份有限公司'


def _data(params):
    return {'1716|' + ENT: {
        'subid': '1716', 'ent_name': ENT, 'subname': '总排口',
        'subtype': '废水', 'params': params,
    }}


class TestParamNameNormalize(unittest.TestCase):
    """实时参数名归一化（修复1）"""

    def setUp(self):
        self.ws = _ws()

    def test_unit_suffix_with_code(self):
        self.assertEqual(self.ws._norm_param_name(
            {'name': '氨氮(mg/L)', 'code': '311'}), '氨氮')
        self.assertEqual(self.ws._norm_param_name(
            {'name': '化学需氧量(mg/L)', 'code': '316'}), '化学需氧量')
        self.assertEqual(self.ws._norm_param_name(
            {'name': '非甲烷总烃(mg/m3)', 'code': '383'}), '非甲烷总烃')

    def test_case_and_html_code(self):
        # 实时行 C0001_ITEM_CODE 是浮点数
        self.assertEqual(self.ws._norm_param_name(
            {'name': 'PH', 'code': 302.0}), 'pH值')

    def test_fallback_strip_unit(self):
        self.assertEqual(self.ws._norm_param_name({'name': '氨氮(mg/L)'}), '氨氮')
        self.assertEqual(self.ws._norm_param_name({'name': '氨氮'}), '氨氮')

    def test_float_code_to_name(self):
        self.assertEqual(self.ws._norm_param_name(
            {'name': '碳氢化合物(总烃)(mg/m3)', 'code': 220.0}), '碳氢化合物总烃')


class TestRealtimeWarningTriggers(unittest.TestCase):
    """修复后实时预警可真正触发（修复1+2 联合）"""

    THRESHOLDS = {'氨氮': 12.0}

    def test_overrun_with_realtime_param_name(self):
        """「氨氮(mg/L)」15.0 须触发橙色（修复前参数名不匹配 → 零预警）"""
        ws = _ws()
        ws.check_and_alert(_data([
            {'name': '氨氮(mg/L)', 'code': '311', 'value': 15.0},
        ]), self.THRESHOLDS)
        self.assertEqual(len(ws._last_realtime_details), 1)
        d = ws._last_realtime_details[0]
        self.assertEqual(d['param'], '氨氮')
        self.assertEqual(d['level'], '橙色预警')
        self.assertEqual(d['type'], 'realtime')

    def test_rapid_rise_with_realtime_param_name(self):
        """3.01 → 8.9（196%）须触发急剧上升黄色（修复前零预警）"""
        ws = _ws()
        ws._last_value[(ENT, '总排口', '氨氮')] = 3.01
        ws.check_and_alert(_data([
            {'name': '氨氮(mg/L)', 'code': '311', 'value': 8.9},
        ]), self.THRESHOLDS)
        self.assertEqual(len(ws._last_realtime_details), 1)
        d = ws._last_realtime_details[0]
        self.assertEqual(d['type'], 'realtime_rapidchange')
        self.assertEqual(d['level'], '黄色预警')

    def test_same_value_branch_no_nameerror(self):
        """同值检测分支首次执行不得 NameError（修复2：deque 模块级导入）"""
        ws = _ws()
        # 氨氮在 SAME_VALUE_THRESHOLDS 中，首次执行即走 deque 分支
        try:
            from config import SAME_VALUE_THRESHOLDS
            self.assertIn('氨氮', SAME_VALUE_THRESHOLDS)
        except ImportError:
            self.skipTest('config.SAME_VALUE_THRESHOLDS 不可用')
        ws.check_and_alert(_data([
            {'name': '氨氮(mg/L)', 'code': '311', 'value': 5.0},
        ]), self.THRESHOLDS)
        hist_key = (ENT, '总排口', '氨氮')
        self.assertIn(hist_key, ws._same_value_history)
        self.assertEqual(len(ws._same_value_history[hist_key]), 1)

    def test_normal_value_no_warning(self):
        """低于阈值且变化小 → 不预警（防误报）"""
        ws = _ws()
        ws._last_value[(ENT, '总排口', '氨氮')] = 8.5
        ws.check_and_alert(_data([
            {'name': '氨氮(mg/L)', 'code': '311', 'value': 8.9},
        ]), self.THRESHOLDS)
        self.assertEqual(ws._last_realtime_details, [])


class TestPredictionWarningHysteresis(unittest.TestCase):
    """修复3：预测预警 effective_level 先赋值后使用"""

    def test_prediction_no_nameerror_after_debounce(self):
        ws = _ws()
        items = [{'subname': '总排口', 'ent_name': ENT, 'param': '氨氮',
                  'predicted': 15.0, 'warning_level': '橙色预警',
                  'pred_type': '当日均值', 'confidence': 0.9}] * 3
        # 修复前：达到防抖次数后进入迟滞逻辑 → NameError
        ws.check_and_alert_predictions(items, {'氨氮': 12.0})
        self.assertTrue(ws._last_pred_details)
        self.assertEqual(ws._last_pred_details[0]['param'], '氨氮')


class TestApiClientImports(unittest.TestCase):
    """修复4：api_client.py 模块级导入 sys/os"""

    def test_api_client_has_sys_os(self):
        import api_client
        self.assertTrue(hasattr(api_client, 'sys'))
        self.assertTrue(hasattr(api_client, 'os'))


if __name__ == '__main__':
    unittest.main()
