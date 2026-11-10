# -*- coding: utf-8 -*-
"""v5.69 异常数据扫描/记录 单元测试"""
import os
import sys
import json
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from data_processor import classify_data_state
from abnormal_scanner import (
    AbnormalStore, scan_all, _classify_rows, _warning_records,
    TYPE_EXCEED, TYPE_FAULT, TYPE_STOP, TYPE_ABNORMAL, TYPE_WARNING,
)


class TestClassifyDataState(unittest.TestCase):
    """数据状态分类器"""

    def test_normal(self):
        for s, t in [('0', ''), ('', ''), ('N', ''), ('0', '正常'), (None, None)]:
            self.assertEqual(classify_data_state(s, t), '正常', f"{s}/{t}")

    def test_exceed(self):
        self.assertEqual(classify_data_state('1', ''), '超标')
        self.assertEqual(classify_data_state('9', ''), '超标')

    def test_fault(self):
        self.assertEqual(classify_data_state('2', ''), '故障')
        self.assertEqual(classify_data_state('F', ''), '故障')
        self.assertEqual(classify_data_state('', 'F'), '故障')
        self.assertEqual(classify_data_state('故障', ''), '故障')
        self.assertEqual(classify_data_state('', '故障'), '故障')

    def test_stop(self):
        self.assertEqual(classify_data_state('3', ''), '停产')
        self.assertEqual(classify_data_state('S', ''), '停产')
        self.assertEqual(classify_data_state('停产', ''), '停产')

    def test_unknown_returns_none(self):
        # 未知字母标记（非故障/停产/正常集合）→ None 视为异常
        self.assertIsNone(classify_data_state('Z', ''))
        self.assertIsNone(classify_data_state('', 'Z'))


class TestAbnormalStore(unittest.TestCase):
    """异常记录存储：去重/查询/持久化"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, 'abnormal_records.json')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _rec(self, **kw):
        base = dict(time='2026-11-07 08:00', ent='测试企业', subname='排口1',
                    subid='100', param='非甲烷总烃', code='383',
                    type=TYPE_EXCEED, value='55', unit='mg/m³', std='50',
                    desc='', state_raw='1', status_raw='',
                    detected_at='2026-11-07 08:05:00', source='24h扫描')
        base.update(kw)
        return base

    def test_add_and_dedupe(self):
        store = AbnormalStore(self.path)
        added = store.add_records([self._rec(), self._rec()])
        self.assertEqual(added, 1)          # 相同 key 去重
        added2 = store.add_records([self._rec(time='2026-11-07 09:00')])
        self.assertEqual(added2, 1)         # 时间不同算新记录
        self.assertEqual(len(store.records), 2)

    def test_query_filters(self):
        store = AbnormalStore(self.path)
        store.add_records([
            self._rec(),
            self._rec(type=TYPE_FAULT, time='2026-11-07 07:00'),
            self._rec(ent='其他企业', time='2026-11-06 07:00'),
        ])
        self.assertEqual(len(store.query()), 3)
        self.assertEqual(len(store.query(ent='测试企业')), 2)
        self.assertEqual(len(store.query(rtype=TYPE_FAULT)), 1)
        self.assertEqual(len(store.query(start='2026-11-07 00:00')), 2)
        self.assertEqual(len(store.query(end='2026-11-06 23:59')), 1)

    def test_persistence(self):
        store = AbnormalStore(self.path)
        store.add_records([self._rec()])
        store2 = AbnormalStore(self.path)
        self.assertEqual(len(store2.records), 1)
        # 重新加载后去重仍然生效
        self.assertEqual(store2.add_records([self._rec()]), 0)


class TestClassifyRows(unittest.TestCase):
    """扫描行分类：超标/故障/停产/数据缺失"""

    def _rows(self):
        return [
            {'DateTime': '2026-11-07 08:00',
             'val_383': '55', 'stand_383': '50', 'state_383': '1', 'status_383': '',
             'val_525': '85', 'state_525': '2', 'status_525': '',
             'val_526': None, 'state_526': '0', 'status_526': '',
             'val_210': '100', 'state_210': '3', 'status_210': ''},
            {'DateTime': '2026-11-07 09:00',
             'val_383': '30', 'stand_383': '50', 'state_383': '0', 'status_383': '',
             'val_525': '-9999', 'state_525': '0', 'status_525': ''},
        ]

    def test_classify(self):
        recs = _classify_rows(self._rows(), ['383', '525', '526', '210'],
                              '测试企业', '100', '排口1', '2026-11-07 10:00:00')
        types = {(r['param'], r['time'], r['type']) for r in recs}
        self.assertIn(('非甲烷总烃', '2026-11-07 08:00', TYPE_EXCEED), types)
        self.assertIn(('烟气温度', '2026-11-07 08:00', TYPE_FAULT), types)
        self.assertIn(('烟气流量', '2026-11-07 08:00', TYPE_STOP), types)
        # 09:00 行 525 无效但 383 有值 → 数据缺失异常
        self.assertIn(('烟气温度', '2026-11-07 09:00', TYPE_ABNORMAL), types)
        # 正常数据不产生记录
        self.assertNotIn(('非甲烷总烃', '2026-11-07 09:00', TYPE_ABNORMAL), types)


class TestScanAll(unittest.TestCase):
    """scan_all 整链路（假客户端）"""

    def test_scan_all_with_fake_client(self):
        class FakeClient:
            enterprise_name = '测试企业'

            def get_enterprise_list(self, subtype):
                return [{'id': 9, 'name': '测试企业'}]

            def get_sub_list(self, entid, subtype):
                return [{'id': '100', 'name': '排口1',
                         'itemCode': '383,525'}]

            def query_history(self, subid, subtype, codes, start, end,
                              index=1, page=1, rows=1000, use_corrected=False):
                return {'total': 1, 'rows': [
                    {'DateTime': '2026-11-07 08:00',
                     'val_383': '55', 'stand_383': '50',
                     'state_383': '1', 'status_383': '',
                     'val_525': '85', 'state_525': '2', 'status_525': ''},
                ]}

        class FakeMulti:
            clients = {'测试企业': FakeClient()}

        from datetime import datetime as _dt, timedelta as _td
        warnings = [{'datetime': (_dt.now() - _td(minutes=30)).strftime('%Y-%m-%d %H:%M:%S'), 'ent_name': '测试企业',
                     'subname': '排口1', 'param': '非甲烷总烃', 'value': 60,
                     'level': '红色预警', 'type': '实时预警'}]
        recs = scan_all(FakeMulti(), warnings, hours=24)
        types = [r['type'] for r in recs]
        self.assertIn(TYPE_EXCEED, types)
        self.assertIn(TYPE_FAULT, types)
        self.assertIn(TYPE_WARNING, types)
        # 预警记录字段完整
        w = [r for r in recs if r['type'] == TYPE_WARNING][0]
        self.assertEqual(w['ent'], '测试企业')
        self.assertIn('红色预警', w['desc'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
