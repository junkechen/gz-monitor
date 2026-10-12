# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 监测参数单位表与排放量计算

背景
----
服务端接口（实时/历史/分钟）只返回**浓度类**字段：
  val_{code}=实测浓度、cvt_{code}=折算浓度、standard_{code}=标准值
并没有"排放量"字段，也不返回参数单位。

因此需要客户端补两件事：
  1. **排放单位**：每个参数的计量单位（mg/m³、mg/L、%…）。
  2. **排放量**：由 浓度 × 流量 计算得出（环保行业通用算法）。

排放量计算公式
-------------
  废气:  排放量(kg/h) = 浓度(mg/m³) × 烟气流量(m³/h) / 1e6
  废水:  排放量(kg/h) = 浓度(mg/L)  × 废水流量(m³/h) / 1000

推导：
  mg/m³ × m³/h = mg/h      -> /1e6 -> kg/h
  mg/L  × m³/h = g/h       -> /1e3 -> kg/h

只有"浓度类"参数（单位为 mg/m³ 或 mg/L）才可计算排放量；
pH、温度、压力、流速、含氧量、湿度、流量本身 均不可计算。
"""

from typing import Dict, Optional, Tuple


# ── 参数单位表（code -> 单位）─────────────────────────────────────────────────
# 来源：docs/数据接口文档.md 2.5 节，并覆盖 data_processor.CODE_TO_NAME 的
# 全部 key（含 SO2/NOx/PM 等字符串 code，保证不出现"无单位"）。
PARAM_UNITS: Dict[str, str] = {
    # ── 废气（VOCs，subtype=64）────────────────────────────────────────
    '201': 'mg/m³',    # 非甲烷总烃（代码映射）/ 二氧化硫（按企业而异）
    '203': 'mg/m³',    # 二氧化硫 / 氮氧化物
    '207': 'mg/m³',    # 氮氧化物 / 颗粒物
    '209': '%',        # 烟气含氧量
    '210': 'm³/h',     # 烟气流量
    '211': 'm/s',      # 流速
    '220': 'mg/m³',    # 碳氢化合物总烃
    '299': 'mg/m³',    # 甲烷
    '383': 'mg/m³',    # 非甲烷总烃
    '525': '℃',        # 烟气温度
    '526': 'kPa',      # 烟气压力
    '527': '%',        # 烟气湿度
    # 字符串 code（部分企业）
    'SO2': 'mg/m³',
    'NOx': 'mg/m³',
    'PM': 'mg/m³',

    # ── 废水（subtype=51）──────────────────────────────────────────────
    '301': '℃',        # 水温
    '302': '无量纲',   # pH值
    '311': 'mg/L',     # 氨氮
    '316': 'mg/L',     # 化学需氧量
    '492': 'm³/h',     # 废水流量
    '494': 'm³/h',     # 流量
    '495': 'm³',       # 累计流量
}

# ── 浓度类参数的换算分母（浓度 -> 排放量）───────────────────────────────────
# 单位 -> 分母：浓度 × 流量 / 分母 = kg/h
_CONCENTRATION_DIVISOR: Dict[str, float] = {
    'mg/m³': 1e6,
    'mg/L': 1e3,
}

# ── 流量参数（排放量计算的乘数来源）─────────────────────────────────────────
# 废气流量 / 废水流量；累计流量(495)是累计值，不能用作瞬时流量
FLOW_CODES: frozenset = frozenset({'210', '492', '494'})

# 排放量单位
EMISSION_UNIT = 'kg/h'


def normalize_code(code) -> str:
    """把排口参数 code 统一成纯数字字符串（兼容 '210'、210、210.0）。"""
    if code is None:
        return ''
    try:
        return str(int(float(code)))
    except (ValueError, TypeError):
        return str(code).strip()


def get_param_unit(code) -> str:
    """
    获取参数单位。未登记的 code 返回空串（调用方应显示 '--'）。

    Args:
        code: 参数代码（可为 int/float/str）

    Returns:
        单位字符串；未知参数返回 ''
    """
    return PARAM_UNITS.get(normalize_code(code), '')


def is_concentration_param(code) -> bool:
    """是否为浓度类参数（可据以计算排放量）。"""
    unit = PARAM_UNITS.get(normalize_code(code), '')
    return unit in _CONCENTRATION_DIVISOR


def get_concentration_divisor(code) -> Optional[float]:
    """浓度类参数换算为 kg/h 的分母；非浓度参数返回 None。"""
    unit = PARAM_UNITS.get(normalize_code(code), '')
    return _CONCENTRATION_DIVISOR.get(unit)


def calc_emission_rate(concentration, flow, code) -> Optional[float]:
    """
    计算瞬时排放量（kg/h）。

    Args:
        concentration: 浓度值（实测或折算）
        flow:          对应流量值（m³/h）
        code:          浓度参数的 code（决定换算分母）

    Returns:
        排放量 kg/h；任一输入无效或该参数不可计算时返回 None。
    """
    divisor = get_concentration_divisor(code)
    if divisor is None:
        return None
    try:
        c = float(concentration)
        f = float(flow)
    except (ValueError, TypeError):
        return None
    if c != c or f != f:          # NaN 检查
        return None
    return (c * f) / divisor


def find_flow_code(code_list) -> Optional[str]:
    """
    从排口的参数列表中找出用于排放量计算的流量参数 code。

    优先返回废气流量(210)，其次废水流量(492/494)。
    同一排口理论上只有一个流量参数。
    """
    for code in code_list or []:
        if normalize_code(code) == '210':
            return '210'
    for code in code_list or []:
        if normalize_code(code) == '492':
            return '492'
    for code in code_list or []:
        if normalize_code(code) == '494':
            return '494'
    return None


def format_emission_rate(value) -> str:
    """格式化排放量：有效值保留 3 位小数，无效值显示 '--'。"""
    if value is None:
        return '--'
    try:
        v = float(value)
    except (ValueError, TypeError):
        return '--'
    if v != v:                     # NaN
        return '--'
    return f"{v:.3f}"


__all__ = [
    'PARAM_UNITS',
    'FLOW_CODES',
    'EMISSION_UNIT',
    'normalize_code',
    'get_param_unit',
    'is_concentration_param',
    'get_concentration_divisor',
    'calc_emission_rate',
    'find_flow_code',
    'format_emission_rate',
]
