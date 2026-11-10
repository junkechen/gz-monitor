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
            # v5.60+：日排放量预测必须有流量参数才能换算 kg，补 210（流量 m³）
            '210': [10000.0 + i * 100 for i in range(14)],
        }
        self.calls = []

    def query_history(self, subid, subtype, codes, start, end, index=1,
                      page=1, rows=1000, use_corrected=False, **kw):
        # v5.47：记录 page/rows，用于断言「use_corrected 未被误传为 page」
        self.calls.append({
            'subid': subid, 'subtype': subtype, 'codes': codes,
            'start': start, 'end': end, 'index': index,
            'page': page, 'rows': rows, 'use_corrected': use_corrected,
        })
        # v5.76：服务端每行含该时刻所有参数（此前按 code 拆行，
        # 与 worker「按行取 val_{code} + 流量」的结构不符，测试长期失效）
        code_list = [c.strip() for c in codes.split(',') if c.strip()]
        n_days = max((len(self.daily_values_per_code.get(c) or [])
                      for c in code_list), default=0)
        base = datetime(2026, 1, 1)
        out = []
        for i in range(n_days):
            row = {'DateTime': (base + timedelta(days=i)).strftime('%Y-%m-%d')}
            for code in code_list:
                vals = self.daily_values_per_code.get(code) or []
                if i < len(vals):
                    row[f'val_{code}'] = str(vals[i])
            out.append(row)
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
        sub_itemcodes_cache={'K1_01': '201,203,210'},
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
        client = _FakeClient({'201': [100.0, 101.0],
                              '210': [10000.0, 10100.0]})   # 仅 2 天
        worker, _ = _make_worker("日排放量预测", daily_forecast_days=7,
                                 client=client)
        captured = []
        worker.prediction_done.connect(lambda p: captured.append(p))
        worker.run()
        self.assertEqual(captured[-1], [], "历史不足却产出了预测")

    def test_j_unsorted_server_response(self):
        """服务端乱序返回时，worker 应自行排序后计算"""
        client = _FakeClient({'201': [float(i) for i in range(1, 15)],
                              '210': [10000.0 + i * 100 for i in range(14)]})
        worker, _ = _make_worker("日排放量预测", daily_forecast_days=7,
                                 client=client)
        captured = []
        worker.prediction_done.connect(lambda p: captured.append(p))
        worker.run()
        p = captured[-1][0]
        # 递增序列排序后应识别为上升趋势
        self.assertEqual(p['trend'], 'up')
        self.assertGreater(p['future_daily'][-1], p['future_daily'][0])


class TestQueryHistoryArgSafety(unittest.TestCase):
    """v5.47 回归：use_corrected 曾被误传为 page（位置参数错位）。"""

    def test_a_page_not_polluted(self):
        """多账号 client 签名下 page 必须为 1，不能被 use_corrected 污染"""
        class _MultiClient:
            def query_history(self, subid, subtype, codes, start, end,
                              index=1, page=1, rows=1000, use_corrected=False):
                return {'_echo': dict(index=index, page=page, rows=rows,
                                      use_corrected=use_corrected)}

        r = mw.PredictionWorker._query_history_safe(
            _MultiClient(), 'S', '01', '201', 'a', 'b',
            index=2, use_corrected=False, page=1, rows=1000)
        self.assertEqual(r['_echo']['page'], 1,
                         "use_corrected=False 被当成 page=0，分页异常")
        self.assertIs(r['_echo']['use_corrected'], False)

    def test_b_use_corrected_true_preserved(self):
        """热电厂 use_corrected=True 时，page 仍应为 1 且标志位正确传递"""
        class _MultiClient:
            def query_history(self, subid, subtype, codes, start, end,
                              index=1, page=1, rows=1000, use_corrected=False):
                return {'_echo': dict(index=index, page=page, rows=rows,
                                      use_corrected=use_corrected)}

        r = mw.PredictionWorker._query_history_safe(
            _MultiClient(), 'S', '01', '201', 'a', 'b',
            index=2, use_corrected=True, page=1, rows=1000)
        self.assertIs(r['_echo']['use_corrected'], True)
        self.assertEqual(r['_echo']['page'], 1)
        self.assertEqual(r['_echo']['index'], 2)

    def test_c_compatible_with_short_signature(self):
        """单账号 client（无 page/rows）不应因多余关键字报错"""
        class _SmallClient:
            def query_history(self, subid, subtype, codes, start, end,
                              index=1, use_corrected=False):
                return {'_echo': dict(index=index, use_corrected=use_corrected)}

        r = mw.PredictionWorker._query_history_safe(
            _SmallClient(), 'S', '01', '201', 'a', 'b',
            index=2, use_corrected=True, page=1, rows=1000)
        self.assertIs(r['_echo']['use_corrected'], True)
        self.assertEqual(r['_echo']['index'], 2)

    def test_d_hour_fallback_when_daily_missing(self):
        """日数据缺失时必须回退到小时数据聚合，而不是直接返回空"""
        class _HourOnlyClient:
            def __init__(self):
                self.calls = []

            def query_history(self, subid, subtype, codes, start, end,
                              index=1, page=1, rows=1000, use_corrected=False):
                self.calls.append(index)
                if index == 2:
                    return {'rows': [], 'total': 0}      # 无日数据
                # 返回 30 天 × 每天 2 条的小时数据
                out = []
                for d in range(1, 31):
                    for h in (8, 20):
                        out.append({
                            'DateTime': f'2026-01-{d:02d} {h:02d}:00',
                            'val_201': str(100.0 + d),
                            # v5.76：排放量需逐时流量才能累加，补 210
                            'val_210': '500.0',
                        })
                return {'rows': out, 'total': len(out)}

        client = _HourOnlyClient()
        worker, _ = _make_worker("日排放量预测", daily_forecast_days=7,
                                 client=client)
        captured = []
        worker.prediction_done.connect(lambda p: captured.append(p))
        worker.run()
        self.assertTrue(captured[-1], "日数据缺失时未回退，结果仍为空")
        self.assertIn('data_source', captured[-1][0])
        self.assertEqual(captured[-1][0]['data_source'], '小时数据聚合')

    def test_e_skip_reasons_recorded(self):
        """数据不足时应记录原因，供 UI 提示"""
        client = _FakeClient({'201': [100.0, 101.0],
                              '210': [10000.0, 10100.0]})   # 仅 2 天
        worker, _ = _make_worker("日排放量预测", daily_forecast_days=7,
                                 client=client)
        worker.run()
        self.assertTrue(worker.daily_skip_reasons,
                        "未记录跳过原因，UI 将无法解释空结果")
        self.assertIn('不足 3 天', worker.daily_skip_reasons[0])

    def test_f_hour_aggregation_helper(self):
        """小时聚合应按日期求均值"""
        rows = [
            {'DateTime': '2026-01-01 08:00', 'val_201': '10'},
            {'DateTime': '2026-01-01 20:00', 'val_201': '20'},
            {'DateTime': '2026-01-02 08:00', 'val_201': '30'},
        ]
        out = mw.PredictionWorker._aggregate_hour_rows_to_daily(rows)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]['DateTime'], '2026-01-01')
        self.assertAlmostEqual(out[0]['val_201'], 15.0)
        self.assertAlmostEqual(out[1]['val_201'], 30.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)