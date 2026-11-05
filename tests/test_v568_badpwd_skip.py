# -*- coding: utf-8 -*-
"""v5.68 单元测试：密码错误黑名单短路登录，避免反复尝试。

覆盖：
  - mark/clear/is_bad_password 的「账号 + 密码哈希」逻辑（密码改了自动放行）
  - login() 对已知密码错误账号直接返回 need_password_check，不发网络请求
  - login_all() 对密码错误账号跳过会话恢复与完整登录，其他账号正常登录
"""
import os
import sys
import json
import tempfile
import unittest
from unittest import mock

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src')
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import multi_account_api as m


class TestBadPasswordBlacklist(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, 'gz_bad_pwd.json')
        self.patcher = mock.patch.object(m, '_bad_pwd_path', return_value=self.path)
        self.patcher.start()
        self.sleep_patcher = mock.patch('multi_account_api.time.sleep')
        self.sleep_patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.sleep_patcher.stop()

    def test_mark_and_is(self):
        # 记录密码错误
        m.mark_bad_password('a', 'pw1')
        self.assertTrue(m.is_bad_password('a', 'pw1'))
        # 密码改了 → 黑名单自动失效并放行
        self.assertFalse(m.is_bad_password('a', 'pw2'))
        # 再次查询应为 False（已清除）
        self.assertFalse(m.is_bad_password('a', 'pw1'))
        # 未记录的账号
        self.assertFalse(m.is_bad_password('b', 'x'))

    def test_login_skips_when_bad(self):
        m.mark_bad_password('x', 'p')
        c = m.GZApiClient()
        # 命中黑名单 → 直接返回，不触碰网络
        res = c.login('x', 'p')
        self.assertFalse(res['success'])
        self.assertTrue(res['need_password_check'])
        self.assertTrue(res['skipped'])

    def test_login_all_skips_bad_account(self):
        mc = m.GZMultiAccountClient()
        mc.add_account('bad', 'wrong')
        mc.add_account('good', 'right')
        m.mark_bad_password('bad', 'wrong')

        with mock.patch.object(m, 'GZApiClient') as CA:
            inst = CA.return_value
            inst.try_resume_session.return_value = False
            inst.login.return_value = {'success': True, 'message': 'ok'}

            res = mc.login_all(progress_callback=None)

        # good 正常：1 次会话恢复 + 1 次登录；bad 被短路：0 次
        self.assertEqual(inst.try_resume_session.call_count, 1)
        self.assertEqual(inst.login.call_count, 1)
        self.assertTrue(res['details']['bad'].get('need_password_check'))
        self.assertTrue(res['details']['good']['success'])
        self.assertEqual(res['success_count'], 1)
        self.assertEqual(res['fail_count'], 1)
        self.assertTrue(res['success'])  # 部分成功

    def test_login_all_all_bad(self):
        mc = m.GZMultiAccountClient()
        mc.add_account('a', 'pa')
        mc.add_account('b', 'pb')
        m.mark_bad_password('a', 'pa')
        m.mark_bad_password('b', 'pb')

        with mock.patch.object(m, 'GZApiClient') as CA:
            inst = CA.return_value
            res = mc.login_all(progress_callback=None)

        self.assertEqual(inst.try_resume_session.call_count, 0)
        self.assertEqual(inst.login.call_count, 0)
        self.assertEqual(res['success_count'], 0)
        self.assertEqual(res['fail_count'], 2)
        self.assertFalse(res['success'])


if __name__ == '__main__':
    unittest.main()
