# -*- coding: utf-8 -*-
"""
v5.41 登录优化回归测试（haslock 处理 + 会话恢复 + 滑块缓存）
全部 mock，不触发真实网络。运行：C:/Python38/python.exe tests/test_login_haslock.py
"""
import os
import sys
import time
import unittest
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import multi_account_api
from multi_account_api import GZApiClient, GZMultiAccountClient


def _reset_caches(tmpdir):
    """把会话缓存文件指到临时目录，避免污染真实数据"""
    path = os.path.join(tmpdir, 'gz_sessions.json')
    multi_account_api._session_cache_path = lambda: path
    return path


class TestLoginHaslock(unittest.TestCase):
    """haslock 识别与 login_all 延迟重试"""

    def _patch_login(self, script):
        """
        script: {username: [第一次返回, 第二次返回, ...]}
        返回 (原login, 调用记录 dict)
        """
        calls = {u: 0 for u in script}
        orig = multi_account_api.GZApiClient.login

        def fake_login(self, username, password, progress_callback=None, **kwargs):
            seq = script[username]
            i = min(calls[username], len(seq) - 1)
            calls[username] += 1
            return seq[i]

        multi_account_api.GZApiClient.login = fake_login
        return orig, calls

    def test_a_haslock_retry_success(self):
        """场景B：haslock 账号 90 秒等待后重试成功 → patch 等待避免真等"""
        tmp = tempfile.mkdtemp()
        _reset_caches(tmp)
        A_OK = {"success": True, "message": "登录成功"}
        B_LOCK = {"success": False, "message": "haslock", "lock_type": "haslock",
                  "lock_seconds": 2}
        B_OK = {"success": True, "message": "登录成功"}
        orig, calls = self._patch_login({
            "A": [A_OK],
            "B": [B_LOCK, B_OK],
        })
        # 把 90 秒等待 patch 成 0.05 秒粒度（测试提速）
        orig_sleep = time.sleep
        orig_wait_const = 90

        class FakeMC(GZMultiAccountClient):
            pass

        # 直接修改 login_all 内的等待：通过 monkeypatch time.sleep 实现
        # （login_all 内 while waited < wait: time.sleep(1)）
        sleep_calls = []

        def fast_sleep(sec):
            sleep_calls.append(sec)
            orig_sleep(0.001)  # 1秒 → 1毫秒

        time.sleep = fast_sleep
        try:
            mc = GZMultiAccountClient()
            mc.add_account("A", "p1")
            mc.add_account("B", "p2")
            res = mc.login_all()
        finally:
            time.sleep = orig_sleep
            multi_account_api.GZApiClient.login = orig

        self.assertTrue(res["success"])
        self.assertEqual(res["success_count"], 2)
        self.assertEqual(res["fail_count"], 0)
        self.assertIn("details", res)
        self.assertTrue(res["details"]["B"]["success"])
        self.assertEqual(calls["B"], 2)  # 首次 + 重试
        # haslock 等待：循环 sleep(1) 共 90 次（v5.41 策略，1秒粒度可响应进度）
        ones = sum(1 for s in sleep_calls if s == 1)
        self.assertGreaterEqual(ones, 90,
                                f"应等待90秒(90次sleep(1)), 实际: {ones}次")

    def test_b_haslock_retry_still_locked(self):
        """场景C：haslock 重试仍锁 → 不再继续尝试，最终部分成功"""
        tmp = tempfile.mkdtemp()
        _reset_caches(tmp)
        A_OK = {"success": True, "message": "登录成功"}
        B_LOCK = {"success": False, "message": "haslock", "lock_type": "haslock",
                  "lock_seconds": 2}
        orig, calls = self._patch_login({
            "A": [A_OK],
            "B": [B_LOCK],  # 永远返回锁定
        })
        orig_sleep = time.sleep
        time.sleep = lambda s: orig_sleep(0.001)
        try:
            mc = GZMultiAccountClient()
            mc.add_account("A", "p1")
            mc.add_account("B", "p2")
            res = mc.login_all()
        finally:
            time.sleep = orig_sleep
            multi_account_api.GZApiClient.login = orig

        self.assertTrue(res["success"])  # 部分成功
        self.assertEqual(res["success_count"], 1)
        self.assertEqual(res["fail_count"], 1)
        self.assertEqual(calls["B"], 2)  # 只重试一次，不反复消耗额度
        self.assertFalse(res["details"]["B"]["success"])
        self.assertIn("网页端", res["details"]["B"]["message"])

    def test_c_resume_session_valid(self):
        """会话恢复：缓存有效且 get_enterprise_subs 返回非空 → 跳过登录"""
        tmp = tempfile.mkdtemp()
        path = _reset_caches(tmp)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({"某企业": {"session_id": "abc123",
                                 "saved_at": time.time()}}, f)

        c = GZApiClient()
        # mock get_enterprise_subs 返回非空 → 会话有效
        orig_subs = GZApiClient.get_enterprise_subs
        GZApiClient.get_enterprise_subs = lambda self: [{"SubId": 1}]
        try:
            ok = c.try_resume_session("某企业")
        finally:
            GZApiClient.get_enterprise_subs = orig_subs
        self.assertTrue(ok)
        self.assertTrue(c.logged_in)

    def test_d_resume_session_invalid(self):
        """会话恢复：get_enterprise_subs 返回空 → 走正常登录，logged_in 复位"""
        tmp = tempfile.mkdtemp()
        path = _reset_caches(tmp)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({"某企业": {"session_id": "old",
                                 "saved_at": time.time()}}, f)

        c = GZApiClient()
        orig_subs = GZApiClient.get_enterprise_subs
        GZApiClient.get_enterprise_subs = lambda self: []
        try:
            ok = c.try_resume_session("某企业")
        finally:
            GZApiClient.get_enterprise_subs = orig_subs
        self.assertFalse(ok)
        self.assertFalse(c.logged_in)

    def test_e_resume_session_expired(self):
        """会话恢复：缓存超过6小时 → 直接判定失效，不发请求"""
        tmp = tempfile.mkdtemp()
        path = _reset_caches(tmp)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({"某企业": {"session_id": "abc",
                                 "saved_at": time.time() - 7 * 3600}}, f)

        c = GZApiClient()
        called = []

        def no_call(self):
            called.append(1)
            return [{"SubId": 1}]

        orig_subs = GZApiClient.get_enterprise_subs
        GZApiClient.get_enterprise_subs = no_call
        try:
            ok = c.try_resume_session("某企业")
        finally:
            GZApiClient.get_enterprise_subs = orig_subs
        self.assertFalse(ok)
        self.assertEqual(len(called), 0)  # 过期缓存不应发任何请求

    def test_f_slider_subsystem_v544(self):
        """v5.44 滑块子系统：自动求解器可用 + 人工兜底方法存在 + login 接受 trail_provider"""
        import inspect
        import slider_solver
        # 自动 NCC 求解器为主路径，solve_trail 必须可调用
        self.assertTrue(callable(slider_solver.solve_trail))
        # 人工拖动兜底方法存在（后台线程调用 GUI 主线程注入的 trail_provider）
        self.assertTrue(hasattr(GZApiClient, '_manual_slider_trail'))
        # login 签名兼容 trail_provider 桥接参数
        params = inspect.signature(GZApiClient.login).parameters
        self.assertIn('trail_provider', params)


if __name__ == '__main__':
    unittest.main(verbosity=2)
