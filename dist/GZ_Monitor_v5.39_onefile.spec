# -*- mode: python ; coding: utf-8 -*-
# v5.39 GZ_Monitor onefile spec - 修复预测结果栏排放口不全
#   修复 PredictionWorker.run 兜底分支未定义变量 group_data 致 NameError，
#   该异常未捕获导致 run 提前终止、prediction_done 信号永不发射、结果表仅含部分排放口。
#   （line 159-178 兜底分支改为从当前排放口 sub_data['params'] 直接提取 codes）
#   新增 tests/test_pred_coverage.py 回归测试：覆盖「缓存无 codes」排放口走兜底分支不崩。
#   保留 v5.35/5.36/5.37/5.38 修复与诊断埋点: SEH 增强 + qInstallMessageHandler +
#       PRED_STEP 路径埋点 + 按需预测 worker dict 生命周期（closeEvent 安全退出）+
#       完成仅合并不整图重绘 + 登录/实时刷新异步化 + 预测表批量填充 + 绘图降载 + 并发限制。
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
    name='GZ_Monitor_v5.39_Win7',
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
