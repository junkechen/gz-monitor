# -*- coding: utf-8 -*-
"""
教学引导（onboarding）单元测试：无头运行。

覆盖：
1. 首登 gating 纯逻辑（is_first_run / mark_first_run_completed + onboarding_version）
2. build_default_steps 返回 8 步且锚定真实控件
3. TourGuide 步进 / 完成 / 信号 / 清理
4. MainWindow.start_onboarding 的 gating 与 force 路径

注意：离线（offscreen）环境下，半透明遮罩顶层窗口的 mapToGlobal/show() 会触发 Qt 段错误
（真实显示器无此问题）。因此测试中对几何相关方法打安全补丁，仅验证逻辑，
真实聚光灯/脉冲视觉效果由用户在 Windows 本机双击 EXE 验收。
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

_FAILS = []


def _check(cond, msg):
    if cond:
        print(f"[OK] {msg}")
    else:
        print(f"[FAIL] {msg}")
        _FAILS.append(msg)


class _FakeClient:
    clients = {}

    def get_all_realtime_data(self, *a, **k):
        return {}

    def get_client_by_subid(self, *a, **k):
        return None


def _patch_tour_for_offscreen():
    """offscreen 下用安全替身替换几何相关方法，避免 Qt 段错误。"""
    from onboarding import TourGuide
    from PyQt5.QtCore import QRect, QPoint

    def _safe_start(self):
        self.setGeometry(0, 0, 800, 600)
        self._goto(0)

    def _safe_recompute(self):
        # 不调用任何 mapTo（offscreen 下会崩溃），用固定矩形占位
        self._hole = QRect(20, 20, 200, 120)
        self._place_card()

    TourGuide.start = _safe_start
    TourGuide._recompute_hole = _safe_recompute


def test_gating_pure():
    """首登 gating 纯逻辑（用临时文件，避免污染真实 app_info）。"""
    import user_data_manager as udm
    tmp = tempfile.mkdtemp()
    fake = os.path.join(tmp, "app_info.json")
    orig = udm.get_app_info_file_path
    udm.get_app_info_file_path = lambda: Path(fake)
    try:
        _check(udm.is_first_run() is True, "is_first_run() 文件缺失时默认 True")
        udm.mark_first_run_completed(1)
        _check(udm.is_first_run() is False, "mark_first_run_completed 后 is_first_run()=False")
        info = udm.load_app_info()
        _check(info.get("onboarding_version") == 1, "onboarding_version 已写入")
        udm.mark_first_run_completed(2)
        _check(udm.load_app_info().get("onboarding_version") == 2, "可更新 onboarding_version")
    finally:
        udm.get_app_info_file_path = orig


def test_build_steps():
    from PyQt5.QtWidgets import QApplication
    from main_window import MainWindow
    from onboarding import build_default_steps
    app = QApplication.instance() or QApplication(sys.argv[:1])
    w = MainWindow(_FakeClient())
    steps = build_default_steps(w)
    _check(len(steps) == 8, f"默认 8 步引导（实际 {len(steps)}）")
    for i, s in enumerate(steps):
        ok = ("target" in s) and (hasattr(s["target"], "mapTo")) and s.get("title") and s.get("text")
        _check(ok, f"步骤 {i + 1} 含 target/title/text")
    # 验证 pre 动作引用的控件存在（切页签用到 right_panel / prediction_tab / realtime_tab）
    for name in ("right_panel", "prediction_tab", "realtime_tab",
                 "pred_btn", "pred_table", "param_picker",
                 "pred_normalize_btn", "pred_mode_combo", "sub_list", "realtime_table"):
        _check(hasattr(w, name), f"步骤锚点控件 {name} 存在")


def test_tour_navigation():
    from PyQt5.QtWidgets import QApplication
    from main_window import MainWindow
    from onboarding import TourGuide, build_default_steps
    app = QApplication.instance() or QApplication(sys.argv[:1])
    w = MainWindow(_FakeClient())
    steps = build_default_steps(w)
    finished = {"fired": False}

    def on_finish():
        finished["fired"] = True

    t = TourGuide(w, steps)
    t.finished.connect(on_finish)
    t.start()
    _check(t._idx == 0, "start 后定位第 0 步")
    t._next()
    _check(t._idx == 1, "_next 前进到第 1 步")
    t._prev()
    _check(t._idx == 0, "_prev 回到第 0 步")
    for _ in range(len(steps) + 2):
        t._next()
    _check(finished["fired"], "走完所有步骤触发 finished 信号")
    t.deleteLater()


def test_start_onboarding_gating():
    from PyQt5.QtWidgets import QApplication
    from main_window import MainWindow, ONBOARDING_VERSION
    import user_data_manager as udm
    app = QApplication.instance() or QApplication(sys.argv[:1])
    w = MainWindow(_FakeClient())

    orig_is = udm.is_first_run
    orig_load = udm.load_app_info
    try:
        # 场景1：已首登 + 看过当前版本 → 不触发
        udm.is_first_run = lambda: False
        udm.load_app_info = lambda: {"first_run": False, "onboarding_version": ONBOARDING_VERSION}
        w.start_onboarding(force=False)
        _check(getattr(w, "_tour", None) is None, "非首登+同版本+force=False 时不启动引导")

        # 场景2：已首登 但 引导版本过期 → 仍触发（升级后需重看）
        udm.load_app_info = lambda: {"first_run": False, "onboarding_version": ONBOARDING_VERSION - 1}
        w.start_onboarding(force=False)
        _check(getattr(w, "_tour", None) is not None, "首登版本过期时仍触发引导")
        if getattr(w, "_tour", None) is not None:
            w._tour._finish()

        # 场景3：force=True → 强制触发（重看教学菜单）
        w.start_onboarding(force=True)
        _check(getattr(w, "_tour", None) is not None, "force=True 时创建引导实例")
        w._tour._finish()
        _check(getattr(w, "_tour", None) is None, "_finish 后引导实例已清理")
    finally:
        udm.is_first_run = orig_is
        udm.load_app_info = orig_load


def main():
    _patch_tour_for_offscreen()
    test_gating_pure()
    test_build_steps()
    test_tour_navigation()
    test_start_onboarding_gating()
    if _FAILS:
        print(f"\n=== onboarding 测试未通过：{len(_FAILS)} 处 ===")
        for m in _FAILS:
            print(f"  - {m}")
        return 1
    print("\n=== onboarding 测试全部通过 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
