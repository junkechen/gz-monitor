# -*- mode: python ; coding: utf-8 -*-
# v5.36 GZ_Monitor onefile spec - 修复按需预测 QThread 运行时析构导致 Win7 点"开始预测"闪退
#   根因: _request_on_demand_prediction 用单一槽位 self._pred_ondemand_worker 保存 worker,
#         被缺失参数循环并发调用时后一个赋值丢弃前一个仍在运行 worker 的引用 -> 引用计数归零
#         -> C++ QThread 析构 -> qFatal("QThread: Destroyed while thread is still running") -> abort
#   修复: 1) 单槽位改为按参数名保留在途 worker 的 dict self._pred_ondemand_workers,
#            finished 后再移除引用并 deleteLater
#         2) closeEvent 先调用 _stop_pred_workers() 对所有在途 worker quit()+wait(3000) 再 accept
#   保留 v5.35 诊断埋点: SEH 增强 + qInstallMessageHandler 抓 qFatal + PRED_STEP 路径埋点(CALL_FIRST)
import os, sys
block_cipher = None

# Analyze from src/ so .spec can be invoked from project root
spec_root = os.path.abspath(os.path.dirname(SPEC))   # dist/
proj_root = os.path.abspath(os.path.join(spec_root, '..'))
src_dir = os.path.join(proj_root, 'src')

# Ensure src/ is on PYTHONPATH at runtime so 'from main import ...' works
extra_paths = [src_dir]

a = Analysis(
    [os.path.join(src_dir, 'main.py')],
    pathex=extra_paths,
    binaries=[],
    datas=[],
    hiddenimports=[
        # 项目自身依赖
        'config', 'multi_account_api', 'data_processor', 'history_fetch_worker',
        'refresh_utils', 'account_manager', 'user_data_manager',
        'pred_param_selector', 'onboarding',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc', 'doctest'],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='GZ_Monitor_v5.36_Win7',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
