# -*- coding: utf-8 -*-
"""v5.72 修复"数据缺失"误报 单元测试

问题：总排口同时配置 废水流量/累计流量/流量 多个流量 code，实际只报送其中
一部分。旧逻辑对窗口内全空的 code 也判"数据缺失（同周期其他参数有值）"，
导致每小时误报（用户截图：废水流量全天无值但累计流量/流量正常，却被记了
60+ 条异常）。

修复：
1. 扫描窗口内从未报送过值的 code 视为"该排口未启用此参数"，不判缺失；
   平时有值、突然缺数仍报异常。
2. AbnormalStore 加载时一次性清除旧逻辑产生的"数据缺失"误报记录。
"""
import os
import sys
import json
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from abnormal_scanner import (
    AbnormalStore, _classify_rows, _PURGE_FLAG,
    TYPE_ABNORMAL, TYPE_EXCEED,
)


class TestNeverReportedCodeNotMissing(unittest.TestCase):
    """窗口内全空的 code 不再误报数据缺失"""

    def test_never_reported_code_not_missing(self):
        # 模拟总排口：废水流量(011)全天不报送，累计流量(492)/流量(210)正常
        rows = [
            {'DateTime': f'2026-11-07 {h:02d}:00',
             'val_492': None, 'state_492': '0', 'status_492': '',
             'val_492': str(1300 + h), 'state_492': '0', 'status_492': '',
             'val_210': '23.0', 'state_210': '0', 'status_210': '',
             'val_383': '8.5', 'state_383': '0', 'status_383': ''}
            for h in range(24)
        ]
        recs = _classify_rows(rows, ['492', '495', '210', '383'],
                              '山东冠洲股份有限公司', '13692', '总排口',
                              '2026-11-07 12:00:00')
        missing = [r for r in recs if r['type'] == TYPE_ABNORMAL]
        self.assertEqual(missing, [],
                         f'未报送参数被误报缺失: {[r["param"] for r in missing]}')

    def test_suddenly_missing_still_reported(self):
        # 平时报送、突然缺数 → 仍要报（真实缺数检测不能丢）
        rows = [
            {'DateTime': '2026-11-07 08:00',
             'val_492': '1358', 'state_492': '0', 'status_492': '',
             'val_383': '8.5', 'state_383': '0', 'status_383': ''},
            {'DateTime': '2026-11-07 09:00',
             'val_492': '-9999', 'state_492': '0', 'status_492': '',
             'val_383': '8.6', 'state_383': '0', 'status_383': ''},
        ]
        recs = _classify_rows(rows, ['492', '383'], '测试企业', '100',
                              '总排口', '2026-11-07 10:00:00')
        missing = [r for r in recs if r['type'] == TYPE_ABNORMAL]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]['time'], '2026-11-07 09:00')
        self.assertEqual(missing[0]['param'], '废水流量')


class TestPurgeFalsePositives(unittest.TestCase):
    """一次性清除 v5.72 之前的"数据缺失"误报记录"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, 'abnormal_records.json')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @staticmethod
    def _missing_rec(time='2026-11-07 08:00'):
        return {'time': time, 'ent': '山东冠洲股份有限公司', 'subname': '总排口',
                'subid': '13692', 'param': '废水流量', 'code': '492',
                'type': TYPE_ABNORMAL, 'value': '', 'unit': 'm³', 'std': '',
                'desc': '数据缺失（同周期其他参数有值）', 'state_raw': '',
                'status_raw': '', 'detected_at': '2026-11-07 08:05:00',
                'source': '24h扫描'}

    @staticmethod
    def _exceed_rec():
        return {'time': '2026-11-07 09:00', 'ent': '山东冠洲股份有限公司',
                'subname': '总排口', 'subid': '13692', 'param': '非甲烷总烃',
                'code': '383', 'type': TYPE_EXCEED, 'value': '55',
                'unit': 'mg/m³', 'std': '50', 'desc': '非甲烷总烃故障',
                'state_raw': '1', 'status_raw': '',
                'detected_at': '2026-11-07 09:05:00', 'source': '24h扫描'}

    def test_old_list_format_purged_once(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump([self._missing_rec(), self._exceed_rec()], f,
                      ensure_ascii=False)
        store = AbnormalStore(self.path)
        self.assertEqual(len(store.records), 1, '误报应被清除')
        self.assertEqual(store.records[0]['type'], TYPE_EXCEED)

        # 落盘后带 flag，再次加载不再过滤（真实缺数记录能存活）
        store.add_records([self._missing_rec(time='2026-11-07 11:00')])
        self.assertEqual(len(store.records), 2)
        store2 = AbnormalStore(self.path)
        self.assertEqual(len(store2.records), 2, '清理只做一次，不能误伤新记录')

    def test_dict_format_with_flag_keeps_records(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump({'records': [self._missing_rec()],
                       _PURGE_FLAG: True}, f, ensure_ascii=False)
        store = AbnormalStore(self.path)
        self.assertEqual(len(store.records), 1, '已清理过的文件不应再动')

    def test_new_format_roundtrip(self):
        store = AbnormalStore(self.path)
        store.add_records([self._exceed_rec()])
        store2 = AbnormalStore(self.path)
        self.assertEqual(len(store2.records), 1)
        with open(self.path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)
        self.assertTrue(data.get(_PURGE_FLAG))


if __name__ == '__main__':
    unittest.main(verbosity=2)
