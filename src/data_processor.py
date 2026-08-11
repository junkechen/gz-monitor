# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 数据处理与预测模块
"""

import statistics
import math
from datetime import datetime
from typing import List, Dict, Optional


# 参数名称映射（code -> 中文名）
CODE_TO_NAME = {
    # 废水
    "316": "化学需氧量", "302": "pH值", "494": "流量",
    "492": "废水流量", "311": "氨氮", "301": "水温", "495": "累计流量",
    # 废气/VOCs
    "383": "非甲烷总烃", "525": "烟气温度", "210": "烟气流量",
    "209": "烟气含氧量", "220": "碳氢化合物总烃", "299": "甲烷",
    "211": "流速", "527": "烟气湿度", "526": "烟气压力",
    # 废气（标准参数）
    "SO2": "二氧化硫", "NOx": "氮氧化物", "PM": "颗粒物",
    # 冠锌等企业的数字代码映射
    "201": "二氧化硫", "203": "氮氧化物", "207": "颗粒物",
}

NAME_TO_CODE = {v: k for k, v in CODE_TO_NAME.items()}

# 废水排放口显示参数
WATER_PARAMS_DISPLAY = ["化学需氧量", "pH值", "流量", "废水流量", "氨氮"]
# VOCs 排口专用显示参数（含非甲烷总烃）
VOCS_PARAMS_DISPLAY = ["非甲烷总烃", "烟气温度", "烟气流量", "烟气含氧量", "流速"]
# 普通废气排放口（锅炉/燃烧类）显示参数（不含非甲烷总烃）
GAS_PARAMS_DISPLAY = ["二氧化硫", "氮氧化物", "颗粒物", "烟气温度", "烟气流量", "烟气含氧量", "流速"]

# 废水排放口subtype
WATER_SUBTYPE = "51"
# VOCs/废气排放口subtype
GAS_SUBTYPE = "64"

# 排放口类型判断
WATER_TYPES = ["废水", "污水"]
GAS_TYPES = ["VOCs", "废气", "烟气", "vocs"]
VOCS_TYPES = ["VOCs", "vocs", "有机废气"]  # VOCs 专属类型关键词


def is_water_sub(sub_type: str) -> bool:
    return any(t in sub_type for t in WATER_TYPES)


def is_vocs_sub(sub_type: str) -> bool:
    """判断是否为 VOCs 排口（使用有机溶剂/涂装类）"""
    return any(t in sub_type for t in VOCS_TYPES)


def is_gas_sub(sub_type: str) -> bool:
    return any(t in sub_type for t in GAS_TYPES)


def get_subtype_code(sub_type: str) -> str:
    if is_water_sub(sub_type):
        return WATER_SUBTYPE
    return GAS_SUBTYPE


def parse_realtime_data(raw: dict) -> Dict[str, List[dict]]:
    """
    解析实时数据，按排放口分组
    支持多企业数据，在subid中包含企业名称作为唯一键
    返回: {subid: [{name, value, unit, std, is_exceed, datetime, status, ent_name}, ...]}
    """
    result = {}
    rows = raw.get('rows', [])
    for row in rows:
        subid = str(row.get('C0007_SUBSTATION_ID', ''))
        if not subid:
            continue

        # 多企业支持：使用企业名称作为subid前缀以避免冲突
        ent_name = row.get('ENTERPRISE_NAME', '')
        unique_key = f"{subid}|{ent_name}" if ent_name else subid

        if unique_key not in result:
            result[unique_key] = {
                'subid': subid,  # 原始排口ID
                'ent_name': ent_name,  # 企业名称
                'subname': row.get('C0007_SUBNAME', ''),
                'subtype': row.get('SUBTYPE', ''),
                'datetime': row.get('DATETIME', ''),
                'status': row.get('C0202_NAME', ''),
                'params': []
            }
        param_name = row.get('C0001_ITEM_NAME', '')
        value = row.get('C1703_VALUE')
        std = row.get('C0115_STDVALUE', '')
        cbbs = row.get('CBBS', 0)
        result[unique_key]['params'].append({
            'name': param_name,
            'code': str(row.get('C0001_ITEM_CODE', '')),
            'value': value,
            'std': std,
            'is_exceed': cbbs != 0 if cbbs is not None else False,
            'datetime': row.get('DATETIME', ''),
        })
    return result


def convert_history_to_realtime_format(history_raw: dict, subid: str, ent_name: str,
                                       subname: str, subtype: str) -> dict:
    """
    将历史API返回的分钟数据转换为 parse_realtime_data 兼容格式，
    用于热电厂获取折算值。

    Args:
        history_raw: get_minute_data_current_hour() 返回的原始数据
        subid: 排放口ID
        ent_name: 企业名称
        subname: 排放口名称
        subtype: 排放口类型

    Returns:
        parse_realtime_data 格式的 dict（单个subid的分组）
    """
    rows = history_raw.get('rows', [])
    if not rows:
        return {}

    # 取最新一条数据
    latest = rows[0]

    # 遍历 latest 的所有 key，提取 val_xxx / stand_xxx / state_xxx
    result = {
        'subid': subid,
        'ent_name': ent_name,
        'subname': subname,
        'subtype': subtype,
        'datetime': latest.get('DateTime', ''),
        'status': latest.get('C0202_NAME', latest.get('STATUS', '在线')),
        'params': []
    }

    # 收集所有 code -> (name, std, is_exceed)
    params_found = set()
    for key in latest.keys():
        if key.startswith('val_'):
            code = key[4:]  # 提取代码，如 "201"
            if code in params_found:
                continue
            params_found.add(code)

            # 获取参数名称：优先用 CODE_TO_NAME，否则用原始 code
            param_name = CODE_TO_NAME.get(code, code)

            # 取值（兼容多种折算字段名）
            cvt_val = None
            for fld in [f'cvt_{code}', f'Corrected_{code}', f'val_{code}', 'Cvt', 'Corrected', 'cvt']:
                if fld in latest:
                    v = latest.get(fld)
                    if v is not None and v != '' and str(v) != '-9999':
                        try:
                            cvt_val = float(v)
                            break
                        except (ValueError, TypeError):
                            pass

            # 取标准值
            std_val = ''
            std_key = f'stand_{code}'
            if std_key in latest:
                sv = latest.get(std_key)
                if sv is not None and sv != '' and str(sv) != '-9999':
                    std_val = str(sv)

            # 取超标状态
            state_val = latest.get(f'state_{code}', '0')
            is_exceed = state_val != '0'

            result['params'].append({
                'name': param_name,
                'code': code,
                'value': cvt_val,          # 折算后的值
                'corrected_value': cvt_val,  # 明确标记为折算值，供预警系统使用
                'std': std_val,
                'is_exceed': is_exceed,
                'datetime': latest.get('DateTime', ''),
            })

    return result


def merge_corrected_data_into_grouped(grouped_data: dict, multi_client,
                                      code_list: list) -> dict:
    """
    对 grouped_data 中的热电厂排放口，用折算数据替换实测值。
    折算数据从 get_minute_data_current_hour(use_corrected=True) 获取。

    Returns:
        新的 grouped_data，其中热电厂使用折算值
    """
    import copy

    result = copy.deepcopy(grouped_data)

    for unique_key, data in grouped_data.items():
        ent_name = data.get('ent_name', '')
        subname = data.get('subname', '')
        subid = data.get('subid', '')
        subtype = data.get('subtype', '')

        # 只处理热电厂（企业名含"热电"且非废水）
        if '热电' not in ent_name or '废水' in subtype or '污水' in subtype:
            continue

        if not subid:
            continue

        # 构建 codes 参数（从现有数据获取参数代码）
        params = data.get('params', [])
        if not params:
            continue

        codes_str = ','.join(str(p.get('code', '')) for p in params if p.get('code'))
        if not codes_str:
            continue

        # 从 subtypes 中判断排放口类型
        if '废水' in subtype or '污水' in subtype:
            subtype_code = '51'
        else:
            subtype_code = '64'

        # 获取客户端
        client_info = multi_client.get_client_by_subid(subid)
        if not client_info:
            continue
        _client = client_info.get('client')
        if not _client:
            continue

        try:
            corrected_result = _client.get_minute_data_current_hour(subid, subtype_code, codes_str, True)
            corrected_rows = corrected_result.get('rows', [])
            if not corrected_rows:
                continue

            latest = corrected_rows[0]

            # 构建 code -> corrected_value 映射
            cvt_map = {}
            std_map = {}
            for p in params:
                code = str(p.get('code', ''))
                if not code:
                    continue

                # 取折算值
                cvt_val = None
                for fld in [f'cvt_{code}', f'Corrected_{code}', f'val_{code}', 'Cvt', 'Corrected', 'cvt']:
                    if fld in latest:
                        v = latest.get(fld)
                        if v is not None and v != '' and str(v) != '-9999':
                            try:
                                cvt_val = float(v)
                                break
                            except (ValueError, TypeError):
                                pass
                if cvt_val is not None:
                    cvt_map[code] = cvt_val

                # 取折算标准
                std_key = f'stand_{code}'
                if std_key in latest:
                    sv = latest.get(std_key)
                    if sv is not None and sv != '' and str(sv) != '-9999':
                        std_map[code] = str(sv)

            # 更新 result 中对应的 params
            if unique_key in result:
                for p in result[unique_key]['params']:
                    code = str(p.get('code', ''))
                    if code in cvt_map:
                        p['value'] = cvt_map[code]     # 用折算值替换
                        p['corrected_value'] = cvt_map[code]  # 标记为折算
                        p['is_thermal_corrected'] = True  # 标记热电折算来源
                    if code in std_map:
                        p['corrected_std'] = std_map[code]  # 折算标准

        except Exception:
            pass  # 单个排放口失败不影响其他

    return result


def parse_history_data(raw: dict, codes_list: List[str]) -> List[dict]:
    """
    解析历史数据
    返回规范化的行列表
    """
    rows = raw.get('rows', [])
    parsed = []
    for row in rows:
        entry = {'datetime': row.get('DateTime', '')}
        for code in codes_list:
            val_key = f'val_{code}'
            std_key = f'stand_{code}'
            state_key = f'state_{code}'
            status_key = f'status_{code}'
            entry[code] = {
                'value': row.get(val_key),
                'std': row.get(std_key, ''),
                'is_exceed': row.get(state_key, '0') != '0',
                'status': row.get(status_key, ''),
                'ex': row.get(f'ex_{code}'),
            }
        parsed.append(entry)
    return parsed


def _filter_outliers(vals: List[float], method: str = 'iqr', threshold: float = 1.5) -> List[float]:
    """
    异常值过滤：使用IQR（四分位距）法或Z-Score法过滤异常值。

    Args:
        vals: 输入数据列表
        method: 'iqr'（四分位距）或 'zscore'（Z分数）
        threshold: 异常值阈值
            - IQR法：1.5=IQR的四分位数，3.0=极端值
            - ZScore法：2.0=偏离2个标准差，3.0=偏离3个标准差

    Returns:
        过滤后的数据列表（原始索引顺序）
    """
    if len(vals) < 4:
        return vals

    result = []
    for v in vals:
        if v is None:
            continue
        result.append(v)

    if len(result) < 4:
        return vals

    if method == 'iqr':
        # IQR法
        sorted_vals = sorted(result)
        q1_idx = len(sorted_vals) // 4
        q3_idx = 3 * len(sorted_vals) // 4
        q1 = sorted_vals[q1_idx]
        q3 = sorted_vals[q3_idx]
        iqr = q3 - q1
        lower = q1 - threshold * iqr
        upper = q3 + threshold * iqr
        return [v for v in vals if v is not None and lower <= v <= upper]
    else:
        # ZScore法
        mean_val = statistics.mean(result)
        std_val = statistics.stdev(result) if len(result) > 1 else 0
        if std_val == 0:
            return vals
        return [v for v in vals if v is not None and abs(v - mean_val) / std_val <= threshold]


def _moving_average_smooth(vals: List[float], window: int = 3) -> List[float]:
    """
    滑动窗口平滑：使用移动平均减少噪声波动。

    Args:
        vals: 输入数据列表
        window: 滑动窗口大小（默认3）

    Returns:
        平滑后的数据列表
    """
    if len(vals) < window:
        return vals

    result = []
    for i in range(len(vals)):
        start = max(0, i - window // 2)
        end = min(len(vals), i + window // 2 + 1)
        window_vals = [vals[j] for j in range(start, end) if vals[j] is not None]
        if window_vals:
            result.append(sum(window_vals) / len(window_vals))
        else:
            result.append(vals[i])
    return result


def _linear_regression_slope(vals: List[float], use_outlier_filter: bool = True):
    """
    用最小二乘法计算时间序列的斜率（趋势变化率 %）。
    比"前后半段均值对比"对噪声更鲁棒。
    返回：(slope_percent, r2)
      slope_percent: 相对于均值的每秒变化率(%)，None 表示数据不足以计算
      r2: 决定系数，0-1，越接近1说明趋势越明显
    """
    n = len(vals)
    if n < 4:
        return None, 0
    mean_val = statistics.mean(vals)
    if mean_val == 0:
        return None, 0
    # x = 时间索引 (0, 1, 2, ...)
    x_mean = (n - 1) / 2
    ss_xx = sum((i - x_mean) ** 2 for i in range(n))
    if ss_xx == 0:
        return None, 0
    ss_xy = sum((i - x_mean) * (v - mean_val) for i, v in enumerate(vals))
    slope_per_step = ss_xy / ss_xx          # 每步增量
    slope_percent = slope_per_step / mean_val * 100  # 相对于均值的百分比
    # 计算 R²
    ss_tot = sum((v - mean_val) ** 2 for v in vals)
    r2 = (ss_xy ** 2) / (ss_xx * ss_tot) if ss_tot > 0 else 0
    return slope_percent, min(1.0, r2)


def predict_hour_value(minute_values: List[float], method: str = 'weighted', with_trend: bool = True) -> dict:
    """
    根据当前小时内分钟数据预测小时均值

    Args:
        minute_values: 分钟数据列表
        method: 'simple'=简单平均, 'weighted'=加权（近期权重更高）, 'trend'=趋势加权
        with_trend: 是否分析数据趋势

    Returns:
        dict: {
            'predicted': 预测值,
            'confidence': 置信度 (0-1),
            'trend': 趋势 ('up', 'down', 'stable'),
            'trend_rate': 趋势变化率,
            'data_points': 数据点数量,
            'data_completeness': 数据完整度 (0-1)
        }
    """
    if not minute_values:
        return {'predicted': None, 'confidence': 0, 'trend': 'stable', 'trend_rate': 0, 'data_points': 0, 'data_completeness': 0}

    vals = [v for v in minute_values if v is not None]
    if not vals:
        return {'predicted': None, 'confidence': 0, 'trend': 'stable', 'trend_rate': 0, 'data_points': 0, 'data_completeness': 0}

    n = len(vals)

    # ── 预测稳定性增强：异常值过滤 + 滑动平滑 ────────────────────────────
    # 只有数据量足够时才进行过滤（避免过度过滤）
    if n >= 10:
        vals_filtered = _filter_outliers(vals, method='iqr', threshold=1.5)
        if len(vals_filtered) >= n * 0.6:  # 过滤后保留至少60%的数据才应用
            vals = vals_filtered
        # 滑动平均平滑（仅对趋势分析使用，不影响原始数据）
        vals_smooth = _moving_average_smooth(vals, window=3)
    else:
        vals_smooth = vals

    predicted = None
    n = len(vals)

    # 计算预测值
    if method == 'weighted' or method == 'trend':
        # 加权平均，近期数据权重更高
        weights = list(range(1, n + 1))
        if method == 'trend' and n >= 3:
            # 趋势加权：考虑数据的变化趋势
            recent_trend = sum(vals[-3:]) / 3 - sum(vals[-6:-3]) / 3 if n >= 6 else 0
            # 如果趋势向上，给予更高权重
            trend_factor = 1 + (recent_trend / (sum(vals) / n)) * 0.3 if sum(vals) > 0 else 1
            weights = [w * trend_factor for w in weights]

        weighted_sum = sum(v * w for v, w in zip(vals, weights))
        predicted = weighted_sum / sum(weights)
    else:
        predicted = statistics.mean(vals)

    # 计算置信度（基于数据量和稳定性）
    # 数据完整度：假设每小时最多60个数据点
    data_completeness = min(1.0, n / 60)

    # 数据稳定性：标准差越小，置信度越高
    if n >= 2:
        std_dev = statistics.stdev(vals)
        # 归一化标准差（相对于均值）
        cv = (std_dev / abs(predicted)) if predicted != 0 else float('inf')
        stability_score = max(0, 1 - cv * 2)  # 变异系数越小，稳定性越高
    else:
        stability_score = 0.5

    # 置信度 = 数据完整度 * 0.6 + 稳定性 * 0.4
    confidence = data_completeness * 0.6 + stability_score * 0.4

    # 数据稀疏惩罚：<10个点大幅降低置信度（防止5个点就触发预警）
    if n < 10:
        sparsity_penalty = n / 10.0
        confidence *= sparsity_penalty
    # 数据量极低（<5）：额外严苛，直接降为0
    if n < 5:
        confidence = min(confidence, 0.05)

    confidence = max(0, min(1, confidence))

    # 分析趋势：使用平滑后的数据进行线性回归（减少噪声影响）
    trend = 'stable'
    trend_rate = 0

    if with_trend and n >= 4:
        # 使用平滑后的数据进行趋势分析，减少噪声影响
        slope_pct, r2 = _linear_regression_slope(vals_smooth)
        if slope_pct is not None:
            # R² < 0.3 → 趋势不显著，视为平稳
            # 仅当趋势显著（R² ≥ 0.3）且变化率超过 2% 才判定方向
            if r2 >= 0.3:
                if slope_pct > 2.0:
                    trend = 'up'
                    trend_rate = slope_pct
                elif slope_pct < -2.0:
                    trend = 'down'
                    trend_rate = slope_pct

        # 限制趋势率幅度：单小时内波动噪声不应超过±25%，防止预测值指数级放大
        trend_rate = max(-25.0, min(25.0, trend_rate))

    return {
        'predicted': predicted,
        'confidence': round(confidence, 2),
        'trend': trend,
        'trend_rate': round(trend_rate, 2),
        'data_points': n,
        'data_completeness': round(data_completeness, 2)
    }


def predict_next_hour_value(minute_values: List[float]) -> dict:
    """
    根据当前小时的分钟数据，外推预测下一小时均值。

    策略：
      1. 先用 predict_hour_value 得到当前小时均值估算
      2. 利用数据的线性趋势率（trend_rate）推算下一小时
      3. 数据点越少 / 趋势越不稳定，下一小时置信度越低

    Returns:
        dict: {
            'predicted': 下一小时预测值,
            'confidence': 置信度 (0-1),
            'trend': 趋势方向,
            'trend_rate': 趋势变化率,
            'data_points': 数据点数量,
            'data_completeness': 当前小时数据完整度,
            'basis': '当前小时均值的预测依据'
        }
    """
    cur = predict_hour_value(minute_values, method='trend', with_trend=True)
    cur_predicted = cur.get('predicted')

    if cur_predicted is None:
        return {
            'predicted': None, 'confidence': 0,
            'trend': 'stable', 'trend_rate': 0,
            'data_points': cur['data_points'],
            'data_completeness': cur['data_completeness'],
            'basis': None
        }

    trend = cur.get('trend', 'stable')
    trend_rate = cur.get('trend_rate', 0)      # 单位：%
    confidence_cur = cur.get('confidence', 0)

    # 外推：将本小时末均值按当前趋势率推算下一小时
    # 适度衰减趋势（下一小时趋势不会与本小时完全相同）
    decay = 0.6   # 趋势保持系数
    next_predicted = cur_predicted * (1 + trend_rate / 100 * decay)
    next_predicted = max(0, next_predicted)   # 物理量不能为负

    # 下一小时置信度 = 当前置信度 × 衰减系数（预测更远，不确定性更大）
    confidence_next = round(confidence_cur * 0.7, 2)

    return {
        'predicted': round(next_predicted, 4),
        'confidence': confidence_next,
        'trend': trend,
        'trend_rate': round(trend_rate * decay, 2),
        'data_points': cur['data_points'],
        'data_completeness': cur['data_completeness'],
        'basis': round(cur_predicted, 4)
    }


def predict_future_hours(minute_values: List[float], horizon: int = 3,
                          intervention_params: dict = None,
                          threshold: float = None) -> List[dict]:
    """
    根据当前小时内分钟数据，预测当前小时及未来 horizon 个小时的均值序列。

    Args:
        minute_values:      当前小时的分钟数据列表
        horizon:            预测未来的小时数（默认3，即+1h/+2h/+3h）
        intervention_params: 干预参数字典（来自干预状态机）。
                            若为None，则使用旧逻辑（already_warned=False）。
        threshold:          预警阈值。用于计算预测值的合理上限。
                            超标后预测值不应无限增长，上限为阈值×1.5。
                            若为None，则使用当前均值的1.8倍作为上限。

                            典型结构：
                            {
                                "state": 状态字符串,
                                "intervention_intensity": "none"/"weak"/"moderate"/"strong"/"shutdown"/"pending",
                                "fallback_multipliers": {1: float, 2: float, 3: float},
                                "response_delay_minutes": int,
                                "confidence_boost": float,
                                "reason": str
                            }

    Returns:
        list of dict，共 horizon+1 条（索引0=当前小时，1=+1h，…，horizon=+Nh）:
        每条包含:
          'hour_offset':       0/1/2/3  (相对当前小时的偏移)
          'label':             "当前小时" / "+1小时" / "+2小时" / "+3小时"
          'predicted':         预测均值（float 或 None）
          'confidence':        置信度 0-1
          'trend':             'up'/'down'/'stable'
          'trend_rate':        趋势变化率（%），已施加衰减
          'data_points':       数据点数
          'data_completeness': 数据完整度
          'intervention_info': 干预信息（可选，用于调试）
    """
    if horizon < 1:
        horizon = 1

    results = []

    # ── 第0条：当前小时预测 ───────────────────────────────────────────────
    cur = predict_hour_value(minute_values, method='trend', with_trend=True)
    cur_pred = cur.get('predicted')
    results.append({
        'hour_offset':       0,
        'label':             '当前小时',
        'predicted':         cur_pred,
        'confidence':        cur.get('confidence', 0),
        'trend':             cur.get('trend', 'stable'),
        'trend_rate':        cur.get('trend_rate', 0),
        'data_points':       cur.get('data_points', 0),
        'data_completeness': cur.get('data_completeness', 0),
    })

    if cur_pred is None:
        # 无法预测当前小时，后续也无法外推
        for i in range(1, horizon + 1):
            results.append({
                'hour_offset':       i,
                'label':             f'+{i}小时',
                'predicted':         None,
                'confidence':        0,
                'trend':             'stable',
                'trend_rate':        0,
                'data_points':       0,
                'data_completeness': 0,
            })
        return results

    # ── 逐步外推 +1h / +2h / … ──────────────────────────────────────────
    # 趋势衰减：每向后一步衰减 0.5（指数衰减，比之前的0.6更保守）
    # 置信度衰减：每步 × 0.65（加速衰减）
    # 外推锚定：始终以 cur_pred（当前小时预测均值）为基数，而非上一步结果，
    #           避免误差链式叠加。只计算"趋势贡献量"，不重复乘以趋势。
    trend_rate_base = cur.get('trend_rate', 0)   # %
    confidence_base = cur.get('confidence', 0)
    trend_dir = cur.get('trend', 'stable')

    # 预测值绝对上限：考虑阈值的合理上限
    # 原则：超标后不会无限上涨，应有运维干预
    # - 如果当前值超标（>阈值）：上限 = 阈值 × 1.5（合理最大值）
    # - 如果当前值未超标：上限 = max(当前均值 × 1.8, 阈值 × 1.5)
    if threshold and threshold > 0:
        if cur_pred > threshold:
            # 已超标：预测上限 = 阈值 × 1.5（最大不会超过1.5倍阈值）
            pred_ceiling = threshold * 1.5
        else:
            # 未超标：取当前均值×1.8 和 阈值×1.2 中的较大值
            pred_ceiling = max(cur_pred * 1.8, threshold * 1.2)
    else:
        # 无阈值信息：使用当前均值的1.8倍作为宽松上限
        pred_ceiling = cur_pred * 1.8

    # ── 干预模式（干预状态机参数）────────────────────────────────────────
    use_intervention = intervention_params is not None
    if use_intervention:
        intensity = intervention_params.get("intervention_intensity", "none")
        multipliers = intervention_params.get("fallback_multipliers", {1: 1.0, 2: 1.0, 3: 1.0})
        conf_boost = intervention_params.get("confidence_boost", 0)
        reason = intervention_params.get("reason", "")
        response_delay = intervention_params.get("response_delay_minutes", 0)
    else:
        # 旧逻辑兼容：没有干预参数时，使用无干预模式
        intensity = "none"
        multipliers = {1: 1.0, 2: 1.0, 3: 1.0}
        conf_boost = 0
        reason = ""
        response_delay = 0

    # 需要干预回落的状态列表
    intervention_active_states = {"weak", "moderate", "strong", "shutdown", "pending"}

    for i in range(1, horizon + 1):
        this_confidence = round(confidence_base * (0.65 ** i) + conf_boost, 2)
        this_confidence = max(0.05, min(1.0, this_confidence))  # 置信度范围限制

        if use_intervention and intensity in intervention_active_states:
            # ── 干预模式：使用状态机提供的回落系数 ─────────────────────────
            mult = multipliers.get(i, multipliers.get(max(multipliers.keys()), 0.65))
            this_pred = cur_pred * mult
            this_pred = max(0.0, this_pred)
            this_pred = min(this_pred, pred_ceiling)  # 仍有上限保护
            this_pred = round(this_pred, 4)

            results.append({
                'hour_offset':       i,
                'label':             f'+{i}小时',
                'predicted':         this_pred,
                'confidence':        this_confidence,
                'trend':             'down',
                'trend_rate':        round((mult - 1) * 100, 2),
                'data_points':       cur.get('data_points', 0),
                'data_completeness': cur.get('data_completeness', 0),
                'intervention_info': {
                    'intensity': intensity,
                    'reason': reason,
                    'response_delay_min': response_delay,
                    'multiplier': mult
                }
            })
        elif use_intervention and intensity == "warning":
            # ── 预警模式：仍轻微上升但无干预迹象 ────────────────────────────
            mult = multipliers.get(i, 1.0)
            this_pred = cur_pred * mult
            this_pred = max(0.0, this_pred)
            this_pred = min(this_pred, pred_ceiling)
            this_pred = round(this_pred, 4)

            results.append({
                'hour_offset':       i,
                'label':             f'+{i}小时',
                'predicted':         this_pred,
                'confidence':        this_confidence,
                'trend':             'up',
                'trend_rate':        round((mult - 1) * 100, 2),
                'data_points':       cur.get('data_points', 0),
                'data_completeness': cur.get('data_completeness', 0),
                'intervention_info': {
                    'intensity': 'warning',
                    'reason': reason,
                    'response_delay_min': response_delay,
                    'multiplier': mult
                }
            })
        else:
            # ── 常规模式（无干预）───────────────────────────────────────────
            decay_factor = 0.5 ** i
            this_trend_rate = round(trend_rate_base * decay_factor, 2)
            this_confidence_raw = round(confidence_base * (0.65 ** i), 2)

            # 锚定 cur_pred：只叠加趋势贡献量，不重复乘
            trend_contribution = cur_pred * (trend_rate_base / 100 * decay_factor)
            this_pred = cur_pred + trend_contribution
            this_pred = max(0.0, this_pred)
            this_pred = min(this_pred, pred_ceiling)
            this_pred = round(this_pred, 4)

            results.append({
                'hour_offset':       i,
                'label':             f'+{i}小时',
                'predicted':         this_pred,
                'confidence':        this_confidence_raw,
                'trend':             trend_dir,
                'trend_rate':        this_trend_rate,
                'data_points':       cur.get('data_points', 0),
                'data_completeness': cur.get('data_completeness', 0),
            })

    return results


def predict_day_average(hour_values: List[float], current_hour: int = None, with_trend: bool = True) -> dict:
    """
    根据当日已有小时数据预测当日均值
    
    Args:
        hour_values: 小时均值列表（按时间顺序）
        current_hour: 当前小时数（0-23），用于调整预测
        with_trend: 是否分析数据趋势
    
    Returns:
        dict: {
            'predicted': 预测值,
            'confidence': 置信度 (0-1),
            'trend': 趋势 ('up', 'down', 'stable'),
            'trend_rate': 趋势变化率,
            'data_points': 数据点数量,
            'data_completeness': 数据完整度 (0-1),
            'method': 使用的预测方法
        }
    """
    from datetime import datetime
    
    if not hour_values:
        return {'predicted': None, 'confidence': 0, 'trend': 'stable', 'trend_rate': 0, 'data_points': 0, 'data_completeness': 0, 'method': 'none'}
    
    vals = [v for v in hour_values if v is not None]
    if not vals:
        return {'predicted': None, 'confidence': 0, 'trend': 'stable', 'trend_rate': 0, 'data_points': 0, 'data_completeness': 0, 'method': 'none'}
    
    n = len(vals)
    predicted = None
    method_used = 'simple'
    
    # 如果没有提供当前小时，使用当前时间
    if current_hour is None:
        current_hour = datetime.now().hour
    
    # 根据数据完整度选择预测方法
    if n >= 12:
        # 数据较多（>=12小时），使用加权平均，更关注近期趋势
        # 使用指数递减权重
        weights = [math.exp(0.1 * i) for i in range(n)]
        weights.reverse()  # 最近的数据权重最高
        weighted_sum = sum(v * w for v, w in zip(vals, weights))
        predicted = weighted_sum / sum(weights)
        method_used = 'weighted_trend'
        
    elif n >= 6:
        # 中等数据量（6-11小时），使用简单平均+趋势调整
        base_avg = statistics.mean(vals)
        
        # 计算趋势（最近3小时 vs 前3小时）
        if n >= 6:
            recent_avg = sum(vals[-3:]) / 3
            earlier_avg = sum(vals[-6:-3]) / 3
            trend_factor = (recent_avg / earlier_avg) if earlier_avg != 0 else 1
            # 趋势调整系数（限制在0.8-1.2之间）
            trend_factor = max(0.8, min(1.2, trend_factor))
            predicted = base_avg * trend_factor
        else:
            predicted = base_avg
        
        method_used = 'trend_adjusted'
        
    else:
        # 数据较少（<6小时），使用简单平均
        predicted = statistics.mean(vals)
        method_used = 'simple'
    
    # 计算置信度
    # 数据完整度：假设全天24小时
    data_completeness = min(1.0, n / 24)
    
    # 数据稳定性
    if n >= 2:
        std_dev = statistics.stdev(vals)
        cv = (std_dev / abs(predicted)) if predicted != 0 else float('inf')
        stability_score = max(0, 1 - cv * 1.5)
    else:
        stability_score = 0.3
    
    # 时间因素：越接近24小时，置信度越高
    time_factor = 0.5 + 0.5 * (n / 24)
    
    # 置信度 = 数据完整度 * 0.4 + 稳定性 * 0.3 + 时间因素 * 0.3
    confidence = data_completeness * 0.4 + stability_score * 0.3 + time_factor * 0.3
    confidence = max(0, min(1, confidence))
    
    # 分析趋势：使用线性回归斜率（与 predict_hour_value 保持一致）
    trend = 'stable'
    trend_rate = 0

    if with_trend and n >= 4:
        slope_pct, r2 = _linear_regression_slope(vals)
        if slope_pct is not None:
            # R² < 0.3 → 趋势不显著，视为平稳
            if r2 >= 0.3:
                if slope_pct > 2.0:
                    trend = 'up'
                    trend_rate = slope_pct
                elif slope_pct < -2.0:
                    trend = 'down'
                    trend_rate = slope_pct
        # 趋势率限幅
        trend_rate = max(-25.0, min(25.0, trend_rate))

    return {
        'predicted': predicted,
        'confidence': round(confidence, 2),
        'trend': trend,
        'trend_rate': round(trend_rate, 2),
        'data_points': n,
        'data_completeness': round(data_completeness, 2),
        'method': method_used
    }


def check_threshold(value: float, param_name: str, thresholds: dict) -> bool:
    """检查是否超过预警阈值"""
    if param_name not in thresholds:
        return False
    threshold = thresholds[param_name]
    if threshold is None:
        return False
    return value > threshold


def get_warning_level(value: float, param_name: str, thresholds: dict) -> str:
    """
    获取预警等级（正常/黄色/橙色/红色）

    thresholds格式支持：
    - 单个浮点数：只有上限检测
    - (lower, upper) 元组：下限+上限检测
      lower=None 表示无下限；upper=None 表示无上限
    """
    if param_name not in thresholds:
        return "正常"

    threshold = thresholds[param_name]
    if threshold is None:
        return "正常"

    # ── 解析阈值格式 ────────────────────────────────────────────────────
    if isinstance(threshold, tuple):
        lower_bound, upper_bound = threshold
    else:
        # 兼容旧格式：单个浮点数 = 只有上限
        lower_bound, upper_bound = None, threshold

    if upper_bound is None and lower_bound is None:
        return "正常"

    # ── 计算偏离程度，确定预警等级 ──────────────────────────────────────
    # 三等级：超过阈值<110%为黄色，110%-120%为橙色，>120%为红色

    def _calc_level(abs_deviation: float, base: float) -> str:
        """基于偏离量和基准值计算预警等级"""
        if base <= 0:
            return "正常"
        pct = abs_deviation / base
        if pct < 0.10:
            return "正常"
        elif pct < 0.20:
            return "黄色预警"
        elif pct < 0.30:
            return "橙色预警"
        else:
            return "红色预警"

    max_level = "正常"

    # ── 上限检测 ────────────────────────────────────────────────────────
    if upper_bound is not None and value > upper_bound:
        deviation = value - upper_bound
        lvl = _calc_level(deviation, upper_bound)
        lvl_order = {"正常": 0, "黄色预警": 1, "橙色预警": 2, "红色预警": 3}
        if lvl_order.get(lvl, 0) > lvl_order.get(max_level, 0):
            max_level = lvl

    # ── 下限检测 ────────────────────────────────────────────────────────
    if lower_bound is not None and value < lower_bound:
        deviation = lower_bound - value
        lvl = _calc_level(deviation, lower_bound)
        lvl_order = {"正常": 0, "黄色预警": 1, "橙色预警": 2, "红色预警": 3}
        if lvl_order.get(lvl, 0) > lvl_order.get(max_level, 0):
            max_level = lvl

    return max_level


def get_display_params_for_sub(sub_type: str) -> List[str]:
    """根据排放口类型获取应显示的参数列表"""
    if is_water_sub(sub_type):
        return WATER_PARAMS_DISPLAY
    elif is_vocs_sub(sub_type):
        # VOCs 排口（涂装/有机废气）：显示非甲烷总烃，不显示 SO₂/NOx/颗粒物
        return VOCS_PARAMS_DISPLAY
    elif is_gas_sub(sub_type):
        # 普通废气排口（锅炉/燃烧）：显示 SO₂/NOx/颗粒物，不显示非甲烷总烃
        return GAS_PARAMS_DISPLAY
    return []


def filter_params_for_display(params: List[dict], sub_type: str) -> List[dict]:
    """过滤参数，只保留对应类型的显示参数"""
    display_list = get_display_params_for_sub(sub_type)
    if not display_list:
        return params
    result = []
    for p in params:
        pname = p.get('name', '')
        # 模糊匹配（参数名可能包含单位）
        for dname in display_list:
            if dname in pname or pname in dname:
                result.append(p)
                break
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 干预状态机：解决"当前超标=已干预"误判问题
# 状态流转：NORMAL → WARNING → INTERVENTION_PENDING → INTERVENTION_ACTIVE → RECOVERING → NORMAL
# ─────────────────────────────────────────────────────────────────────────────

class InterventionStateMachine:
    """
    干预状态机：根据历史数据变化趋势自动识别干预状态和强度，
    替代简单的"当前超标=已干预"判断。

    核心改进：
    1. 干预时机判定：基于最近5分钟趋势，不是当前绝对值
    2. 干预强度识别：根据下降速率自动分类（停产/限产/弱干预）
    3. 响应延迟模拟：干预效果有10-30分钟延迟
    """

    # 状态枚举
    STATE_NORMAL = "NORMAL"              # 正常
    STATE_WARNING = "WARNING"            # 触发预警（待干预）
    STATE_INTERVENTION_PENDING = "PENDING"   # 预警已触发，等待干预生效（缓冲期30分钟）
    STATE_INTERVENTION_ACTIVE = "ACTIVE" # 干预已生效（观察到明显下降）
    STATE_RECOVERING = "RECOVERING"      # 恢复中（接近阈值或持续下降）

    def __init__(self):
        # 状态记录：{(subname, param): {"state": str, "last_update": timestamp, "trend_history": []}}
        self._states: Dict[tuple, dict] = {}
        self._max_history = 200  # 最多记录200个监测点

    def update(self, subname: str, param: str, cur_value: float,
               threshold: float, current_time: float = None) -> dict:
        """
        更新状态机，返回当前状态和预测参数。

        Args:
            subname: 排放口名称
            param: 参数名称
            cur_value: 当前值
            threshold: 预警阈值
            current_time: 当前时间戳（秒），默认用time.time()

        Returns:
            dict: {
                "state": 当前状态,
                "intervention_intensity": 干预强度("none"/"weak"/"moderate"/"strong"/"shutdown"),
                "fallback_multipliers": {1: float, 2: float, 3: float},  # 干预后回落系数
                "response_delay_minutes": 干预响应延迟（分钟）,
                "confidence_boost": 置信度提升（0-0.2）,  # 有历史干预数据时提升置信度
                "reason": 状态判定原因
            }
        """
        import time
        if current_time is None:
            current_time = time.time()

        key = (subname, param)
        now_state = self._states.get(key, {})

        # ── 初始化状态历史 ──────────────────────────────────────────────────
        if "trend_history" not in now_state:
            now_state["trend_history"] = []
        if "state" not in now_state:
            now_state["state"] = self.STATE_NORMAL
        if "last_update" not in now_state:
            now_state["last_update"] = current_time

        trend_history = now_state["trend_history"]

        # 记录当前值到历史（保留最近20个点）
        trend_history.append({
            "time": current_time,
            "value": cur_value,
            "threshold": threshold
        })
        if len(trend_history) > 20:
            trend_history = trend_history[-20:]
        now_state["trend_history"] = trend_history

        # ── 计算最近N分钟的变化趋势 ─────────────────────────────────────────
        if len(trend_history) >= 3:
            recent = trend_history[-3:]  # 最近3个点（约3分钟）
            oldest_val = recent[0]["value"]
            newest_val = recent[-1]["value"]
            time_span = recent[-1]["time"] - recent[0]["time"]

            if time_span > 0 and oldest_val > 0:
                # 每分钟变化率 %
                min_change_rate = (newest_val - oldest_val) / oldest_val / (time_span / 60) * 100
            else:
                min_change_rate = 0
        else:
            min_change_rate = 0

        # ── 计算超阈值幅度 ────────────────────────────────────────────────
        exceed_ratio = (cur_value / threshold - 1) * 100 if threshold > 0 else 0

        # ── 状态流转逻辑 ────────────────────────────────────────────────────
        prev_state = now_state["state"]
        new_state = prev_state

        if exceed_ratio > 0:
            # 正在超标
            if min_change_rate < -3:
                # 快速下降 → 干预已生效
                new_state = self.STATE_INTERVENTION_ACTIVE
            elif min_change_rate > 2 and exceed_ratio > 15:
                # 仍在上升且超标严重 → 干预可能无效或未干预
                new_state = self.STATE_WARNING
            elif min_change_rate > 0 and exceed_ratio > 5:
                # 轻微上升或平稳，超标 → 等待干预
                new_state = self.STATE_INTERVENTION_PENDING
            elif exceed_ratio < 10:
                # 超标轻微（<10%）→ 黄色预警待干预
                new_state = self.STATE_INTERVENTION_PENDING
        else:
            # 未超标
            if prev_state in (self.STATE_INTERVENTION_ACTIVE, self.STATE_INTERVENTION_PENDING):
                new_state = self.STATE_RECOVERING
            else:
                new_state = self.STATE_NORMAL

        # 状态更新（带防抖：需连续2次才切换）
        if new_state != prev_state:
            if now_state.get("_pending_state") == new_state:
                # 确认状态切换
                now_state["state"] = new_state
                now_state["_pending_state"] = None
                now_state["last_update"] = current_time
            else:
                # 记录待确认状态
                now_state["_pending_state"] = new_state
        else:
            now_state["_pending_state"] = None

        self._states[key] = now_state

        # ── 计算干预强度和回落系数 ─────────────────────────────────────────
        return self._compute_intervention_params(
            subname, param, min_change_rate, exceed_ratio, prev_state, new_state
        )

    def _compute_intervention_params(self, subname: str, param: str,
                                     min_change_rate: float, exceed_ratio: float,
                                     prev_state: str, new_state: str) -> dict:
        """
        根据状态和趋势计算干预参数。
        """
        # 干预强度分类
        if new_state == self.STATE_NORMAL:
            intensity = "none"
            multipliers = {1: 1.0, 2: 1.0, 3: 1.0}
            response_delay = 0
            confidence_boost = 0
            reason = "当前未超标，使用常规预测"

        elif new_state == self.STATE_WARNING:
            # 预警触发但无干预迹象
            intensity = "none"
            multipliers = {1: 1.05, 2: 1.10, 3: 1.15}  # 继续轻微上升
            response_delay = 0
            confidence_boost = 0
            reason = "预警触发但未见干预效果，预计继续上升"

        elif new_state == self.STATE_INTERVENTION_PENDING:
            # 已预警，等待干预生效（缓冲期）
            intensity = "pending"
            # 假设干预需要15分钟生效，前15分钟仍轻微上升
            multipliers = {1: 1.02, 2: 0.95, 3: 0.88}  # +1h趋稳，+2h开始下降
            response_delay = 15
            confidence_boost = 0.05
            reason = "预警已触发，预计15分钟后干预生效"

        elif new_state == self.STATE_INTERVENTION_ACTIVE:
            # 干预已生效，观察到下降趋势
            if min_change_rate < -10:
                # 快速下降（>10%/min）→ 停产或大幅限产
                intensity = "shutdown"
                multipliers = {1: 0.55, 2: 0.30, 3: 0.15}
                response_delay = 5
                confidence_boost = 0.15
                reason = "检测到快速下降，干预强度：停产/大幅限产"
            elif min_change_rate < -5:
                # 中速下降（5-10%/min）→ 限产50%左右
                intensity = "strong"
                multipliers = {1: 0.70, 2: 0.50, 3: 0.35}
                response_delay = 10
                confidence_boost = 0.12
                reason = "检测到中速下降，干预强度：限产50%"
            elif min_change_rate < -2:
                # 慢速下降（2-5%/min）→ 限产30%左右
                intensity = "moderate"
                multipliers = {1: 0.85, 2: 0.72, 3: 0.60}
                response_delay = 15
                confidence_boost = 0.10
                reason = "检测到慢速下降，干预强度：限产30%"
            else:
                # 微弱下降 → 干预力度不足
                intensity = "weak"
                multipliers = {1: 0.92, 2: 0.85, 3: 0.78}
                response_delay = 20
                confidence_boost = 0.05
                reason = "下降缓慢，干预力度可能不足"

        elif new_state == self.STATE_RECOVERING:
            # 恢复中，值已回到阈值以下或持续下降
            if exceed_ratio < -10:
                # 远低于阈值 → 恢复正常
                intensity = "none"
                multipliers = {1: 0.98, 2: 0.96, 3: 0.94}
                response_delay = 0
                confidence_boost = 0.10
                reason = "值已显著低于阈值，预测趋于平稳"
            else:
                # 接近阈值 → 缓慢恢复
                intensity = "weak"
                multipliers = {1: 0.95, 2: 0.90, 3: 0.85}
                response_delay = 10
                confidence_boost = 0.08
                reason = "正在恢复，预测缓慢下降"
        else:
            intensity = "none"
            multipliers = {1: 1.0, 2: 1.0, 3: 1.0}
            response_delay = 0
            confidence_boost = 0
            reason = "未知状态，使用默认预测"

        return {
            "state": new_state,
            "intervention_intensity": intensity,
            "fallback_multipliers": multipliers,
            "response_delay_minutes": response_delay,
            "confidence_boost": confidence_boost,
            "reason": reason,
            "trend_rate_per_min": round(min_change_rate, 2),
            "exceed_ratio": round(exceed_ratio, 2)
        }

    def get_state(self, subname: str, param: str) -> Optional[dict]:
        """获取指定排放口+参数的当前状态"""
        return self._states.get((subname, param))

    def reset_state(self, subname: str, param: str):
        """重置指定排放口+参数的状态"""
        key = (subname, param)
        if key in self._states:
            del self._states[key]


# 全局单例（避免重复创建）
_global_intervention_sm: Optional[InterventionStateMachine] = None

def get_intervention_state_machine() -> InterventionStateMachine:
    """获取全局干预状态机实例"""
    global _global_intervention_sm
    if _global_intervention_sm is None:
        _global_intervention_sm = InterventionStateMachine()
    return _global_intervention_sm
