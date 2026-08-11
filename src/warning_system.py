# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 预警系统
支持多级预警、声音预警和视觉提示
"""

import os
import threading
import time
from datetime import datetime
from typing import Dict, Callable, Optional, List, Tuple
import json


class WarningSystem:
    """预警管理系统（增强版）"""

    # 只预警重要参数
    IMPORTANT_PARAMS = {
        "化学需氧量", "氨氮", "非甲烷总烃",
        "二氧化硫", "氮氧化物", "颗粒物", "pH值"
    }

    # 废水参数（用于判断同值超时阈值）
    WATER_PARAMS = {"化学需氧量", "氨氮", "pH值"}
    # 废气参数
    GAS_PARAMS = {"非甲烷总烃", "二氧化硫", "氮氧化物", "颗粒物"}

    # 三种声音模式定义
    # sound_type: 'beep1' | 'beep2' | 'beep3'
    SOUND_TYPES = {
        'beep1': '叮咚（提示音）',
        'beep2': '滴滴（急促音）',
        'beep3': '警报（连续音）',
    }

    def __init__(self):
        self.alert_active = False
        self.alert_stop_event = threading.Event()
        self.warning_callback: Optional[Callable] = None
        self.current_warnings = set()       # 实时预警key集合
        self.current_pred_warnings = set()  # 预测预警key集合
        # 最新实时/预测预警详情，用于合并展示
        self._last_realtime_details: List[dict] = []
        self._last_pred_details: List[dict] = []

        # 声音开关（默认开启）
        self.sound_enabled = True

        # 声音类型（默认 beep1）
        self.sound_type = 'beep1'

        # 预警历史记录
        self.warning_history: List[dict] = []
        self.max_history = 1000  # 最多保存1000条记录

        # 预警历史文件
        self.history_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "warning_history.json"
        )

        # 创建数据目录
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        self._load_history()

        # ── 预测预警防抖机制 ────────────────────────────────────────────────────
        self._pred_warn_counts: Dict[Tuple[str, str], int] = {}
        self._pred_min_confidence = 0.15   # 置信度低于此值不触发预警
        self._pred_debounce_needed = 2     # 需要连续出现2次才真正报警
        self._pred_state_max_keys = 100    # 防抖/迟滞状态字典最大条目数

        # ── 预警迟滞机制 ──────────────────────────────────────────────────────
        self._pred_last_level: Dict[Tuple[str, str], str] = {}
        self._HYSTERESIS_MARGIN = 0.03

        # ── 同值检测机制 ────────────────────────────────────────────────────
        # _same_value_history: {(ent_name, subname, param): [(timestamp, value), ...]}
        # 每条记录包含时间戳和值，按实际时间窗口判断同值
        from collections import deque
        self._same_value_history: Dict[Tuple[str, str, str], deque] = {}
        self._same_value_max = 500  # 最大保留条数（足够覆盖4小时，按1分钟1条计算）

        # ── 急剧变化检测机制 ─────────────────────────────────────────────────
        # _last_value: {(ent_name, subname, param): last_value} 上一个有效值
        # _rapid_change_debounce: {(ent_name, subname, param): 冷却计数器}
        self._last_value: Dict[Tuple[str, str, str], float] = {}
        self._rapid_change_debounce: Dict[Tuple[str, str, str], int] = {}
        self._rapid_change_cooldown = 5  # 急剧变化后冷却5次（5分钟）才重新检测

        # ── 干预历史记录 ─────────────────────────────────────────────────────
        self._intervention_history: List[dict] = []
        self._max_intervention_history = 500
        self._intervention_file = os.path.join(
            os.path.dirname(self.history_file),
            "intervention_history.json"
        )
        self._load_intervention_history()

    def set_sound_enabled(self, enabled: bool):
        """设置声音报警开关"""
        self.sound_enabled = enabled
        if not enabled:
            self.stop_alert()

    def set_sound_type(self, sound_type: str):
        """设置声音类型：'beep1' | 'beep2' | 'beep3'"""
        if sound_type in self.SOUND_TYPES:
            self.sound_type = sound_type

    def set_warning_callback(self, callback: Callable):
        """设置预警回调函数（主线程更新UI）"""
        self.warning_callback = callback

    def start_alert(self, level: str = "黄色预警"):
        """开始声音预警（根据预警等级使用不同声音）"""
        if not self.sound_enabled:
            return
        if self.alert_active:
            return
        self.alert_active = True
        self.alert_stop_event.clear()
        threading.Thread(target=self._play_alert_sound, args=(level,), daemon=True).start()

    def stop_alert(self):
        """停止声音预警"""
        self.alert_active = False
        self.alert_stop_event.set()

    def _play_alert_sound(self, level: str):
        """循环播放预警音（根据声音类型和预警等级）"""
        import winsound

        stype = self.sound_type

        # ── beep1：叮咚（提示音，单音上升，柔和） ────────────────────────────
        if stype == 'beep1':
            if level == "黄色预警":
                pattern = [(880, 120), (1047, 160)]   # A5 → C6，间隔宽松
                interval = 1.2
            elif level == "橙色预警":
                pattern = [(784, 100), (988, 130), (1175, 150)]  # G5→B5→D6
                interval = 0.8
            else:  # 红色预警
                pattern = [(880, 100), (1175, 100), (1397, 180)]  # A5→D6→F6
                interval = 0.5

        # ── beep2：滴滴（急促音，双音快速） ──────────────────────────────────
        elif stype == 'beep2':
            if level == "黄色预警":
                pattern = [(1000, 80), (1000, 80)]
                interval = 0.9
            elif level == "橙色预警":
                pattern = [(1200, 70), (1200, 70), (1200, 70)]
                interval = 0.6
            else:  # 红色预警
                pattern = [(1400, 60), (1400, 60), (1400, 60), (1400, 60)]
                interval = 0.4

        # ── beep3：警报（连续扫频音，紧迫感强） ──────────────────────────────
        else:  # beep3
            if level == "黄色预警":
                pattern = [(700, 80), (800, 80), (900, 80), (800, 80)]
                interval = 0.8
            elif level == "橙色预警":
                pattern = [(600, 60), (750, 60), (900, 60), (1050, 60), (900, 60), (750, 60)]
                interval = 0.5
            else:  # 红色预警
                pattern = [(500, 50), (700, 50), (900, 50), (1100, 50),
                           (1100, 50), (900, 50), (700, 50), (500, 50)]
                interval = 0.35

        while self.alert_active and not self.alert_stop_event.is_set():
            try:
                for freq, dur in pattern:
                    if not self.alert_active or self.alert_stop_event.is_set():
                        break
                    winsound.Beep(freq, dur)
                time.sleep(interval)
            except Exception:
                break
        self.alert_active = False

    def check_and_alert(self, data: dict, thresholds: dict):
        """
        检查实时数据并触发预警

        支持三种预警类型：
        1. 超标预警：值超过/低于阈值
        2. 同值预警：连续同值超过阈值（废气30分钟/废水4小时，按实际时间计算）
        3. 急剧变化预警：值在短时间内大幅上升/下降

        Args:
            data: parse_realtime_data 返回的分组数据（已包含折算值）
            thresholds: 预警阈值配置
        """
        new_warnings = set()
        warnings_detail = []
        max_level = "正常"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 导入同值检测和急剧变化阈值配置
        try:
            from config import SAME_VALUE_THRESHOLDS, RAPID_CHANGE_THRESHOLDS
        except Exception:
            SAME_VALUE_THRESHOLDS = {}
            RAPID_CHANGE_THRESHOLDS = {}

        for subid, sub_data in data.items():
            subname = sub_data.get('subname', '')
            ent_name = sub_data.get('ent_name', '')

            for param in sub_data.get('params', []):
                param_name = param.get('name', '')
                value = param.get('value')

                if value is None:
                    continue

                # 只预警重要参数
                if param_name not in self.IMPORTANT_PARAMS:
                    continue

                if not isinstance(value, (int, float)):
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        continue

                # 用于预警记录的关键key（包含企业名避免冲突）
                warn_key = f"{ent_name}|{subname}_{param_name}"
                hist_key = (ent_name, subname, param_name)

                # ══ 预警类型1：超标预警（上下限） ══════════════════════════════
                from data_processor import get_warning_level
                level = get_warning_level(value, param_name, thresholds)

                if level != "正常":
                    new_warnings.add(warn_key)

                    # 更新最高预警等级
                    if level == "红色预警":
                        max_level = "红色预警"
                    elif level == "橙色预警" and max_level != "红色预警":
                        max_level = "橙色预警"
                    elif level == "黄色预警" and max_level == "正常":
                        max_level = "黄色预警"

                    warnings_detail.append({
                        'subname': subname,
                        'ent_name': ent_name,
                        'param': param_name,
                        'value': value,
                        'level': level,
                        'threshold': thresholds.get(param_name, 'N/A'),
                        'datetime': now_str,
                        'type': 'realtime'
                    })
                    self._add_to_history(warnings_detail[-1])

                # ══ 预警类型2：同值检测（基于实际时间窗口）═══════════════════════
                if param_name in SAME_VALUE_THRESHOLDS:
                    max_same_minutes = SAME_VALUE_THRESHOLDS[param_name]  # 时间窗口（分钟）

                    if hist_key not in self._same_value_history:
                        self._same_value_history[hist_key] = deque(maxlen=self._same_value_max)

                    history = self._same_value_history[hist_key]
                    
                    # 记录当前时间戳和值
                    current_time = time.time()
                    history.append((current_time, value))

                    # 计算时间窗口：现在 - 最早记录的时间
                    if len(history) >= 2:
                        earliest_time = history[0][0]
                        window_duration = (current_time - earliest_time) / 60  # 转换为分钟

                        # 如果时间窗口已达到阈值（max_same_minutes分钟），检查是否全部同值
                        if window_duration >= max_same_minutes:
                            # 获取时间窗口内的所有值
                            window_values = [v for _, v in history]
                            first_val = window_values[0]
                            
                            # 检查所有值是否相同（排除0值）
                            if first_val is not None and first_val != 0:
                                all_same = all(abs(v - first_val) < 1e-9 for v in window_values)
                                if all_same:
                                    same_key = f"{warn_key}_samevalue"
                                    if same_key not in self.current_warnings:
                                        new_warnings.add(same_key)
                                        same_level = "黄色预警"
                                        if max_level == "正常":
                                            max_level = same_level
                                        warnings_detail.append({
                                            'subname': subname,
                                            'ent_name': ent_name,
                                            'param': param_name,
                                            'value': value,
                                            'level': same_level,
                                            'threshold': f"连续{max_same_minutes}分钟同值",
                                            'datetime': now_str,
                                            'type': 'realtime_samevalue',
                                            'detail': f"连续{max_same_minutes}分钟值保持不变（{value}），可能存在设备故障或数据异常"
                                        })
                                        self._add_to_history(warnings_detail[-1])
                                        # 清空历史，防止持续重复报警
                                        history.clear()
                else:
                    # 非同值检测参数：保留少量历史用于急剧变化检测
                    if hist_key not in self._same_value_history:
                        self._same_value_history[hist_key] = deque(maxlen=5)
                    self._same_value_history[hist_key].append((time.time(), value))

                # ══ 预警类型3：急剧变化检测 ══════════════════════════════════
                if param_name in RAPID_CHANGE_THRESHOLDS:
                    change_pct = RAPID_CHANGE_THRESHOLDS[param_name]  # 百分比

                    # 检查冷却状态
                    cooldown = self._rapid_change_debounce.get(hist_key, 0)
                    if cooldown > 0:
                        self._rapid_change_debounce[hist_key] = cooldown - 1
                    else:
                        last_val = self._last_value.get(hist_key)
                        if last_val is not None and last_val != 0 and value != last_val:
                            change = abs(value - last_val) / abs(last_val) * 100
                            if change >= change_pct:
                                change_type = "急剧上升" if value > last_val else "急剧下降"
                                rapid_key = f"{warn_key}_rapidchange"
                                if rapid_key not in self.current_warnings:
                                    new_warnings.add(rapid_key)
                                    rapid_level = "黄色预警"
                                    if max_level == "正常":
                                        max_level = rapid_level
                                    warnings_detail.append({
                                        'subname': subname,
                                        'ent_name': ent_name,
                                        'param': param_name,
                                        'value': value,
                                        'level': rapid_level,
                                        'threshold': f"变化{change:.0f}%（>{change_pct}%）",
                                        'datetime': now_str,
                                        'type': 'realtime_rapidchange',
                                        'detail': f"数值{change_type}（{last_val:.2f} → {value:.2f}，变化{change:.0f}%）"
                                    })
                                    self._add_to_history(warnings_detail[-1])
                                    # 触发冷却
                                    self._rapid_change_debounce[hist_key] = self._rapid_change_cooldown

                # 更新急剧变化检测的上一个值（对所有参数生效）
                self._last_value[hist_key] = value

                # ══ 防止状态字典无限增长 ═══════════════════════════════════
                if len(self._same_value_history) > 500:
                    # 删除最老的10%
                    excess = len(self._same_value_history) - 400
                    for k in list(self._same_value_history.keys())[:excess]:
                        self._same_value_history.pop(k, None)
                if len(self._last_value) > 500:
                    excess = len(self._last_value) - 400
                    for k in list(self._last_value.keys())[:excess]:
                        self._last_value.pop(k, None)
                if len(self._rapid_change_debounce) > 500:
                    excess = len(self._rapid_change_debounce) - 400
                    for k in list(self._rapid_change_debounce.keys())[:excess]:
                        self._rapid_change_debounce.pop(k, None)

        # 更新实时预警状态
        self.current_warnings = new_warnings
        self._last_realtime_details = warnings_detail

        # 合并实时+预测，统一刷新UI
        self._merge_and_notify()

    def check_and_alert_predictions(self, prediction_results: list, thresholds: dict,
                                     confidence_threshold: float = None):
        """
        检查预测结果并触发声音预警

        新增防护机制：
        1. 置信度门槛：预测置信度低于 _pred_min_confidence 时不触发声音报警
        2. 防抖机制：单个时间点超标必须连续出现 _pred_debounce_needed 次才触发
        3. 降级机制：低置信度预测（< 0.30）的预警等级最高为橙色

        prediction_results: list of dict，每条包含
            {'ent_name', 'subname', 'param', 'predicted', 'warning_level',
             'pred_type'（'当前小时' / '下一小时' / '当日均值'），
             'confidence'（可选，置信度）}
        """
        conf_thresh = (confidence_threshold if confidence_threshold is not None
                       else self._pred_min_confidence)

        new_pred_warnings = set()
        warnings_detail = []
        max_level = "正常"

        # 统计本轮各 (subname, param) 的预警次数，用于防抖
        this_round_counts: Dict[Tuple[str, str], int] = {}

        for item in prediction_results:
            level = item.get('warning_level', '正常')
            if level == '正常':
                continue

            param_name = item.get('param', '')
            if param_name not in self.IMPORTANT_PARAMS:
                continue

            subname = item.get('subname', '')
            ent_name = item.get('ent_name', '')
            pred_type = item.get('pred_type', '预测')
            predicted = item.get('predicted')
            confidence = item.get('confidence', 1.0)  # 默认为1.0（实时数据场景）

            warning_key = f"pred_{subname}_{param_name}_{pred_type}"
            key2 = (subname, param_name)             # 防抖用的稳定key

            # ── 置信度门槛：太低的数据不参与预警 ──────────────────────────────
            if confidence < conf_thresh:
                # 低于门槛：记录但不触发，仍需防抖计数归零
                this_round_counts[key2] = this_round_counts.get(key2, 0) + 1
                # 低于门槛的项不能提升 max_level
                continue

            # ── 防抖计数：跟踪该 (排放口, 参数) 连续出现预警的次数 ───────────
            # 之前已有计数 + 本轮计数，达到阈值才触发
            prev_count = self._pred_warn_counts.get(key2, 0)
            this_count = this_round_counts.get(key2, 0) + prev_count
            this_round_counts[key2] = this_count

            if this_count < self._pred_debounce_needed:
                # 尚未达到防抖阈值：记录本次，但不触发声音/写历史
                continue

            new_pred_warnings.add(warning_key)

            # ── 迟滞机制：防止边界值在预警等级间反复跳动 ───────────────────
            # 升级（正常→预警）：需要超过阈值+3%才确认
            # 降级（预警→正常）：需要低于阈值-3%才确认（需原始等级，非effective_level）
            prev_lvl = self._pred_last_level.get(key2, '正常')
            lvl_order = {"正常": 0, "黄色预警": 1, "橙色预警": 2, "红色预警": 3}
            prev_order = lvl_order.get(prev_lvl, 0)
            curr_order = lvl_order.get(effective_level, 0)
            threshold_val = thresholds.get(param_name, 0)
            margin = threshold_val * self._HYSTERESIS_MARGIN if threshold_val else 0

            if curr_order > prev_order:
                # 升级：要求值超过当前等级阈值+3%才真正升级
                if threshold_val > 0 and predicted < (threshold_val * 1.03):
                    # 未超过迟滞边界，压制升级
                    effective_level = prev_lvl if prev_lvl != '正常' else '黄色预警'
            elif curr_order < prev_order and curr_order == 0:
                # 降级到正常：要求值低于阈值-3%才真正降级
                if threshold_val > 0 and predicted > (threshold_val - margin):
                    # 未低于迟滞边界，保持原等级
                    effective_level = prev_lvl

            # 同步更新 last_level（下次调用时使用）
            if effective_level != '正常':
                self._pred_last_level[key2] = effective_level
            elif curr_order == 0:
                self._pred_last_level[key2] = '正常'

            # ── 低置信度降级：<0.30 的预测等级最高为橙色 ───────────────────
            effective_level = level
            if confidence < 0.30:
                level_order = {"正常": 0, "黄色预警": 1, "橙色预警": 2, "红色预警": 3}
                if level_order.get(level, 0) > level_order.get("橙色预警", 0):
                    effective_level = "橙色预警"

            # 更新最高等级
            if effective_level == "红色预警":
                max_level = "红色预警"
            elif effective_level == "橙色预警" and max_level != "红色预警":
                max_level = "橙色预警"
            elif effective_level == "黄色预警" and max_level == "正常":
                max_level = "黄色预警"

            detail = {
                'subname': subname,
                'ent_name': ent_name,
                'param': param_name,
                'value': predicted,
                'level': effective_level,
                'raw_level': level,               # 原始计算等级（用于参考）
                'confidence': confidence,
                'threshold': thresholds.get(param_name, 'N/A'),
                'datetime': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'type': f'prediction_{pred_type}'
            }
            warnings_detail.append(detail)
            self._add_to_history(detail)

        # 同步防抖计数：本轮没出现的 (排放口, 参数) → 计数归零
        active_keys = set(this_round_counts.keys())
        all_keys = set(self._pred_warn_counts.keys())
        for k in all_keys - active_keys:
            self._pred_warn_counts[k] = 0

        # 更新本轮有效计数
        for k, v in this_round_counts.items():
            if v > 0:
                self._pred_warn_counts[k] = v

        # ── 防止内存泄漏：字典容量限制 ────────────────────────────────────────
        # 清理已归零且不在活跃集合中的旧条目
        stale = [k for k, v in self._pred_warn_counts.items() if v == 0 and k not in active_keys]
        for k in stale:
            del self._pred_warn_counts[k]
        # 如果整体规模超限，裁剪最老的条目
        if len(self._pred_warn_counts) > self._pred_state_max_keys:
            excess = len(self._pred_warn_counts) - self._pred_state_max_keys
            # 按值升序裁剪（优先删除计数低的）
            for k, _ in sorted(self._pred_warn_counts.items(), key=lambda x: x[1])[:excess]:
                self._pred_warn_counts.pop(k, None)
        if len(self._pred_last_level) > self._pred_state_max_keys:
            excess = len(self._pred_last_level) - self._pred_state_max_keys
            for k in list(self._pred_last_level.keys())[:excess]:
                self._pred_last_level.pop(k, None)

        # 更新预测预警状态（无论有无超标都更新，确保正常时自动清除）
        self.current_pred_warnings = new_pred_warnings
        self._last_pred_details = warnings_detail

        # 合并实时+预测，统一刷新UI
        self._merge_and_notify()


    def _merge_and_notify(self):
        """
        合并实时预警和预测预警，统一计算最高等级并回调通知UI。
        只要有任意一类预警就显示；两类都正常时才清除。
        """
        LEVEL_ORDER = {"正常": 0, "黄色预警": 1, "橙色预警": 2, "红色预警": 3}

        all_details = self._last_realtime_details + self._last_pred_details
        has_warning = bool(all_details)

        if has_warning:
            max_level = max(
                (d.get('level', '正常') for d in all_details),
                key=lambda l: LEVEL_ORDER.get(l, 0),
                default="正常"
            )
            if not self.alert_active:
                self.start_alert(max_level)
        else:
            max_level = "正常"
            self.stop_alert()

        if self.warning_callback:
            self.warning_callback(all_details, is_warning=has_warning, max_level=max_level)

    def _add_to_history(self, warning: dict):
        """添加到预警历史"""
        self.warning_history.append(warning)

        # 限制历史记录数量
        if len(self.warning_history) > self.max_history:
            self.warning_history = self.warning_history[-self.max_history:]

        # 保存到文件
        self._save_history()

    def _load_history(self):
        """从文件加载预警历史"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.warning_history = json.load(f)
        except Exception as e:
            print(f"[DEBUG] 加载预警历史失败: {e}")
            self.warning_history = []

    def _save_history(self):
        """保存预警历史到文件"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.warning_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[DEBUG] 保存预警历史失败: {e}")

    def get_warning_history(self, limit: int = 100) -> List[dict]:
        """获取预警历史（最近N条）"""
        return self.warning_history[-limit:]

    def clear_history(self):
        """清空预警历史"""
        self.warning_history = []
        self._save_history()

    # ── 干预历史管理 ─────────────────────────────────────────────────────────

    def _load_intervention_history(self):
        """从文件加载干预历史"""
        try:
            if os.path.exists(self._intervention_file):
                with open(self._intervention_file, 'r', encoding='utf-8') as f:
                    self._intervention_history = json.load(f)
        except Exception as e:
            print(f"[DEBUG] 加载干预历史失败: {e}")
            self._intervention_history = []

    def _save_intervention_history(self):
        """保存干预历史到文件"""
        try:
            with open(self._intervention_file, 'w', encoding='utf-8') as f:
                json.dump(self._intervention_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[DEBUG] 保存干预历史失败: {e}")

    def record_intervention(self, subname: str, param: str, ent_name: str,
                           intervention_intensity: str, intervention_state: str,
                           predicted_values: dict, actual_values: dict = None):
        """
        记录一次干预事件，用于后续分析预测准确性。

        Args:
            subname: 排放口名称
            param: 参数名称
            ent_name: 企业名称
            intervention_intensity: 干预强度("weak"/"moderate"/"strong"/"shutdown")
            intervention_state: 干预状态机状态
            predicted_values: 预测值 {"+1h": float, "+2h": float, "+3h": float}
            actual_values: 实际值（可选，用于后续对比预测准确性）{"+1h": float, ...}
        """
        record = {
            'datetime': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'subname': subname,
            'param': param,
            'ent_name': ent_name,
            'intensity': intervention_intensity,
            'state': intervention_state,
            'predicted': predicted_values,
            'actual': actual_values,  # 后续更新
            'verified': False         # 是否已验证（对比了实际值）
        }
        self._intervention_history.append(record)

        # 限制历史记录数量
        if len(self._intervention_history) > self._max_intervention_history:
            self._intervention_history = self._intervention_history[-self._max_intervention_history:]

        self._save_intervention_history()

    def verify_intervention(self, subname: str, param: str, actual_values: dict):
        """
        验证干预效果：更新干预记录中的实际值，用于对比预测准确性。

        Args:
            subname: 排放口名称
            param: 参数名称
            actual_values: 实际值 {"+1h": float, "+2h": float, "+3h": float}
        """
        # 查找最新的未验证记录
        for record in reversed(self._intervention_history):
            if (record.get('subname') == subname and
                record.get('param') == param and
                not record.get('verified', False)):
                record['actual'] = actual_values
                record['verified'] = True
                record['verified_datetime'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save_intervention_history()
                break

    def get_intervention_history(self, limit: int = 50) -> List[dict]:
        """获取干预历史（最近N条）"""
        return self._intervention_history[-limit:]

    def get_intervention_accuracy(self, subname: str = None, param: str = None) -> dict:
        """
        获取干预预测准确率统计。

        Returns:
            dict: {
                "total_records": int,
                "verified_records": int,
                "avg_error_pct": float,  # 平均误差百分比
                "by_intensity": {...}    # 按干预强度分类的统计
            }
        """
        records = self._intervention_history
        if subname:
            records = [r for r in records if r.get('subname') == subname]
        if param:
            records = [r for r in records if r.get('param') == param]

        verified = [r for r in records if r.get('verified', False)]

        if not verified:
            return {"total_records": len(records), "verified_records": 0}

        # 计算误差
        errors = []
        by_intensity = {}
        for r in verified:
            intensity = r.get('intensity', 'unknown')
            if intensity not in by_intensity:
                by_intensity[intensity] = {"count": 0, "errors": []}

            predicted = r.get('predicted', {})
            actual = r.get('actual', {})
            for hour in ['+1h', '+2h', '+3h']:
                p = predicted.get(hour)
                a = actual.get(hour)
                if p is not None and a is not None and a > 0:
                    err_pct = abs(p - a) / a * 100
                    errors.append(err_pct)
                    by_intensity[intensity]["errors"].append(err_pct)
            by_intensity[intensity]["count"] += 1

        # 汇总按强度统计
        intensity_stats = {}
        for intensity, data in by_intensity.items():
            if data["errors"]:
                intensity_stats[intensity] = {
                    "count": data["count"],
                    "avg_error_pct": round(sum(data["errors"]) / len(data["errors"]), 2)
                }

        return {
            "total_records": len(records),
            "verified_records": len(verified),
            "avg_error_pct": round(sum(errors) / len(errors), 2) if errors else 0,
            "by_intensity": intensity_stats
        }

    def is_alerting(self) -> bool:
        return self.alert_active

    def get_warning_count_today(self) -> int:
        """获取今日预警次数"""
        today = datetime.now().strftime("%Y-%m-%d")
        return sum(
            1 for w in self.warning_history
            if w.get('datetime', '').startswith(today)
        )


class PredictionWarning:
    """预测预警（小时/日均预测）"""

    @staticmethod
    def check_hour_prediction(predicted_value: float, param_name: str, thresholds: dict) -> Tuple[bool, str]:
        """检查小时预测值是否超标，返回(是否超标, 预警等级)"""
        from data_processor import get_warning_level
        level = get_warning_level(predicted_value, param_name, thresholds)
        return (level != "正常", level)

    @staticmethod
    def check_day_prediction(predicted_value: float, param_name: str, thresholds: dict) -> Tuple[bool, str]:
        """检查日均预测值是否超标，返回(是否超标, 预警等级)"""
        from data_processor import get_warning_level
        level = get_warning_level(predicted_value, param_name, thresholds)
        return (level != "正常", level)
