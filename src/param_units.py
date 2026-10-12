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
  废气:  排放量(kg) = 实测浓度(mg/m³) × 期间累计流量(m³) / 1e6
  废水:  排放量(kg) = 实测浓度(mg/L)  × 期间累计流量(m³) / 1000

推导：
  mg/m³ × m³ = mg   -> /1e6 -> kg
  mg/L  × m³ = g    -> /1e3 -> kg

**重要口径（v5.51 实证确认，勿再改回）**：
  1. 浓度取**实测值** val_{code}，**不是折算值** cvt_{code}。
     网页端实证（2026-10-13 截图，顶层流量 127021 m³）：
       SO2 实测 13.7 × 127021/1e6 = 1.740  -> 网页 1.74   ✓
       SO2 折算 14.5 × 127021/1e6 = 1.842  -> 网页 1.84   ✗
       NOx 实测 6.82 × 127021/1e6 = 0.866  -> 网页 0.866  ✓
       NOx 折算 7.17 × 127021/1e6 = 0.911  -> 网页 0.911  ✗
     热电厂虽同时上报实测/折算，但排放量统计只用实测。
  2. 流量取**期间累计量** val_{flow}（日累计 127021 m³、小时累计约 13 万 m³），
     故结果是期间排放**质量(kg)**，不是速率；小时粒度下累计量与流量率
     数值相同，无需再按 24h 折算。
  3. 服务端可能直接返回排放量字段（网页有「排放量(kg)」列），
     故优先 extract_emission_mass() 读取，取不到再按上式计算。

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
    '209': '%',        # 烟气含氧量（服务端名「氧气」）
    '210': 'm³',       # 烟气流量（服务端名「流量」，单位 m³=期间累计量）
    '211': 'm/s',      # 流速
    '220': 'mg/m³',    # 碳氢化合物总烃
    '299': 'mg/m³',    # 甲烷
    '383': 'mg/m³',    # 非甲烷总烃
    '525': '℃',        # 烟气温度
    '526': 'kPa',      # 烟气压力（服务端名「千帕」）
    '527': '%',        # 烟气湿度
    # 字符串 code（部分企业）
    'SO2': 'mg/m³',
    'NOx': 'mg/m³',
    'PM': 'mg/m³',

    # ── 废水（subtype=51）──────────────────────────────────────────────
    '301': '℃',        # 水温
    '302': '无量纲',   # pH值（服务端名「PH」）
    '311': 'mg/L',     # 氨氮
    '316': 'mg/L',     # 化学需氧量
    '492': 'm³',       # 废水流量（期间累计量）
    '494': 'm³',       # 流量（服务端单位 m³，非 m³/h）
    '495': 'm³',       # 累计流量
}

# ── 浓度类参数的换算分母（浓度 -> 排放量）───────────────────────────────────
# 单位 -> 分母：浓度 × 期间累计流量 / 分母 = kg
# 注：v5.49 曾按「瞬时流量」口径标为 kg/h；经与网页端核对（2026-10-13），
# 网页「排放量(kg)」列用的是**期间累计流量**（如日累计 127021 m³），
# 故正确单位为 kg（期间质量），公式与数值 4/4 精确匹配网页显示。
_CONCENTRATION_DIVISOR: Dict[str, float] = {
    'mg/m³': 1e6,
    'mg/L': 1e3,
}

# ── 流量参数（排放量计算的乘数来源）─────────────────────────────────────────
# 废气流量 / 废水流量。服务端单位标为 m³（**期间累计量**），
# 与网页端排放量统计口径一致（非瞬时 m³/h）。
FLOW_CODES: frozenset = frozenset({'210', '492', '494'})

# 排放量单位（期间质量）
EMISSION_UNIT = 'kg'

# ── 服务端排放量字段候选名 ──────────────────────────────────────────────────
# 网页端表格有「排放量(kg)」列，说明服务端**可能**直接返回该值。
# 接口文档未记录字段名（仅提到顶层 pf_flow），故按可能性排序枚举候选，
# 命中即采用服务端权威值，未命中则回退到客户端计算。
EMISSION_FIELD_CANDIDATES: tuple = (
    'pf_{code}',      # 与顶层 pf_flow 同前缀，最可能
    'pfl_{code}',
    'flow_{code}',
    'emission_{code}',
    'pf{code}',
)


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
    计算期间排放量（kg）。

    公式：排放量(kg) = 浓度 × 期间累计流量 / 分母
      废气（mg/m³ × m³）：/1e6
      废水（mg/L  × m³）：/1e3

    与网页端口径一致：网页「排放量(kg)」列用期间累计流量，
    实测 4/4 匹配（SO2 13.7×127021/1e6=1.74 kg 等）。

    注：v5.49 曾按瞬时流量口径命名/标注为 kg/h，v5.50 修正为 kg。
    函数名保留 ``calc_emission_rate`` 以兼容既有调用方。

    Args:
        concentration: 浓度值（实测或折算）
        flow:          期间累计流量（m³）
        code:          浓度参数的 code（决定换算分母）

    Returns:
        排放量 kg；任一输入无效或该参数不可计算时返回 None。
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


# 语义化别名：明确表示「期间排放质量(kg)」
calc_emission_mass = calc_emission_rate


def extract_emission_mass(row: dict, code) -> Optional[float]:
    """
    从服务端行数据中读取排放量（kg）——服务端权威值优先。

    网页端表格含「排放量(kg)」列，说明服务端**可能**直接返回该字段。
    接口文档未记录字段名，故按 EMISSION_FIELD_CANDIDATES 枚举候选，
    命中且值有效则返回；否则返回 None（调用方回退到计算值）。

    Args:
        row:  服务端返回的一行数据（dict）
        code: 参数代码

    Returns:
        排放量 kg；未找到字段或值无效时返回 None。
    """
    if not isinstance(row, dict):
        return None
    c = normalize_code(code)
    if not c:
        return None
    for pattern in EMISSION_FIELD_CANDIDATES:
        key = pattern.format(code=c)
        if key not in row:
            continue
        v = row.get(key)
        if v in (None, '', '--', '/'):
            continue
        try:
            fv = float(v)
        except (ValueError, TypeError):
            continue
        if fv != fv:              # NaN
            continue
        return fv
    return None


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
    'EMISSION_FIELD_CANDIDATES',
    'normalize_code',
    'get_param_unit',
    'is_concentration_param',
    'get_concentration_divisor',
    'calc_emission_rate',
    'calc_emission_mass',
    'extract_emission_mass',
    'find_flow_code',
    'format_emission_rate',
]
