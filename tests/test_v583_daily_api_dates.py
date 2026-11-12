# -*- coding: utf-8 -*-
"""v5.83：日数据接口(index=2)日期格式修复的单元测试。

根因：服务端日接口只接受裸日期 yyyy-MM-dd；带 ' 00:00'/' 23:59'
时间后缀返回空（v5.78 曾据此误判「日接口恒空」改走小时聚合，
导致基准日均被小时口径平滑低估 ~35%）。

用桩 session 捕获 POST body，验证 index=2 剥后缀、index=1 保留。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from api_client import GZApiClient, bare_date  # noqa: E402


class _Resp:
    def json(self):
        return {"total": 0, "rows": []}


class _StubSession:
    """捕获 POST 请求体的假 session"""

    def __init__(self):
        self.captured = []
        self.headers = {}

    def post(self, url, headers=None, data=None, timeout=None):
        self.captured.append(data)
        return _Resp()

    def get(self, *a, **kw):
        return _Resp()


class TestBareDate(unittest.TestCase):
    def test_bare_date_strips_time(self):
        self.assertEqual(bare_date('2026-11-02 00:00'), '2026-11-02')
        self.assertEqual(bare_date('2026-11-08 23:59'), '2026-11-08')

    def test_bare_date_keeps_plain(self):
        self.assertEqual(bare_date('2026-11-02'), '2026-11-02')

    def test_bare_date_non_string(self):
        self.assertEqual(bare_date(20261102), '20261102')


class TestQueryHistoryDateFix(unittest.TestCase):
    def _client(self):
        c = GZApiClient()
        c.session = _StubSession()
        return c

    def test_daily_query_strips_time_suffix(self):
        c = self._client()
        c.query_history('8190', '64', '383', '2026-11-02 00:00',
                        '2026-11-08 23:59', index=2)
        body = c.session.captured[-1]
        self.assertIn('index=2', body)
        self.assertIn('start=2026-11-02', body)
        self.assertIn('end=2026-11-08', body)
        self.assertNotIn('00%3A00', body)
        self.assertNotIn('23%3A59', body)

    def test_hourly_query_keeps_time_suffix(self):
        c = self._client()
        c.query_history('8190', '64', '383', '2026-11-02 00:00',
                        '2026-11-08 23:59', index=1)
        body = c.session.captured[-1]
        self.assertIn('index=1', body)
        self.assertIn('00%3A00', body)
        self.assertIn('23%3A59', body)

    def test_multi_account_daily_query_strips_time_suffix(self):
        from multi_account_api import GZApiClient as MAGZApiClient
        c = MAGZApiClient()
        c.session = _StubSession()
        c.query_history('8190', '64', '383', '2026-11-02 00:00',
                        '2026-11-08 23:59', index=2, page=1, rows=1000)
        body = c.session.captured[-1]
        self.assertIn('index=2', body)
        self.assertIn('start=2026-11-02', body)
        self.assertNotIn('00%3A00', body)


if __name__ == '__main__':
    unittest.main()
