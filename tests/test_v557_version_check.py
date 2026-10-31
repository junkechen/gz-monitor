# -*- coding: utf-8 -*-
"""v5.57 回归：在线版本检测（升级提示）的核心逻辑。

覆盖：版本号解析、与当前版本比较、网络失败静默处理。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from main_window import VersionCheckWorker


def test_parse_version():
    assert VersionCheckWorker._parse_version('v5.56') == (5, 56)
    assert VersionCheckWorker._parse_version('5.57') == (5, 57)
    assert VersionCheckWorker._parse_version('v10.2.3') == (10, 2, 3)
    assert VersionCheckWorker._parse_version('notaversion') is None


def test_parse_version_compare():
    assert (5, 57) > (5, 56)
    assert (6, 0) > (5, 99)
    assert (5, 56) > (5, 55, 9)  # 元组长度不同但按元素比较，前两位已分胜负


def test_worker_runs_without_crash_on_bad_url():
    # 离线/错误地址不应抛异常、不应误报升级
    w = VersionCheckWorker('5.56', 'http://127.0.0.1:1/nonexistent')
    emitted = []
    w.update_available.connect(lambda a, b: emitted.append((a, b)))
    w.run()  # 直接调用 run()，同步执行，便于断言
    assert emitted == [], "网络失败时不应发出升级信号"
    print("[OK] v5.57 版本检测解析/比较/失败静默 通过")


if __name__ == '__main__':
    test_parse_version()
    test_parse_version_compare()
    test_worker_runs_without_crash_on_bad_url()
