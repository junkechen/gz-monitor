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

**v5.82 补充：两套数据源的「流量」含义不同，勿混用（4 份冠洲导出实测）**：
  A. 服务端 API（实时/历史/分钟）：流量为 m³/h（瞬时/平均风量）。
     分钟粒度须传 hours=1/60 折算成该分钟桶体积（v5.80）。
  B. 官网「历史数据」导出 xls：流量(m3) 列的语义**不统一**——
     废气小时值 ≈ m³/h、日值 = 日累计（≈24×小时），
     废水 10 分钟桶却是该桶累计体积（实测 4 m³：
     4.65 mg/L × 4 /1000 = 0.0186 kg ≈ 官网 0.019 kg）。
     因此导入路径**不重算**，直接采用导出文件的「排放量」列
     （web_daily_import.parse_export），只有服务端 API 才用本模块的公式。
  废水口（总排口：COD/氨氮，mg/L）分母 1000；
  废气口（VOCs总排口：非甲烷总烃等，mg/m³）分母 1e6，日导出(t)=kg/1000。

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


def calc_emission_rate(concentration, flow, code, hours: float = 1.0) -> Optional[float]:
    """
    计算期间排放量（kg）。

    公式：排放量(kg) = 浓度 × 流量(m³/h) × 小时数 / 分母
      废气（mg/m³ × m³）：/1e6
      废水（mg/L  × m³）：/1e3

    v5.80：服务端各粒度的「流量(m3)」均为 **m³/h（瞬时/平均流量）**：
      - 小时数据：×1h（数值即该小时累计风量）
      - 日数据：日导出流量为日累计（≈24×小时值），×1 即可
      - **分钟数据：必须 ×1/60**，否则排放量会被高估 60 倍
        （实测官网分钟 00:00：1.81 mg/m³ × 119649 m³/h /60 /1e6 = 0.0036 kg，
        与官网 0.004 kg 一致；不除 60 则为 0.2166 kg）

    与网页端口径一致：网页「排放量(kg)」列用期间累计流量，
    实测 4/4 匹配（SO2 13.7×127021/1e6=1.74 kg 等）。

    注：v5.49 曾按瞬时流量口径命名/标注为 kg/h，v5.50 修正为 kg。
    函数名保留 ``calc_emission_rate`` 以兼容既有调用方。

    Args:
        concentration: 浓度值（实测或折算）
        flow:          流量（m³/h 或该时段累计 m³，见上文）
        code:          浓度参数的 code（决定换算分母）
        hours:         时间系数。分钟数据传 1/60，小时/日数据传 1.0

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
    if hours is None or hours <= 0:
        hours = 1.0
    return (c * f * float(hours)) / divisor


# 语义化别名：明确表示「期间排放质量(kg)」
calc_emission_mass = calc_emission_rate


def extract_emission_mass(row: dict, code, flow_code=None) -> Optional[float]:
    """
    从服务端行数据中读取排放量（kg）——服务端权威值优先。

    网页端表格含「排放量(t)」列（注意导出为吨，1 t = 1000 kg），说明服务端
    **可能**直接返回该字段。接口文档未记录字段名，故按
    EMISSION_FIELD_CANDIDATES 枚举候选，命中且值有效则返回；
    否则返回 None（调用方回退到计算值）。

    v5.77：服务端字段单位不固定（t 或 kg）。传入 flow_code 时，用
    「浓度 × 流量 / 分母」的 kg 值做量级校验：
      - 读数与换算值同量级（比值 0.1~10）→ 视为 kg，原样返回；
      - 读数比换算值小约 1000 倍（比值 1e-4~1e-2）→ 视为吨，×1000。

    Args:
        row:       服务端返回的一行数据（dict）
        code:      参数代码
        flow_code: 流量参数代码（可选，用于单位归一化校验）

    Returns:
        排放量 kg；未找到字段或值无效时返回 None。
    """
    if not isinstance(row, dict):
        return None
    c = normalize_code(code)
    if not c:
        return None
    raw = None
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
        raw = fv
        break
    if raw is None:
        # v5.82：候选字段名全部未命中时用「关键词 + 量级」自动发现。
        # 旧版此处直接 return None，导致 detect_server_emission 永远不可达
        # （它恰好是为「字段名未知」这个场景准备的）。
        return detect_server_emission(row, c, flow_code)

    # v5.77：单位归一化（t → kg）
    if flow_code:
        kg = calc_emission_rate(row.get(f'val_{c}'),
                                row.get(f'val_{normalize_code(flow_code)}'), c)
        if kg is not None and kg > 0:
            ratio = raw / kg
            if 1e-4 <= ratio <= 1e-2:      # 服务端以吨返回
                return raw * 1000.0
    return raw


# v5.82：服务端排放量字段名未知时的"关键词 + 量级"双重校验自动发现。
# 仅当字段名含以下关键词、且数值与公式换算值同量级（0.5~2 倍）时才采纳，
# 避免把标准值(50)、状态值等误当排放量。
_EMISSION_KEY_HINTS = (
    'emis', 'pf_', 'pf{', 'ex_', 'emission', 'pollut',
    'discharg', 'mass', 'output',
)


def detect_server_emission(row: dict, code, flow_code=None) -> Optional[float]:
    """自动发现服务端行内的排放量字段（kg），未命中返回 None。

    官网导出的历史数据每行都带「排放量(kg)」列（由分钟数据积分而来），
    说明服务端确实能给出该值，但接口返回的字段名未知。命中条件：
      1) 字段名含排放量相关关键词；
      2) 数值与「浓度×流量/分母」同量级（0.5~2 倍），否则视为非排放量字段。
    """
    if not isinstance(row, dict):
        return None
    c = normalize_code(code)
    if not c:
        return None
    calc = None
    if flow_code:
        calc = calc_emission_rate(row.get(f'val_{c}'),
                                  row.get(f'val_{normalize_code(flow_code)}'), c)
    for k, v in row.items():
        kl = str(k).lower()
        if not any(h in kl for h in _EMISSION_KEY_HINTS):
            continue
        if kl.startswith('val_') or kl.startswith('state_') or kl.startswith('status_'):
            continue
        try:
            fv = float(v)
        except (ValueError, TypeError):
            continue
        if fv != fv or fv <= 0:
            continue
        if calc and calc > 0:
            # v5.82：放宽到 0.1~10 倍。官网小时排放量按分钟积分得到，
            # 与「小时平均浓度 × 小时流量」可能差数倍（v5.79 实测 11 时
            # 0.902 kg vs 公式 0.1155 kg，7.8 倍），旧的 0.5~2 倍会
            # 把正确的服务端值误杀；50 这类标准值仍会被排除（数百倍）。
            if not (0.1 <= fv / calc <= 10.0):
                continue
        return fv
    return None


def find_flow_code(code_list) -> Optional[str]:
    """
    从排口的参数列表中找出用于排放量计算的流量参数 code。

    优先返回废气流量(210)，其次废水流量(492/494)。
    同一排口理论上只有一个流量参数。

    注意：本函数只看参数列表、不看数据。若同一排口同时登记了 492/494/495
    但只有其中一个有值，请改用 pick_flow_code(rows, code_list)。
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


# 流量参数优先级：期间/瞬时流量优先，累计流量(495)仅在前两者无值时兜底
_FLOW_PRIORITY = ('210', '492', '494', '495')


def pick_flow_code(rows, code_list) -> Optional[str]:
    """
    按**数据可用性**挑选流量参数 code（v5.63）。

    背景：部分排口同时登记了「废水流量(492)」「流量(494)」「累计流量(495)」，
    但服务端只有其中之一有值。旧逻辑固定优先 492，导致 492 为空时排放量
    整列显示 '--'（如总排口的 COD 排放量）。

    规则：
      1. 候选 = code_list 中属于流量类的 code；
      2. 按 210 > 492 > 494 > 495 的优先级（同旧逻辑，仅跳过无值项），取"最近数据行有有效正值"的 code；
      3. 都无有效值时回退静态规则（find_flow_code）。

    Args:
        rows:      数据行列表（升序，允许为空）
        code_list: 排口参数 code 列表

    Returns:
        选中的流量 code；无流量参数时返回 None。
    """
    cands = []
    for code in code_list or []:
        c = normalize_code(code)
        if c in _FLOW_PRIORITY and c not in cands:
            cands.append(c)
    if not cands:
        return None

    checked = 0
    for r in reversed(list(rows or [])):
        if not isinstance(r, dict):
            continue
        checked += 1
        for pref in _FLOW_PRIORITY:
            if pref not in cands:
                continue
            v = r.get(f'val_{pref}')
            if v in (None, '', '--'):
                continue
            try:
                if float(v) > 0:
                    return pref
            except (TypeError, ValueError):
                continue
        if checked >= 50:          # 只看最近 50 行，避免大表遍历开销
            break

    # 全无有效值：按静态优先级回退
    for pref in _FLOW_PRIORITY:
        if pref in cands:
            return pref
    return find_flow_code(code_list)


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
    'detect_server_emission',
    'normalize_code',
    'get_param_unit',
    'is_concentration_param',
    'get_concentration_divisor',
    'calc_emission_rate',
    'calc_emission_mass',
    'extract_emission_mass',
    'find_flow_code',
    'pick_flow_code',
    'format_emission_rate',
]
