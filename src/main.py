# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 主程序入口
"""

import sys
import os
import traceback

# ── 全局异常兜底：防止未捕获异常导致程序静默退出 ─────────────────────────────
def _global_exception_hook(exc_type, exc_value, exc_tb):
    """全局异常钩子：捕获所有未处理异常，记录日志而非静默崩溃"""
    try:
        err_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print(f"[FATAL] 未捕获异常:\n{err_msg}", file=sys.stderr)
        # 尝试写入日志文件
        if getattr(sys, 'frozen', False):
            log_dir = os.path.join(os.path.dirname(sys.executable), "logs")
        else:
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "crash.log")
    except Exception:
        pass  # 日志写入失败也不要再抛异常

sys.excepthook = _global_exception_hook

# 添加src目录到路径（打包后和开发时均适用）
if getattr(sys, 'frozen', False):
    # 打包后的情况
    base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
    src_path = os.path.join(base_path, 'src')
else:
    # 开发时的情况
    src_path = os.path.dirname(os.path.abspath(__file__))

if src_path not in sys.path:
    sys.path.insert(0, src_path)

# 确保当前目录也在路径中（用于相对导入）
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont, QColor, QPalette
from PyQt5.QtCore import QTimer, Qt

from main_window import LoginDialog, MainWindow
from multi_account_api import GZMultiAccountClient
from config import BUILTIN_ACCOUNTS


# 全局窗口引用（防止GC）
_main_window = None
_login_dialog = None


def main():
    global _main_window, _login_dialog

    # 必须在创建QApplication之前设置WebEngine的属性
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setFont(QFont("Microsoft YaHei", 9))
    app.setPalette(_dark_palette())

    # 判断版本
    version = _get_version()

    # 显示登录对话框
    _login_dialog = LoginDialog(version=version)

    # 直接在对话框显示后执行多账户登录
    def do_multi_account_login():
        global _main_window, _login_dialog

        try:
            print(">>> 开始登录流程...")

            # 创建多账户客户端并添加所有内置账户
            multi_client = GZMultiAccountClient()
            for account in BUILTIN_ACCOUNTS:
                multi_client.add_account(account['name'], account['password'])
            print(f">>> 已添加 {len(BUILTIN_ACCOUNTS)} 个账户")

            # 登录所有账户
            _login_dialog.login_btn.setEnabled(False)
            print(">>> 开始登录所有账户...")
            result = multi_client.login_all(progress_callback=_login_dialog.set_login_progress)
            print(f">>> 登录结果: {result}")

            if result['success']:
                _login_dialog.set_login_result(True, result['message'])
                print(">>> 登录成功，准备显示主窗口...")

                # 延迟1秒后显示主窗口
                def show_main_window():
                    global _main_window
                    try:
                        print(">>> 隐藏登录对话框...")
                        _login_dialog.hide()
                        print(">>> 创建主窗口...")
                        _main_window = MainWindow(multi_client)
                        print(">>> 显示主窗口...")
                        _main_window.show()
                        print(">>> 主窗口已显示")
                    except Exception as e:
                        print(f">>> 创建主窗口失败: {e}")
                        import traceback
                        traceback.print_exc()
                        _login_dialog.show()
                        _login_dialog.set_login_result(False, f"创建窗口失败: {str(e)}")
                        _login_dialog.login_btn.setEnabled(True)

                QTimer.singleShot(1000, show_main_window)
            else:
                _login_dialog.set_login_result(False, result['message'])
                _login_dialog.login_btn.setEnabled(True)
                print(">>> 登录失败")

        except Exception as e:
            print(f">>> 登录过程发生错误: {e}")
            import traceback
            traceback.print_exc()
            _login_dialog.set_login_result(False, f"登录失败: {str(e)}")
            _login_dialog.login_btn.setEnabled(True)

    # 连接登录按钮到多账户登录
    # 先断开之前的连接（如果有的话），避免重复连接
    try:
        _login_dialog.login_btn.clicked.disconnect()
    except Exception:
        pass  # 没有连接可以忽略
    
    _login_dialog.login_btn.clicked.connect(do_multi_account_login)
    _login_dialog.show()
    print(">>> 登录对话框已显示")

    sys.exit(app.exec())


def _get_version() -> int:
    """根据程序名判断版本 (v1/v2/v3)"""
    name = os.path.basename(
        sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
    ).lower()
    if 'v2' in name or 'version2' in name:
        return 2
    if 'v3' in name or 'version3' in name:
        return 3
    return 1   # 默认版本一


def _dark_palette() -> QPalette:
    """暗色主题调色板"""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(13, 17, 23))
    p.setColor(QPalette.ColorRole.WindowText,       QColor(230, 237, 243))
    p.setColor(QPalette.ColorRole.Base,             QColor(22, 27, 34))
    p.setColor(QPalette.ColorRole.AlternateBase,    QColor(33, 38, 45))
    p.setColor(QPalette.ColorRole.ToolTipBase,      QColor(230, 237, 243))
    p.setColor(QPalette.ColorRole.ToolTipText,      QColor(230, 237, 243))
    p.setColor(QPalette.ColorRole.Text,             QColor(230, 237, 243))
    p.setColor(QPalette.ColorRole.Button,           QColor(33, 38, 45))
    p.setColor(QPalette.ColorRole.ButtonText,       QColor(230, 237, 243))
    p.setColor(QPalette.ColorRole.BrightText,       QColor(248, 81,  73))
    p.setColor(QPalette.ColorRole.Link,             QColor(88, 166, 255))
    p.setColor(QPalette.ColorRole.Highlight,        QColor(88, 166, 255))
    p.setColor(QPalette.ColorRole.HighlightedText,  QColor(13, 17, 23))
    return p


if __name__ == '__main__':
    main()
