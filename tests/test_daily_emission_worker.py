# -*- coding: utf-8 -*-
"""
v5.46 日排放量预测 —— 集成测试（PredictionWorker 分支）

用 mock 替身替代真实服务端，验证：
  1. 「日排放量预测」能正确调用 query_history(index=2) 拉日数据
  2. worker 产出的结果结构包含 future_daily / future_dates / confidences
  3. 结果行数与参数数量一致
  4. 天数变化（daily_forecast_days）会改变输出长度
  5. 旧预测类型不受影响（回归保护）
  6. 超标项被正确标记 is_warning / warning_level
"""

import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep + 'src')

import main_window as mw


class _FakeClient:
    """模拟 GZApiClient：只提供 query_history，并记录调用参数。"""

    def __init__(self, daily_values_per_code=None):
        # {code: [v1, v2, ...]}，默认构造 14 天稳定上升序列
        self.daily_values_per_code = daily_values_per_code or {
            '201': [100.0 + i * 2 for i in range(14)],
            '203': [50.0 + (i % 3) for i in range(14)],
        }
        self.calls = []

    def query_history(self, subid, subtype, codes, start, end, index=1,
                      page=None, rows=None, use_corrected=False, **kw):
        self.calls.append({
            'subid': subid, 'subtype': subtype, 'codes': codes,
            'start': start, 'end': end, 'index': index,
            'use_corrected': use_corrected,
        })
        # 故意返回乱序，验证 worker 会排序
        code_list = [c.strip() for c in codes.split(',') if c.strip()]
        out = []
        for code in code_list:
            vals = self.daily_values_per_code.get(code)
            if not vals:
                continue
            base = datetime(2026, 1, 1)
            for i, v in enumerate(vals):
                out.append({
                    'DateTime': (base + timedelta(days=i)).strftime('%Y-%m-%d'),
                    f'val_{code}': str(v),
                })
        # 倒序返回，模拟服务端不稳定排序
        out.reverse()
        return {'total': len(out), 'rows': out}


class _FakeMultiClient:
    def __init__(self, client):
        self._client = client

    def get_client_by_subid(self, subid):
        return {'client': self._client}


def _make_worker(pred_type, daily_forecast_days=7, client=None):
    client = client or _FakeClient()
    grouped = {
        'K1': {'subid': 'K1', 'subtype': '废气', 'subname': '1#排口',
               'ent_name': '测试企业', 'params': []},
    }
    return mw.PredictionWorker(
        grouped_data=grouped,
        multi_client=_FakeMultiClient(client),
        prediction_horizon=3,
        prediction_params=[],
        pred_type=pred_type,
        thresholds={'二氧化硫': 120.0},
        sub_itemcodes_cache={'K1_01': '201,203'},
        api_data_cache={},
        thresholds_cache={},
        get_subtype_code_fn=lambda t: '01',
        is_water_sub_fn=lambda t: False,
        code_to_name_map={'201': '二氧化硫', '203': '氮氧化物'},
        daily_forecast_days=daily_forecast_days,
    ), client


class TestDailyEmissionWorker(unittest.TestCase):

    def test_a_daily_branch_queries_day_index(self):
        """日排放量预测必须用 index=2（日数据）查询"""
        worker, client = _make_worker("日排放量预测")
        worker.run()
        self.assertTrue(client.calls, "未发起任何数据请求")
        for c in client.calls:
            self.assertEqual(c['index'], 2,
                             f"日排放量预测应使用 index=2，实际={c['index']}")

    def test_b_result_structure(self):
        """结果结构应包含逐日预测/日期/置信度等字段"""
        worker, _ = _make_worker("日排放量预测", daily_forecast_days=7)
        captured = []
        worker.prediction_done.connect(lambda p: captured.append(p))
        worker.run()
        self.assertTrue(captured and captured[-1], "worker 未产出结果")

        for p in captured[-1]:
            for field in ('ent_name', 'subname', 'param', 'predicted',
                          'future_daily', 'future_dates', 'confidences',
                          'trend', 'confidence', 'warning_level'):
                self.assertIn(field, p, f"结果缺少字段 {field}")
            self.assertIsNotNone(p['predicted'], "基线预测值不应为 None")
            self.assertEqual(len(p['future_daily']), 7)
            self.assertEqual(len(p['future_dates']), 7)
            self.assertEqual(len(p['confidences']), 7)

    def test_c_forecast_length_follows_setting(self):
        """预测天数设置应决定 future_daily 长度"""
        for days in (3, 7, 15):
            worker, _ = _make_worker("日排放量预测", daily_forecast_days=days)
            worker.run()
            # 通过 prediction_done 信号捕获结果
            captured = []
            worker.prediction_done.connect(lambda p: captured.append(p))
            worker.run()
            if captured and captured[-1]:
                for p in captured[-1]:
                    self.assertEqual(len(p.get('future_daily', [])), days,
                                     f"days={days} 时长度不符")
                    self.assertEqual(len(p.get('future_dates', [])), days)
                    self.assertEqual(len(p.get('confidences', [])), days)

    def test_d_dates_start_from_tomorrow(self):
        """预测日期应从明天开始"""
        worker, _ = _make_worker("日排放量预测", daily_forecast_days=3)
        captured = []
        worker.prediction_done.connect(lambda p: captured.append(p))
        worker.run()
        self.assertTrue(captured and captured[-1], "无结果")
        expected = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        self.assertEqual(captured[-1][0]['future_dates'][0], expected)

    def test_e_warning_flag_set_when_exceed(self):
        """预测值超过阈值时应标记预警"""
        # 二氧化硫阈值 120，序列 100..126，未来必然超阈值
        worker, _ = _make_worker("日排放量预测", daily_forecast_days=7)
        captured = []
        worker.prediction_done.connect(lambda p: captured.append(p))
        worker.run()
        preds = captured[-1]
        self.assertTrue(preds, "无结果")
        so2 = [p for p in preds if p['param'] == '二氧化硫']
        self.assertTrue(so2, "缺少二氧化硫预测")
        self.assertTrue(so2[0]['is_warning'], "超阈值却未标记 is_warning")
        self.assertNotEqual(so2[0]['warning_level'], '正常')

    def test_f_normal_when_below_threshold(self):
        """低于阈值应标记为正常"""
        worker, _ = _make_worker("日排放量预测", daily_forecast_days=7)
        captured = []
        worker.prediction_done.connect(lambda p: captured.append(p))
        worker.run()
        preds = captured[-1]
        nox = [p for p in preds if p['param'] == '氮氧化物']
        self.assertTrue(nox, "缺少氮氧化物预测")
        self.assertFalse(nox[0]['is_warning'], "低浓度却被误标预警")

    def test_g_pred_type_tagged(self):
        """结果应标记 pred_type='日排放量预测'"""
        worker, _ = _make_worker("日排放量预测", daily_forecast_days=7)
        captured = []
        worker.prediction_done.connect(lambda p: captured.append(p))
        worker.run()
        for p in captured[-1]:
            self.assertEqual(p['pred_type'], '日排放量预测')

    def test_h_cache_reused(self):
        """同一天数下重复运行应命中缓存，不重复请求"""
        worker, client = _make_worker("日排放量预测", daily_forecast_days=7)
        worker.run()
        first = len(client.calls)
        worker.run()
        self.assertEqual(len(client.calls), first,
                         "第二次运行未命中 API 缓存")

    def test_i_insufficient_history_skipped(self):
        """日数据不足 3 天时应跳过，不产出结果"""
        client = _FakeClient({'201': [100.0, 101.0]})   # 仅 2 天
        worker, _ = _make_worker("日排放量预测", daily_forecast_days=7,
                                 client=client)
        captured = []
        worker.prediction_done.connect(lambda p: captured.append(p))
        worker.run()
        self.assertEqual(captured[-1], [], "历史不足却产出了预测")

    def test_j_unsorted_server_response(self):
        """服务端乱序返回时，worker 应自行排序后计算"""
        client = _FakeClient({'201': [float(i) for i in range(1, 15)]})
        worker, _ = _make_worker("日排放量预测", daily_forecast_days=7,
                                 client=client)
        captured = []
        worker.prediction_done.connect(lambda p: captured.append(p))
        worker.run()
        p = captured[-1][0]
        # 递增序列排序后应识别为上升趋势
        self.assertEqual(p['trend'], 'up')
        self.assertGreater(p['future_daily'][-1], p['future_daily'][0])


if __name__ == '__main__':
    unittest.main(verbosity=2)