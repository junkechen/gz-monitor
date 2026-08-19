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

            # ── 增强诊断：把异常地址解析为「模块+偏移」并抓取调用栈 ───────────────
            # 思路（v5.34 新增）：原生崩溃只拿到异常码没用，必须知道是哪个 DLL 的哪
            # 一行出错。GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS)
            # 可由任意地址反查其所属模块 HMODULE，再 GetModuleFileNameW 取路径 →
            # basename 即模块名，偏移 = 地址 - 模块基址。CaptureStackBackTrace 抓
            # 当前线程调用栈，逐帧同样解析为「模块+偏移」。这样用户下次崩溃时 crash.log
            # 直接告诉我们是 Qt5Gui / Qt5Core / _image / ft2font / matplotlib /
            # python38 等哪个模块出错，无需再传 .dmp。
            _GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS = 0x4
            try:
                _kernel32.GetModuleHandleExW.argtypes = [
                    ctypes.c_ulong, ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_void_p)]
                _kernel32.GetModuleHandleExW.restype = ctypes.c_bool
            except Exception:
                pass
            try:
                _kernel32.GetModuleFileNameW.argtypes = [
                    ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong]
                _kernel32.GetModuleFileNameW.restype = ctypes.c_ulong
            except Exception:
                pass
            try:
                _kernel32.CaptureStackBackTrace.argtypes = [
                    ctypes.c_ulong, ctypes.c_ulong,
                    ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_ulong)]
                _kernel32.CaptureStackBackTrace.restype = ctypes.c_ushort
            except Exception:
                pass
            try:
                _kernel32.CreateFileW.argtypes = [
                    ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
                    ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
                _kernel32.CreateFileW.restype = ctypes.c_void_p
            except Exception:
                pass

            # 常见原生异常码 → 可读名（便于 crash.log 直接看出异常类型）
            _EXCEPTION_CODE_NAMES = {
                0xC0000005: 'EXCEPTION_ACCESS_VIOLATION',
                0xC0000006: 'EXCEPTION_IN_PAGE_ERROR',
                0xC000001D: 'EXCEPTION_ILLEGAL_INSTRUCTION',
                0xC0000025: 'EXCEPTION_NONCONTINUABLE_EXCEPTION',
                0xC0000026: 'EXCEPTION_INVALID_DISPOSITION',
                0xC000008C: 'EXCEPTION_ARRAY_BOUNDS_EXCEEDED',
                0xC000008D: 'EXCEPTION_FLT_DENORMAL_OPERAND',
                0xC000008E: 'EXCEPTION_FLT_DIVIDE_BY_ZERO',
                0xC000008F: 'EXCEPTION_FLT_INEXACT_RESULT',
                0xC0000090: 'EXCEPTION_FLT_INVALID_OPERATION',
                0xC0000091: 'EXCEPTION_FLT_OVERFLOW',
                0xC0000092: 'EXCEPTION_FLT_STACK_CHECK',
                0xC0000093: 'EXCEPTION_FLT_UNDERFLOW',
                0xC0000094: 'EXCEPTION_INT_DIVIDE_BY_ZERO',
                0xC00000FD: 'EXCEPTION_STACK_OVERFLOW',
                0xC0000374: 'STATUS_HEAP_CORRUPTION',
                0xC0000409: 'STATUS_STACK_BUFFER_OVERRUN',
                0x80000003: 'EXCEPTION_BREAKPOINT',
                0x80000004: 'EXCEPTION_SINGLE_STEP',
            }

            def _exception_code_name(code):
                return _EXCEPTION_CODE_NAMES.get(int(code) & 0xFFFFFFFF)

            def _resolve_module(addr):
                """由地址反查所属模块，返回 (模块基名, 模块基址, 偏移)。无法解析返回 (None, addr, 0)。"""
                if not addr:
                    return (None, addr, 0)
                try:
                    hmod = ctypes.c_void_p()
                    if _kernel32.GetModuleHandleExW(
                            _GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,
                            ctypes.c_void_p(int(addr)),
                            ctypes.byref(hmod)) and hmod.value:
                        buf = ctypes.create_unicode_buffer(1024)
                        _kernel32.GetModuleFileNameW(hmod, buf, 1024)
                        base = int(hmod.value)
                        offset = int(addr) - base
                        name = buf.value or ''
                        short = os.path.basename(name) if name else '0x%X' % base
                        return (short, base, offset)
                except Exception:
                    pass
                return (None, addr, 0)

            def _capture_stack_trace(max_frames=48):
                """用 CaptureStackBackTrace 抓取当前线程调用栈（返回地址列表）。"""
                frames = []
                try:
                    ary = (ctypes.c_void_p * max_frames)()
                    n = _kernel32.CaptureStackBackTrace(0, max_frames, ary, None)
                    n = int(n)
                    frames = [int(ary[i]) for i in range(n)]
                except Exception:
                    pass
                return frames

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

            def _seh_handler(exception_code, exception_address=0, exc_ptrs=None):
                """SEH 入口：写增强版 crash.log（含出错模块+偏移与调用栈）+ 落盘 .dmp。

                Args:
                    exception_code: 异常码（如 0xC0000005）。
                    exception_address: 出错指令地址（EXCEPTION_RECORD.ExceptionAddress）。
                    exc_ptrs: EXCEPTION_POINTERS 原始指针，用于把真实异常上下文写进 .dmp。
                """
                try:
                    log_dir = _log_dir_for_exe()
                    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                    dmp_path = os.path.join(log_dir, f'crash_{_proc_id}_{ts}.dmp')
                    log_path = os.path.join(log_dir, 'crash.log')
                    code_name = _exception_code_name(exception_code)
                    lines = []
                    lines.append(
                        f"NATIVE SEH EXCEPTION 0x{int(exception_code) & 0xFFFFFFFF:08X}"
                        f"{(' (' + code_name + ')') if code_name else ''}")
                    lines.append(f"  timestamp: {ts}")
                    lines.append(f"  pid={_proc_id}")

                    # ── 出错模块 + 偏移（由 ExceptionAddress 反查） ──
                    if exception_address:
                        mod, base, off = _resolve_module(int(exception_address))
                        if mod:
                            lines.append(f"  faulting_address = 0x{int(exception_address):X}")
                            lines.append(
                                f"  faulting_module   = {mod}  (base=0x{base:X}, offset=0x{off:X})")
                        else:
                            lines.append(
                                f"  faulting_address = 0x{int(exception_address):X}  (module not resolved)")
                    else:
                        lines.append("  faulting_address = unknown")

                    # ── 调用栈（每帧解析为 模块+偏移） ──
                    try:
                        frames = _capture_stack_trace()
                        if frames:
                            lines.append(f"  call_stack ({len(frames)} frames):")
                            for i, f in enumerate(frames):
                                m, b, o = _resolve_module(int(f))
                                if m:
                                    lines.append(f"    #{i:02d}  {m}+0x{o:X}   (0x{int(f):X})")
                                else:
                                    lines.append(f"    #{i:02d}  0x{int(f):X}   (module not resolved)")
                        else:
                            lines.append("  call_stack: (empty)")
                    except Exception as st_exc:
                        lines.append(f"  call_stack_error: {st_exc!r}")

                    lines.append(f"  dump: {dmp_path}")
                    msg = "\n".join(lines) + "\n"
                    with open(log_path, 'a', encoding='utf-8') as f:
                        f.write(f"\n===== NATIVE_CRASH {ts} =====\n{msg}\n")

                    # ── 落盘 MiniDump（携带真实异常上下文，便于事后符号化） ──
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
                        if out_file and out_file != -1:  # -1 == INVALID_HANDLE_VALUE
                            # 用 MiniDumpWithFullMemory + 其它 flag
                            flags = (_MINIDUMP_TYPE.MiniDumpWithFullMemory
                                     | _MINIDUMP_TYPE.MiniDumpWithDataSegs
                                     | _MINIDUMP_TYPE.MiniDumpWithHandleData
                                     | _MINIDUMP_TYPE.MiniDumpWithThreadInfo
                                     | _MINIDUMP_TYPE.MiniDumpWithUnloadedModules)
                            exception_info = _MINIDUMP_EXCEPTION_INFORMATION()
                            exception_info.ThreadId = _kernel32.GetCurrentThreadId()
                            if exc_ptrs:
                                # 把真实异常指针写进 dump，符号化时能直接定位 faulting IP
                                exception_info.ExceptionPointers = ctypes.c_void_p(int(exc_ptrs))
                                exception_info.ClientPointers = False
                                ex_arg = ctypes.byref(exception_info)
                            else:
                                exception_info.ExceptionPointers = 0
                                exception_info.ClientPointers = False
                                ex_arg = None
                            _MINIDUMP_WRITE_DUMP(_proc_handle, _proc_id, out_file,
                                                 flags, ex_arg, None, None)
                            _kernel32.CloseHandle(out_file)
                    except Exception as dump_exc:
                        try:
                            with open(log_path, 'a', encoding='utf-8') as f:
                                f.write(f"  dump write failed: {dump_exc!r}\n")
                        except Exception:
                            pass
                    # 必须返回 1 让异常被当作已处理，但进程通常会退出
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
                    """SEH 分派入口：从 EXCEPTION_POINTERS 解析异常码与出错地址。"""
                    code = 0
                    addr = 0
                    if exc_ptrs:
                        try:
                            # EXCEPTION_POINTERS = { PEXCEPTION_RECORD; PCONTEXT; }
                            record_ptr = ctypes.c_void_p.from_address(int(exc_ptrs)).value
                            if record_ptr:
                                # EXCEPTION_RECORD 布局（winnt.h）：
                                #   +0  DWORD  ExceptionCode
                                #   +4  DWORD  ExceptionFlags
                                #   +8  PVOID  ExceptionRecord
                                #   +12 PVOID  ExceptionAddress  ← 出错指令地址
                                code = ctypes.c_uint32.from_address(record_ptr).value
                                addr = ctypes.c_void_p.from_address(record_ptr + 12).value
                        except Exception:
                            code = 0
                            addr = 0
                    return _seh_handler(code, addr, exc_ptrs)

                _seh_c = SEH_HANDLER_TYPE(_seh_trampoline)
                _seh_c_addr = ctypes.cast(_seh_c, ctypes.c_void_p).value
                prev = SetUnhandledExceptionFilter(_seh_c_addr)
                _write_crash_log('SEH_INSTALLED',
                                 f'SetUnhandledExceptionFilter registered, '
                                 f'addr=0x{_seh_c_addr:X}, prev=0x{prev or 0:X}\n')

                # 注意：这里【刻意不】使用 AddVectoredExceptionHandler(CALL_FIRST)。
                # 该 API 会在「每一次 first-chance 异常」(含 Python/Qt 内部可自行恢复的
                # 良性异常) 时被首个调用，若处理函数对其一律返回 EXCEPTION_EXECUTE_HANDLER(1)
                # 会打断正常的异常恢复流程，导致进程在启动/首绘时无故退出 (v5.31 的回归)。
                # SetUnhandledExceptionFilter 是 last-chance 兜底，只在真正无人处理的
                # 原生崩溃时触发，既能拿到 MiniDump 又不会干扰正常异常流，已足够。
            except Exception as seh_set_exc:
                _write_crash_log('SEH_FAILED', f'SetUnhandledExceptionFilter failed: {seh_set_exc}\n')
        except Exception as load_exc:
            _write_crash_log('DBGHELP_LOAD_FAILED', f'failed to load dbghelp: {load_exc}\n')
except Exception:
    # ctypes 不可用就静默忽略（理论上在 Windows 打包环境必成功）
    pass


# ── Qt 消息钩子：捕获 qFatal/qCritical/qWarning（静默崩溃的决定性取证手段） ──
# 关键：v5.34 发现 Win7 上「开始预测」后进程静默消失、却无任何 NATIVE_CRASH/UNCAUGHT
# 记录 —— 说明崩溃绕过了 SetUnhandledExceptionFilter。头号嫌疑是 Qt 的 qFatal：
# Qt 的 qFatal 默认行为是 abort()（或 _exit 1），根本不走 SEH；常见诱因如
# 「Cannot create children for a parent that is in a different thread」「QWidget:
# Must construct a QApplication before a QWidget」「QPainter::begin: Paint device
# returned engine == 0」。下面把 Qt 所有消息（尤其 FATAL/CRITICAL）写进 crash.log，
# 这样下次静默崩溃时日志里会留下 qFatal 的罪证文字，一锤定音。
def _qt_message_handler(msg_type, context, msg: str) -> None:
    try:
        _names = {
            QtMsgType.QtDebugMsg: 'DEBUG',
            QtMsgType.QtInfoMsg: 'INFO',
            QtMsgType.QtWarningMsg: 'WARNING',
            QtMsgType.QtCriticalMsg: 'CRITICAL',
            QtMsgType.QtFatalMsg: 'FATAL',
            QtMsgType.QtSystemMsg: 'SYSTEM',
        }
        level = _names.get(msg_type, 'UNKNOWN')
        ctx = ''
        try:
            if context and context.file:
                ctx = f'  [Qt file={context.file} line={context.line} func={context.function}]'
        except Exception:
            pass
        _write_crash_log('QT_MSG', f'[{level}] {msg}{ctx}\n')
        if msg_type == QtMsgType.QtFatalMsg:
            # qFatal 在返回后会由 Qt 默认行为 abort()，我们已在上面同步落盘；
            # 这里再补一段 Python 栈（若此刻仍在 Python 调用帧里），便于定位触发点。
            try:
                import traceback as _tb
                _write_crash_log('QT_FATAL', 'qFatal triggered; process will now abort.\n'
                                 + ''.join(_tb.format_stack()))
            except Exception:
                pass
    except Exception:
        pass
    # 注意：不要拦截 Qt 的后续默认行为（qFatal 仍会 abort 退出），这样进程确实退出。


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
from PyQt5.QtCore import QTimer, Qt, QtMsgType, qInstallMessageHandler, QThread, pyqtSignal

from main_window import LoginDialog, MainWindow
from multi_account_api import GZMultiAccountClient
from config import BUILTIN_ACCOUNTS


# 全局窗口引用（防止GC）
_main_window = None
_login_dialog = None
_login_worker = None  # v5.38: 后台登录线程引用（防止 QThread 运行时被析构而 qFatal）


class LoginWorker(QThread):
    """后台登录线程（v5.38 性能优化）。

    原实现把 multi_client.login_all()（5 个账户逐个登录 + time.sleep(0.5) 的
    串行网络请求）直接跑在主线程，登录期间 UI 完全卡死。现在移入后台线程，
    进度与结果通过 pyqtSignal 桥接回主线程更新登录对话框，绝不跨线程直接
    调用 Qt 控件。
    """
    progress = pyqtSignal(str)          # 登录进度消息
    login_finished = pyqtSignal(dict)   # 登录结果 dict

    def __init__(self, multi_client, parent=None):
        super().__init__(parent)
        self._multi_client = multi_client

    def run(self):
        """后台执行 login_all，进度/结果通过信号回主线程"""
        try:
            result = self._multi_client.login_all(progress_callback=self.progress.emit)
            self.login_finished.emit(result)
        except Exception as e:
            print(f">>> 登录线程异常: {e}")
            import traceback
            traceback.print_exc()
            self.login_finished.emit({
                "success": False,
                "message": f"登录失败: {str(e)}",
                "success_count": 0,
                "fail_count": 0,
                "total": 0,
            })


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

    # 安装 Qt 消息钩子：把 qFatal/qCritical 等写进 crash.log（静默崩溃取证）
    try:
        qInstallMessageHandler(_qt_message_handler)
        _write_crash_log('QT_MSG_HANDLER_INSTALLED', 'qInstallMessageHandler set\n')
    except Exception:
        pass

    # 判断版本
    version = _get_version()

    # 显示登录对话框
    _login_dialog = LoginDialog(version=version)

    # 显示登录对话框后执行多账户登录（v5.38: 登录移入后台线程，UI 不再卡死）
    def do_multi_account_login():
        global _main_window, _login_dialog, _login_worker

        try:
            print(">>> 开始登录流程...")

            # 防止重复点击：上一次登录线程仍在运行则忽略
            if _login_worker is not None:
                try:
                    if _login_worker.isRunning():
                        print(">>> 登录线程已在运行，忽略重复点击")
                        return
                except RuntimeError:
                    _login_worker = None

            # 创建多账户客户端并添加所有内置账户
            multi_client = GZMultiAccountClient()
            for account in BUILTIN_ACCOUNTS:
                multi_client.add_account(account['name'], account['password'])
            print(f">>> 已添加 {len(BUILTIN_ACCOUNTS)} 个账户")

            # 登录所有账户（v5.38: 后台线程执行，不阻塞主线程）
            _login_dialog.login_btn.setEnabled(False)
            print(">>> 开始登录所有账户（后台线程）...")

            def _on_login_progress(msg):
                # 主线程更新登录进度（信号已桥接回主线程）
                _login_dialog.set_login_progress(msg)

            def _on_login_finished(result):
                print(f">>> 登录结果: {result}")
                # 注意：这里不能把 _login_worker 置 None（线程可能尚未结束，
                # 提前丢引用会让 QThread 运行时被析构而 qFatal），统一交给
                # _on_login_worker_finished 在 finished 信号里清理。
                if result.get('success'):
                    _login_dialog.set_login_result(True, result.get('message', ''))
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
                    _login_dialog.set_login_result(False, result.get('message', ''))
                    _login_dialog.login_btn.setEnabled(True)
                    print(">>> 登录失败")

            def _on_login_worker_finished():
                # 线程已结束：安全释放全局引用 + deleteLater（析构安全）
                global _login_worker
                w = _login_worker
                _login_worker = None
                if w is not None:
                    try:
                        w.deleteLater()
                    except Exception:
                        pass

            _login_worker = LoginWorker(multi_client)
            _login_worker.progress.connect(_on_login_progress)
            _login_worker.login_finished.connect(_on_login_finished)
            _login_worker.finished.connect(_on_login_worker_finished)
            _login_worker.start()
            print(">>> 登录线程已启动")

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
