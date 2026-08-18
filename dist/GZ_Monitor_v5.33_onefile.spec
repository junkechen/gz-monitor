# -*- mode: python ; coding: utf-8 -*-
# v5.33 GZ_Monitor onefile spec - 移除有问题的 AddVectoredExceptionHandler(CALL_FIRST) 回归
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
    name='GZ_Monitor_v5.33_Win7',
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
