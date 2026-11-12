# -*- coding: utf-8 -*-
"""官网历史数据导入（v5.78 引入，v5.82 按 4 份冠洲导出实测校正）

背景：官网「历史数据」页面可直接查询/导出 Excel，但客户端调用的
`HistoryReport.ashx?index=2`（日数据）在该服务端始终返回空（历史 258 次实证），
只能靠小时数据聚合，而小时值已被平滑/缺数，算出的日排放量与官网导出
存在偏差（如 2026-11-07 官网 5.97 kg，客户端仅 0.55 kg）。

因此提供「导入官网导出文件」：解析官网导出的「排放量」列，日数据单位(t)×1000
转 kg，小时/分钟数据单位(kg)按日累加，按 企业+排口+参数+日期 持久化。
预测取数时优先使用该序列，基准即为官网日均，可逐日核对。

── 排放量口径（v5.82 用 4 份官网导出实测确认，勿再改回）──────────────
  废水口（总排口：化学需氧量/氨氮/pH/水温，浓度 mg/L）：
      排放量(kg) = 浓度(mg/L)  × 流量(m³) / 1000
  废气口（VOCs总排口：非甲烷总烃/甲烷/碳氢化合物，浓度 mg/m³）：
      排放量(kg) = 浓度(mg/m³) × 流量(m³) / 1e6
      日导出排放量(t) = 上述 kg / 1000
  **导入模块直接采用导出文件的「排放量」列，不用浓度×流量重算**：
  官网导出的「流量(m3)」列语义在不同排口/粒度下并不统一——
  废气小时值 ≈ m³/h（数值恰等于该小时体积）、日值 = 日累计 m³，
  而废水 10 分钟桶 = 该桶累计体积（实测 4 m³：4.65×4/1000=0.0186 kg
  ≈ 官网 0.019 kg）。自行反推极易差 6~60 倍。服务端 API 才是统一的
  m³/h 口径（分钟须 ÷60），两套数据源不可混用。

── 三种粒度（由时间列格式判定）────────────────────────────────────────
  日   '2026-11-01'          → 每行即一整天，直接采用
  小时 '2026-11-12 00'       → 同日多行累加；需覆盖 ≥18 个不同小时才算完整天
  分钟 '2026-11-11 07:00'    → 同上；按不同小时数判定覆盖
  官网导出常含**部分天**（如总排口 11-11 仅 07:00-23:50、VOCs 11-12 仅
  00-06）。部分天排放量只覆盖半天，若混入日均基准会显著拉低结果，
  故 v5.82 将其记入 `partial_days` 并从 `values_kg`/基准序列中排除，
  数据本身仍保留供查看，UI 导入时提示忽略数量。

文件结构（官网导出）：
  第1行 标题；第2行 参数名(含单位，合并单元格)；
  第3行 子列（实测值/折算值/标准值/排放量(t 或 kg)/来源/状态）；
  第4行起 数据（第 0/1/2 列为 企业/排口/监测时间，末尾可能有汇总行）。
"""
import datetime as _dt
import json
import os
import re
from typing import Dict, List, Optional, Tuple

_T_ON_KG = 1000.0          # 1 t = 1000 kg
_FULL_DAY_MIN_HOURS = 18   # 与 worker 的「有效小时 <18 判缺数」口径一致


def _data_dir() -> str:
    """数据目录：打包版用 exe 同级 data/，源码运行用项目 data/。

    v5.82 修正：打包后 __file__ 位于 PyInstaller 临时解压目录，
    直接用会导致导入的官网数据在程序退出后丢失。
    """
    import sys
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'data')


def _store_path() -> str:
    return os.path.join(_data_dir(), 'web_daily_import.json')


# 括号内容统一剥离：既含单位 (mg/L)/(mg/m3)/(t)，也含 (总烃) 等修饰
_UNIT_PARENS = re.compile(r'[（(][^（）()]*[）)]')


def _norm_param(name: str) -> str:
    """去掉单位括号并规范参数名，返回系统内部参数名。

    v5.82：旧正则只列了 mg/m3|t|% 等，漏掉废水单位 mg/L，导致
    「化学需氧量(mg/L)」被原样存成 key，与系统内部名「化学需氧量」
    匹配不上，废水排口导入的数据完全用不上。改为剥离任意括号内容。
    """
    s = str(name or '').strip()
    if not s:
        return ''
    # 官网「碳氢化合物(总烃)」→ 系统「碳氢化合物总烃」（括号里不是单位）
    if '碳氢化合物' in s:
        return '碳氢化合物总烃'
    return _UNIT_PARENS.sub('', s).strip()


def _as_float(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    s = str(v).strip()
    if s in ('', '--', '/', '-', 'nan', 'NaN', '√', '正常', '异常'):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


_RE_MIN = re.compile(r'^\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2}):(\d{1,2})\s*$')
_RE_HOUR = re.compile(r'^\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s+(\d{1,2})\s*$')
_RE_DAY = re.compile(r'^\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*$')


def _parse_time(v):
    """返回 (YYYY-MM-DD, granularity, hour) 或 None（汇总行/非法行）。

    granularity: 'day' | 'hour' | 'minute'
    """
    if isinstance(v, _dt.datetime):
        return (v.strftime('%Y-%m-%d'), 'minute' if v.minute or v.second else 'hour', v.hour)
    if isinstance(v, _dt.date):
        return (v.strftime('%Y-%m-%d'), 'day', None)
    s = str(v or '').strip()
    m = _RE_MIN.match(s)
    if m:
        y, mo, d, h, _mi = map(int, m.groups())
        return (f"{y}-{mo:02d}-{d:02d}", 'minute', h)
    m = _RE_HOUR.match(s)
    if m:
        y, mo, d, h = map(int, m.groups())
        return (f"{y}-{mo:02d}-{d:02d}", 'hour', h)
    m = _RE_DAY.match(s)
    if m:
        y, mo, d = map(int, m.groups())
        return (f"{y}-{mo:02d}-{d:02d}", 'day', None)
    return None


def _as_date(v) -> Optional[str]:
    """把监测时间规范为 YYYY-MM-DD（兼容旧调用）。"""
    p = _parse_time(v)
    return p[0] if p else None


def _read_rows(path: str) -> List[list]:
    """纯 xlrd / openpyxl 读取（v5.82：去掉 pandas 依赖）。

    v5.81 的 spec hiddenimports 未列 pandas，打包版导入存在缺依赖风险；
    xlrd / openpyxl 本就在 hiddenimports 内，且本机运行环境齐备。
    """
    ext = os.path.splitext(path)[1].lower()
    rows: List[list] = []
    if ext == '.xls':
        import xlrd
        book = xlrd.open_workbook(path)
        sh = book.sheet_by_index(0)
        for r in range(sh.nrows):
            row = []
            for c in range(sh.ncols):
                cell = sh.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:      # 日期单元格 -> datetime
                    try:
                        row.append(xlrd.xldate.xldate_as_datetime(cell.value, book.datemode))
                    except Exception:
                        row.append(cell.value)
                else:
                    row.append(cell.value)
            rows.append(row)
    elif ext in ('.xlsx', '.xlsm'):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            for row in wb.active.iter_rows(values_only=True):
                rows.append(list(row))
        finally:
            wb.close()
    else:
        raise ValueError('仅支持官网导出的 .xls / .xlsx 文件')
    return rows


def _find_header(rows) -> int:
    """定位「监测时间」表头行（兼容标题行数不固定的导出）。"""
    for i, row in enumerate(rows[:6]):
        for c, v in enumerate(row):
            if str(v).strip() == '监测时间':
                return i
    return 1          # 兜底：官网固定第 2 行


def parse_export(path: str) -> Dict[str, Dict]:
    """解析官网导出的历史数据文件（.xls/.xlsx）

    Returns:
        { "企业|排口|参数": {
            "ent", "subname", "param", "unit_src",
            "values_kg": {date: kg},          # 仅完整天，参与日均基准
            "partial_days": {date: {"kg":..., "hours":..., "granularity":...}},
            "dates": [...], "rows": n, "granularity": ... } }
    """
    rows = _read_rows(path)
    hi = _find_header(rows)
    if len(rows) < hi + 3:
        raise ValueError('文件内容过少，无法识别为官网历史数据导出')
    row_param = rows[hi]
    row_sub = rows[hi + 1]

    # 参数名是合并单元格（仅首列有值）→ 向前填充
    param_emis_col: Dict[str, tuple] = {}
    cur = ''
    for j in range(len(row_sub)):
        raw = row_param[j] if j < len(row_param) else ''
        if isinstance(raw, str) and raw.strip():
            cur = _norm_param(raw)
        sub = str(row_sub[j] or '').strip()
        if cur and '排放量' in sub:
            low = sub.replace(' ', '').lower()
            factor = _T_ON_KG if '(t)' in low or '（t）' in low else 1.0
            param_emis_col[cur] = (j, factor)
    if not param_emis_col:
        raise ValueError('未找到「排放量」列，请确认导出文件包含排放量数据')

    ent_col, sub_col, time_col = 0, 1, 2
    out: Dict[str, Dict] = {}
    # 临时累计：key -> date -> {"kg", "hours": set, "gran"}
    acc: Dict[str, Dict[str, dict]] = {}
    for r in range(hi + 2, len(rows)):
        row = rows[r]
        if len(row) <= time_col:
            continue
        tp = _parse_time(row[time_col])
        if not tp:                       # 平均值/最大值/累计值等汇总行
            continue
        date, gran, hour = tp
        ent = str(row[ent_col] or '').strip()
        subname = str(row[sub_col] or '').strip()
        if not ent or not subname:
            continue
        for param, (col, factor) in param_emis_col.items():
            raw_v = _as_float(row[col]) if col < len(row) else None
            if raw_v is None:
                continue
            key = f"{ent}|{subname}|{param}"
            rec = out.setdefault(key, {
                'ent': ent, 'subname': subname, 'param': param,
                'unit_src': 't' if factor == _T_ON_KG else 'kg',
                'values_kg': {}, 'partial_days': {}, 'rows': 0,
                'granularity': gran,
            })
            rec['rows'] += 1
            day = acc.setdefault(key, {}).setdefault(
                date, {'kg': 0.0, 'hours': set(), 'gran': gran})
            day['kg'] += raw_v * factor
            if hour is not None:
                day['hours'].add(hour)
            day['gran'] = gran

    # 按覆盖小时数判定完整天 / 部分天
    for key, days in acc.items():
        rec = out[key]
        for date, day in days.items():
            kg = round(day['kg'], 6)
            if day['gran'] == 'day' or len(day['hours']) >= _FULL_DAY_MIN_HOURS:
                rec['values_kg'][date] = kg
                rec['partial_days'].pop(date, None)
            else:
                rec['partial_days'][date] = {
                    'kg': kg, 'hours': len(day['hours']),
                    'granularity': day['gran'],
                }
        rec['dates'] = sorted(rec['values_kg'].keys())
    return out


class WebDailyStore:
    """官网导入日排放量（kg）的持久化存储"""

    def __init__(self, path: Optional[str] = None):
        self.path = path or _store_path()
        self.series: Dict[str, Dict] = {}
        self.last_import_partial = 0        # v5.82：最近一次导入忽略的部分天数
        self._load()

    def _load(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.series = data.get('series') or {}
        except Exception:
            self.series = {}

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump({'series': self.series}, f, ensure_ascii=False,
                          indent=1)
        except Exception:
            pass

    def merge(self, parsed: Dict[str, Dict]) -> int:
        """合并导入结果，返回新增/更新的日期点数。

        v5.82：合并 partial_days；若后续导入的完整日数据覆盖了该日期，
        则从 partial_days 中移除（避免同一天既算完整又算部分）。
        """
        n = 0
        for key, rec in (parsed or {}).items():
            cur = self.series.get(key)
            if not cur:
                self.series[key] = rec
                n += len(rec.get('values_kg') or {})
                continue
            new_vals = rec.get('values_kg') or {}
            cur.setdefault('values_kg', {}).update(new_vals)
            partial = cur.setdefault('partial_days', {})
            partial.update(rec.get('partial_days') or {})
            for d in new_vals:                       # 完整日覆盖部分日
                partial.pop(d, None)
            cur['dates'] = sorted(cur['values_kg'].keys())
            for f in ('ent', 'subname', 'param', 'unit_src', 'granularity'):
                if rec.get(f):
                    cur[f] = rec[f]
            n += len(new_vals)
        self.save()
        return n

    def get_series(self, ent: str, subname: str, param: str,
                   start: Optional[str] = None,
                   end: Optional[str] = None) -> Tuple[List[float], List[str]]:
        """取某排口某参数在 [start, end]（YYYY-MM-DD）内的日排放量（kg）。

        v5.82：明确排除 partial_days，防止半天数据混入日均基准。
        """
        rec = self.series.get(f"{ent}|{subname}|{param}")
        if not rec:
            return [], []
        partial = rec.get('partial_days') or {}
        vals, dates = [], []
        for d in sorted((rec.get('values_kg') or {}).keys()):
            if d in partial:
                continue
            if start and d < start:
                continue
            if end and d > end:
                continue
            vals.append(float(rec['values_kg'][d]))
            dates.append(d)
        return vals, dates

    def matched_count(self) -> int:
        return len(self.series)


_GLOBAL_STORE: Optional[WebDailyStore] = None


def get_store() -> WebDailyStore:
    global _GLOBAL_STORE
    if _GLOBAL_STORE is None:
        _GLOBAL_STORE = WebDailyStore()
    return _GLOBAL_STORE


def import_file(path: str) -> int:
    parsed = parse_export(path)
    st = get_store()
    n = st.merge(parsed)
    st.last_import_partial = sum(
        len(r.get('partial_days') or {}) for r in parsed.values())
    return n
