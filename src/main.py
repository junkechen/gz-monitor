# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 主程序入口
"""

import sys
import os
import traceback
import time
from datetime import datetime  # 用于 _write_crash_log 等模块级函数

# ── 全局异常兜底：防止未捕获异常导致程序静默退出 ─────────────────────────────
def _log_dir_for_exe() -> str:
    """获取日志目录（%APPDATA% 优先，EXE 同级目录次之）。"""
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    # 1) 优先写到 %APPDATA%\GZ_Monitor\logs （权限稳定）
    appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
    preferred = os.path.join(appdata, 'GZ_Monitor', 'logs')
    try:
        os.makedirs(preferred, exist_ok=True)
        # 写权限测试
        test = os.path.join(preferred, '.write_test')
        with open(test, 'w', encoding='utf-8') as f:
            f.write('1')
        os.remove(test)
        return preferred
    except Exception:
        pass
    # 2) 回退到 EXE 同级 logs/
    fallback = os.path.join(base, 'logs')
    os.makedirs(fallback, exist_ok=True)
    return fallback


def _write_crash_log(prefix: str, text: str) -> None:
    """把崩溃信息追加写入 crash.log（永不抛异常）。"""
    try:
        log_dir = _log_dir_for_exe()
        path = os.path.join(log_dir, 'crash.log')
        with open(path, 'a', encoding='utf-8') as f:
            f.write(f"\n===== {prefix} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====\n")
            f.write(text)
            f.write("\n")
    except Exception:
        # 写日志失败时 silent fallback：至少把内容打到 stderr
        try:
            print(f"[CRASH-LOG-WRITE-FAILED] {prefix}: {text}", file=sys.stderr)
        except Exception:
            pass


def _global_exception_hook(exc_type, exc_value, exc_tb):
    """全局异常钩子：捕获所有未处理异常，写盘到 crash.log（不再静默崩溃）。"""
    try:
        err_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        sys.stderr.write(f"[FATAL] 未捕获异常:\n{err_msg}\n")
        sys.stderr.flush()
        _write_crash_log('UNCAUGHT', err_msg)
    except Exception as inner_exc:
        try:
            sys.stderr.write(f"[FATAL] exception hook itself failed: {inner_exc}\n")
        except Exception:
            pass


def _unraisable_hook(unraisable):
    """捕获 sys.unraisable（典型场景：C 回调里的 Python 异常被吞）。"""
    try:
        msg = (f"{unraisable.exc_type.__name__}: {unraisable.exc_value}\n"
               f"  origin: {getattr(unraisable, 'object', '?')}\n"
               f"  source: {getattr(unraisable, 'source', '?')}\n"
               f"  tb: {''.join(traceback.format_exception(unraisable.exc_type, unraisable.exc_value, unraisable.exc_traceback)) if unraisable.exc_traceback else '(none)'}")
        _write_crash_log('UNRAISABLE', msg)
    except Exception:
        pass


sys.excepthook = _global_exception_hook
try:
    sys.unraisablehook = _unraisable_hook  # Python 3.8+
except AttributeError:
    pass

# 进程退出前的「干净退出」标记（区分闪退 vs 正常退出）
import atexit
def _atexit_clean_exit():
    try:
        _write_crash_log('CLEAN_EXIT', f'process exiting cleanly; pid={os.getpid()}\n')
    except Exception:
        pass
atexit.register(_atexit_clean_exit)


# ── Windows 原生崩溃兜底：通过 ctypes 接管 SEH，落盘 .dmp ─────────────────────
# 关键能力：当 matplotlib/PyQt5 的 C 层段错误（如 Win7 QImage blit 越界）直接
# 把进程杀掉时，Python 的 sys.excepthook 根本来不及触发；只有 SEH + MiniDump
# 才能拿到堆栈。下面这段代码必须在 QApplication 之前导入，否则就晚了。
try:
    import ctypes
    from ctypes import wintypes

    if sys.platform == 'win32':
        _MINIDUMP_WRITE_DUMP = None
        try:
            _dbghelp = ctypes.windll.dbghelp
            _MINIDUMP_WRITE_DUMP = _dbghelp.MiniDumpWriteDump
            _MINIDUMP_WRITE_DUMP.argtypes = [
                wintypes.HANDLE, wintypes.DWORD, wintypes.HANDLE,
                ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ]
            _MINIDUMP_WRITE_DUMP.restype = ctypes.c_uint32

            _kernel32 = ctypes.windll.kernel32

            EXCEPTION_MAXIMUM_PARAMS = 15  # 定义在 winnt.h

            class _EXCEPTION_RECORD(ctypes.Structure):
                _fields_ = [
                    ('ExceptionCode', wintypes.DWORD),
                    ('ExceptionFlags', wintypes.DWORD),
                    ('ExceptionRecord', ctypes.c_void_p),
                    ('ExceptionAddress', ctypes.c_void_p),
                    ('NumberParameters', wintypes.DWORD),
                    ('ExceptionInformation', ctypes.c_uint32 * EXCEPTION_MAXIMUM_PARAMS),
                ]

            class _MINIDUMP_EXCEPTION_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ('ThreadId', wintypes.DWORD),
                    ('ExceptionPointers', ctypes.c_void_p),
                    ('ClientPointers', wintypes.BOOL),
                ]

            class _MINIDUMP_TYPE:
                MiniDumpWithFullMemory = 0x00000002
                MiniDumpWithDataSegs = 0x00000004
                MiniDumpWithHandleData = 0x00000008
                MiniDumpWithUnloadedModules = 0x00000020
                MiniDumpWithFullMemoryInfo = 0x00000040
                MiniDumpWithThreadInfo = 0x00000100

            LONG = ctypes.c_long
            _EXCEPTION_POINTERS = ctypes.c_void_p

            # 异常码
            EXCEPTION_ACCESS_VIOLATION = 0xC0000005
            EXCEPTION_STACK_OVERFLOW = 0xC00000FD
            EXCEPTION_ILLEGAL_INSTRUCTION = 0xC000001D
            EXCEPTION_INT_DIVIDE_BY_ZERO = 0xC0000094

            # 进程路径
            _proc_handle = _kernel32.GetCurrentProcess()
            _proc_id = _kernel32.GetCurrentProcessId()

            def _seh_handler(exception_code):
                """SEH 入口：写 .dmp + 写 crash.log 后让进程自然退出。"""
                try:
                    log_dir = _log_dir_for_exe()
                    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                    dmp_path = os.path.join(log_dir, f'crash_{_proc_id}_{ts}.dmp')
                    log_path = os.path.join(log_dir, 'crash.log')
                    msg = (
                        f"NATIVE SEH EXCEPTION 0x{exception_code & 0xFFFFFFFF:08X}\n"
                        f"  timestamp: {ts}\n"
                        f"  pid={_proc_id}\n"
                        f"  dump: {dmp_path}\n"
                    )
                    with open(log_path, 'a', encoding='utf-8') as f:
                        f.write(f"\n===== NATIVE_CRASH {ts} =====\n{msg}\n")
                    # 落盘 MiniDump
                    try:
                        out_file = _kernel32.CreateFileW(
                            ctypes.c_wchar_p(dmp_path),
                            0x80000000 | 0x40000000,  # GENERIC_READ | GENERIC_WRITE
                            0,  # no share
                            None,
                            2,  # CREATE_ALWAYS
                            0x80,  # FILE_ATTRIBUTE_NORMAL
                            None,
                        )
                        if out_file:
                            # 用 MiniDumpWithFullMemory + 其它 flag
                            flags = (_MINIDUMP_TYPE.MiniDumpWithFullMemory
                                     | _MINIDUMP_TYPE.MiniDumpWithDataSegs
                                     | _MINIDUMP_TYPE.MiniDumpWithHandleData
                                     | _MINIDUMP_TYPE.MiniDumpWithThreadInfo)
                            exception_info = _MINIDUMP_EXCEPTION_INFORMATION()
                            exception_info.ThreadId = _kernel32.GetCurrentThreadId()
                            exception_info.ExceptionPointers = 0  # 简化
                            exception_info.ClientPointers = False
                            _MINIDUMP_WRITE_DUMP(_proc_handle, _proc_id, out_file,
                                                 flags,
                                                 ctypes.byref(exception_info) if exception_info.ExceptionPointers else None,
                                                 None, None)
                            _kernel32.CloseHandle(out_file)
                    except Exception as dump_exc:
                        with open(log_path, 'a', encoding='utf-8') as f:
                            f.write(f"  dump write failed: {dump_exc}\n")
                    # 必须返回 1 让异常被当作已处理（避免 nested 处理），但进程通常会退出
                    return 1  # EXCEPTION_EXECUTE_HANDLER
                except Exception:
                    return 1

            # 注册 SEH：用 SetUnhandledExceptionFilter（WinXP+/全通用）
            try:
                SetUnhandledExceptionFilter = _kernel32.SetUnhandledExceptionFilter
                SetUnhandledExceptionFilter.argtypes = [ctypes.c_void_p]
                SetUnhandledExceptionFilter.restype = ctypes.c_void_p

                SEH_HANDLER_TYPE = ctypes.WINFUNCTYPE(LONG, _EXCEPTION_POINTERS)

                def _seh_trampoline(exc_ptrs):
                    try:
                        # EXCEPTION_POINTERS = { EXCEPTION_RECORD* pExceptionRecord; ... }
                        # pExceptionRecord 首字段 DWORD ExceptionCode
                        code = 0
                        if exc_ptrs:
                            try:
                                # 读前 4 字节作为 ExceptionCode
                                code = ctypes.c_uint32.from_address(exc_ptrs).value
                            except Exception:
                                code = 0
                    except Exception:
                        code = 0
                    return _seh_handler(code)

                _seh_c = SEH_HANDLER_TYPE(_seh_trampoline)
                _seh_c_addr = ctypes.cast(_seh_c, ctypes.c_void_p).value
                prev = SetUnhandledExceptionFilter(_seh_c_addr)
                _write_crash_log('SEH_INSTALLED',
                                 f'SetUnhandledExceptionFilter registered, '
                                 f'addr=0x{_seh_c_addr:X}, prev=0x{prev or 0:X}\n')

                # 同时注册 AddVectoredExceptionHandler 作为首发拦截（Windows XP+）
                try:
                    AddVectoredExceptionHandler = _kernel32.AddVectoredExceptionHandler
                    AddVectoredExceptionHandler.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
                    AddVectoredExceptionHandler.restype = ctypes.c_void_p
                    vec_handler = AddVectoredExceptionHandler(1, _seh_c_addr)  # CALL_FIRST
                    _write_crash_log('VECTORED_HANDLER_INSTALLED',
                                     f'AddVectoredExceptionHandler ok, handle=0x{vec_handler or 0:X}\n')
                except Exception as vec_exc:
                    _write_crash_log('VECTORED_HANDLER_SKIPPED', f'{vec_exc}\n')
            except Exception as seh_set_exc:
                _write_crash_log('SEH_FAILED', f'SetUnhandledExceptionFilter failed: {seh_set_exc}\n')
        except Exception as load_exc:
            _write_crash_log('DBGHELP_LOAD_FAILED', f'failed to load dbghelp: {load_exc}\n')
except Exception:
    # ctypes 不可用就静默忽略（理论上在 Windows 打包环境必成功）
    pass


# ── Win7 环境诊断日志（启动时记录） ────────────────────────────────────────
def _log_win7_diagnostics() -> None:
    """记录 OS/Python/Qt/matplotlib 版本以及设备像素比，便于 Win7 排查。"""
    try:
        from datetime import datetime as _dt
        info = []
        info.append(f"timestamp: {_dt.now().isoformat()}")
        try:
            info.append(f"sys.platform: {sys.platform}")
        except Exception: pass
        try:
            import platform as _plat
            info.append(f"platform.release: {_plat.release()}; platform.version: {_plat.version()}")
        except Exception: pass
        info.append(f"Python: {sys.version.split()[0]}")
        try:
            import PyQt5
            from PyQt5.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
            info.append(f"Qt: {QT_VERSION_STR}; PyQt5: {PYQT_VERSION_STR}")
        except Exception as exc:
            info.append(f"PyQt5 import failed: {exc}")
        try:
            import matplotlib
            info.append(f"matplotlib: {matplotlib.__version__}")
        except Exception:
            pass
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                # devicePixelRatio 与 devicePixelRatioF
                for screen in app.screens():
                    info.append(f"screen name={screen.name()} dpr={screen.devicePixelRatio()} dprF={screen.devicePixelRatioF()} geom={screen.geometry()}")
                    break
        except Exception:
            pass
        try:
            info.append(f"sys.executable: {sys.executable}")
            info.append(f"sys.frozen: {getattr(sys, 'frozen', False)}")
        except Exception:
            pass
        info.append(f"sys.argv: {sys.argv}")
        _write_crash_log('STARTUP_DIAG', '\n'.join(info))
    except Exception:
        pass

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

    # 启动后立即记录 Win7 环境诊断（必须在 QApplication 创建后调用）
    _log_win7_diagnostics()

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

                        # 首次启动教学引导：延迟触发，等主窗口布局稳定后展示遮罩
                        try:
                            from user_data_manager import is_first_run
                            if is_first_run():
                                QTimer.singleShot(800, _main_window.start_onboarding)
                        except Exception:
                            pass
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
