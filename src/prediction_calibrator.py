# -*- coding: utf-8 -*-
"""
GZ 安环监测系统 —— 预测算法自学习校准器（v5.58）

目标
----
让用户提出的「自动根据实际数据对预测算法进行优化」真正落地：
预测不是一次性静态公式，而是随着真实监测数据的积累**持续自我校准**。

机制（三步走）
--------------
1. **回溯采集（record_sample）**
   每次预测时，利用「当前已下载的历史序列」做一次留一法回溯检验
   （hold-out backtest）：用序列前段预测后若干点，再与序列里已知的真实
   值对比，把 ``(预测值, 实际值, 置信度)`` 作为一个反馈样本记下。
   因为历史序列本身就是真实监测数据，这等价于「用实际数据检验预测」。

2. **自动校准（recalibrate）**
   样本按 ``(预测类型, 步长)`` 分组后，计算：
     - bias_factor = 中位偏差比 (actual / predicted)，修正系统性偏高/偏低；
     - conf_scale  = 让「平均报告置信度」贴合「平均实际命中率」，修正过度自信/保守。
   阈值与幅值均做了钳制，防止极端样本把校准带偏（稳定性优先）。

3. **反馈应用（get_correction）**
   预测函数在输出前读取校准参数，对预测值做偏差修正、对置信度做缩放。
   **无任何样本时参数恒为 (1.0, 1.0)，与原算法完全等价 —— 零回归风险。**

线程与异常
----------
- 模块级 RLock 保护内存样本与落盘，预测后台线程与主线程均可安全调用。
- 任何文件 IO / 解析异常一律静默吞掉，绝不让校准逻辑影响正常预测。
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Dict, Optional, Tuple

# ── 可调常量 ───────────────────────────────────────────────────────────────
MAX_SAMPLES = 3000          # 内存中保留的最大反馈样本数（超出丢弃最旧）
MIN_SAMPLES_TO_CALIBRATE = 8  # 单个 (类型,步长) 至少多少个样本才出校准值
BIAS_CLAMP = (0.5, 1.6)     # bias_factor 允许区间，防止除零/极端序列带偏
CONF_CLAMP = (0.5, 1.25)    # conf_scale 允许区间
FLUSH_INTERVAL_SEC = 20.0   # 两次落盘的最小间隔（节流，避免频繁写盘）
FLUSH_BATCH = 40            # 累计多少个新样本后强制落盘一次
STATE_VERSION = 1

# ── 日志（尽量不依赖外部 logger 配置，失败则静默）─────────────────────────
try:  # pragma: no cover - 仅便于排查
    import logging
    _logger = logging.getLogger("pred_calib")
except Exception:  # noqa
    _logger = None


def _log(msg: str) -> None:
    if _logger is not None:
        try:
            _logger.debug(msg)
        except Exception:  # noqa
            pass


# ── 状态文件路径（优先可写：源码 data/ 或 exe 同级 data/）─────────────────
def _state_path() -> str:
    """返回校准状态文件绝对路径，并确保 data 目录存在。"""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        # src/prediction_calibrator.py -> 项目根 = 上级目录
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base, "data")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except Exception:  # noqa - 目录建不成也不应影响预测
        pass
    return os.path.join(data_dir, "pred_calibration.json")


# ── 模块级单例状态 ─────────────────────────────────────────────────────────
_lock = threading.RLock()
_samples: list = []                 # 反馈样本列表
_params: Dict[str, dict] = {}       # key -> {bias, conf_scale, n}
_loaded = False
_dirty_count = 0
_last_flush_ts = 0.0


def _key(horizon_type: str, horizon_offset: int) -> str:
    return f"{horizon_type}#{int(horizon_offset)}"


def _load() -> None:
    """惰性加载状态文件（仅首次）。"""
    global _samples, _params, _loaded
    with _lock:
        if _loaded:
            return
        _loaded = True
        try:
            path = _state_path()
            if not os.path.exists(path):
                return
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data.get("samples"), list):
                _samples = data["samples"][-MAX_SAMPLES:]
            if isinstance(data.get("params"), dict):
                _params = data["params"]
            _log(f"[CALIB] 已加载 {len(_samples)} 样本, {len(_params)} 组校准")
        except Exception:  # noqa - 损坏或缺失都按空处理
            _samples, _params = [], {}


def _flush() -> None:
    """把内存状态写盘（内部调用，调用方需持锁）。返回是否成功。"""
    global _last_flush_ts, _dirty_count
    try:
        path = _state_path()
        data = {
            "version": STATE_VERSION,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "samples": _samples,
            "params": _params,
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(tmp, path)  # 原子替换，避免半截文件
        _last_flush_ts = time.time()
        _dirty_count = 0
        _log(f"[CALIB] 已落盘 {len(_samples)} 样本")
        return True
    except Exception:  # noqa
        return False


def _maybe_flush() -> None:
    """根据节流规则决定是否落盘 + 重新校准。"""
    global _dirty_count
    now = time.time()
    if _dirty_count >= FLUSH_BATCH or (now - _last_flush_ts) >= FLUSH_INTERVAL_SEC:
        _recalibrate_locked()
        _flush()


def _recalibrate_locked() -> None:
    """根据现有样本重算所有 (类型,步长) 的校准参数。调用方需持锁。"""
    groups: Dict[str, list] = {}
    for s in _samples:
        k = s.get("k")
        if not k:
            continue
        groups.setdefault(k, []).append(s)

    for k, items in groups.items():
        valid = [it for it in items
                 if it.get("predicted") not in (None, 0)
                 and it.get("actual") is not None]
        if len(valid) < MIN_SAMPLES_TO_CALIBRATE:
            # 样本不足：保留旧校准值（若已有），否则不写
            if k not in _params:
                continue
            _params[k]["n"] = len(valid)
            continue

        # 偏差比
        ratios = sorted(it["actual"] / it["predicted"] for it in valid)
        mid = ratios[len(ratios) // 2]
        bias = max(BIAS_CLAMP[0], min(BIAS_CLAMP[1], mid))

        # 置信度缩放：让平均报告置信度贴合平均实际命中率
        # 实际命中率近似 = mean(1 - abs_err_pct)，报告置信度 = mean(confidence)
        errs = [it.get("abs_err_pct", 0.0) for it in valid if it.get("confidence")]
        confs = [it["confidence"] for it in valid if it.get("confidence")]
        if errs and confs:
            realized = max(0.0, 1.0 - (sum(errs) / len(errs)))
            reported = sum(confs) / len(confs)
            if reported > 1e-3:
                scale = max(CONF_CLAMP[0], min(CONF_CLAMP[1], realized / reported))
            else:
                scale = 1.0
        else:
            scale = 1.0

        _params[k] = {
            "bias": round(bias, 4),
            "conf_scale": round(scale, 4),
            "n": len(valid),
        }
    _log(f"[CALIB] 重新校准完成，共 {len(_params)} 组参数")


def record_sample(horizon_type: str, horizon_offset: int,
                  predicted: Optional[float], actual: Optional[float],
                  confidence: float = 0.0) -> None:
    """记录一个回溯反馈样本（预测值 vs 实际值）。

    由预测函数在每次回溯检验后调用。异常一律静默，绝不影响主流程。
    """
    try:
        if predicted is None or actual is None:
            return
        p = float(predicted)
        a = float(actual)
        if p == 0:
            return
        abs_err_pct = abs(a - p) / abs(a) if a != 0 else abs(a - p) / abs(p)
        sample = {
            "k": _key(horizon_type, horizon_offset),
            "predicted": round(p, 6),
            "actual": round(a, 6),
            "confidence": round(float(confidence or 0.0), 4),
            "abs_err_pct": round(float(abs_err_pct), 6),
            "ts": int(time.time()),
        }
        with _lock:
            _load()
            _samples.append(sample)
            # 原地截断，保留最近 MAX_SAMPLES 个样本。
            # 注意：不要写成 _samples = _samples[-MAX_SAMPLES:]，否则会被 Python
            # 当作本函数局部变量，导致上方 _samples.append 触发 UnboundLocalError。
            if len(_samples) > MAX_SAMPLES:
                del _samples[:-MAX_SAMPLES]
            global _dirty_count
            _dirty_count += 1
            _maybe_flush()
    except Exception:  # noqa - 异常静默，绝不影响主流程
        pass


def get_correction(horizon_type: str, horizon_offset: int) -> Tuple[float, float]:
    """读取 (类型,步长) 的校准修正。

    Returns:
        (bias_factor, conf_scale)，无样本时返回 (1.0, 1.0)。
    """
    try:
        with _lock:
            _load()
            p = _params.get(_key(horizon_type, horizon_offset))
        if not p:
            return 1.0, 1.0
        return float(p.get("bias", 1.0)), float(p.get("conf_scale", 1.0))
    except Exception:  # noqa
        return 1.0, 1.0


def get_stats() -> Dict[str, int]:
    """返回 UI 展示用统计：总样本数、已校准组数。"""
    try:
        with _lock:
            _load()
            return {"samples": len(_samples), "groups": len(_params)}
    except Exception:  # noqa
        return {"samples": 0, "groups": 0}


def reset_calibration() -> bool:
    """清空校准（用户手动重置用）。"""
    try:
        with _lock:
            global _samples, _params, _dirty_count
            _samples, _params = [], {}
            _dirty_count = 0
            _flush()
        return True
    except Exception:  # noqa
        return False


def flush_now() -> None:
    """程序退出前显式落盘（可在 atexit 注册）。"""
    try:
        with _lock:
            _recalibrate_locked()
            _flush()
    except Exception:  # noqa
        pass
