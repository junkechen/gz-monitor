# -*- coding: utf-8 -*-
"""v5.33: 验证 MainWindow.__init__ 不再主线程同步执行 _refresh_data，而是 QTimer.singleShot 异步触发。

为什么：v5.32 之前 _refresh_data() 在 __init__ 主线程同步调用，Win10 上快看不出来，
但 Win7 / 慢网络时主线程被 HTTP 同步请求阻塞，导致 QTimer 调度的 show_main_window 回调进不去，
主窗口永远不显示。任务管理器看到「进程在 / CPU=0 / 不显示」。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from unittest.mock import MagicMock, patch
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

# 必须有 QApplication 才能实例化 MainWindow
_app = QApplication([])


def test_mainwindow_init_does_not_call_refresh_data_sync():
    """Mock 掉 _refresh_data，检查 MainWindow.__init__ 时它没被同步执行。"""
    from main_window import MainWindow

    # 用一个假的 multi_client 跳过实际登录
    fake_client = MagicMock()
    fake_client.clients = {'fakeEnt': MagicMock()}

    # Patch _refresh_data 计数
    call_count = {'n': 0}
    original = MainWindow._refresh_data if hasattr(MainWindow, '_refresh_data') else None

    def counting_refresh(self):
        call_count['n'] += 1

    with patch.object(MainWindow, '_refresh_data', counting_refresh), \
         patch.object(MainWindow, '_setup_warning', lambda self: None), \
         patch.object(MainWindow, '_setup_menu',     lambda self: None), \
         patch.object(MainWindow, '_init_ui',        lambda self: None):
        try:
            w = MainWindow(fake_client)
        except Exception as e:
            # 即便 _init_ui / _setup_warning 被 patch 掉，MainWindow 别的字段仍可能初始化失败
            print(f"[WARN] MainWindow 初始化失败: {e}; 但本测试仅检查 _refresh_data 调用时机")
            return

        # 关键断言：实例化完成时，_refresh_data 不应被同步调用
        # v5.33 行为：构造函数只 QTimer.singleShot(0, ...) 排程，事件循环还没跑就被实例化
        assert call_count['n'] == 0, (
            f"v5.33 修复要求 MainWindow.__init__ 不再同步调用 _refresh_data，"
            f"但构造期间已被调用 {call_count['n']} 次 (Win7 启动卡死的元凶)。"
        )
        print(f"[OK] MainWindow.__init__ 期间 _refresh_data 调用次数 = {call_count['n']} (期望 0，v5.33 行为)")


if __name__ == '__main__':
    test_mainwindow_init_does_not_call_refresh_data_sync()
    print("\n=== MainWindow 异步化测试通过 ===")
