# -*- coding: utf-8 -*-
"""官网日数据导入（v5.78）

背景：官网「历史数据」页面可直接查询日数据并导出 Excel，但客户端调用的
`HistoryReport.ashx?index=2` 在该服务端始终返回空（历史 258 次实证），
只能靠小时数据聚合，而小时值已被平滑/缺数，算出的日排放量与官网导出
存在偏差（如 2026-11-07 官网 5.97 kg，客户端仅 0.55 kg）。

因此提供「导入官网导出文件」：解析官网导出的「排放量(t)」列，×1000 转 kg，
按 企业+排口+参数+日期 持久化。预测取数时优先使用该序列，基准即为官网日均，
可逐日核对。

文件结构（官网导出）：
  第1行 标题；第2行 参数名(含单位，合并单元格)；
  第3行 子列（实测值/折算值/标准值/排放量(t)）；
  第4行起 数据（第 0/1/2 列为 企业/排口/监测时间，末尾有 平均值/最大值/最小值/累计值 汇总行）。
"""
import json
import os
import re
from typing import Dict, List, Optional, Tuple

_T_ON_KG = 1000.0          # 1 t = 1000 kg


def _data_dir() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')


def _store_path() -> str:
    return os.path.join(_data_dir(), 'web_daily_import.json')


def _norm_param(name: str) -> str:
    """去掉单位括号并规范参数名，返回系统内部参数名（尽量）"""
    s = str(name or '').strip()
    if not s:
        return ''
    # 去掉末尾的单位括号，如 (mg/m3)/(%)/(t)
    s = re.sub(r'[（(]\s*(mg/m3|mg/m³|m3|m³|%|t|℃|千帕|kpa)\s*[)）]', '',
               s, flags=re.I).strip()
    # 官网「碳氢化合物(总烃)」→ 系统「碳氢化合物总烃」
    if '碳氢化合物' in s:
        return '碳氢化合物总烃'
    s = s.replace('(总烃)', '').replace('（总烃）', '')
    return s


def _as_float(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if s in ('', '--', '/', '-', 'nan', 'NaN'):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _as_date(v) -> Optional[str]:
    """把监测时间规范为 YYYY-MM-DD"""
    if v is None:
        return None
    s = str(v).strip()
    m = re.match(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def parse_export(path: str) -> Dict[str, Dict]:
    """解析官网导出的历史数据文件（.xls/.xlsx）

    Returns:
        { "企业|排口|参数": {"dates": [...], "values_kg": {...},
                            "ent":..., "subname":..., "param":..., "unit_src":"t"} }
    """
    import pandas as pd

    df = pd.read_excel(path, header=None)
    if df.shape[0] < 4:
        raise ValueError('文件内容过少，无法识别为官网历史数据导出')
    row_param = df.iloc[1]
    row_sub = df.iloc[2]

    # 建立 参数 -> 排放量(t) 列索引
    param_emis_col: Dict[str, int] = {}
    cur = ''
    for j in range(df.shape[1]):
        raw = row_param.iloc[j]
        if isinstance(raw, str) and raw.strip():
            cur = _norm_param(raw)
        sub = row_sub.iloc[j]
        if cur and isinstance(sub, str) and '排放量' in sub:
            param_emis_col[cur] = j
    if not param_emis_col:
        raise ValueError('未找到「排放量(t)」列，请确认导出文件包含排放量数据')

    ent_col, sub_col, time_col = 0, 1, 2
    out: Dict[str, Dict] = {}
    for r in range(3, df.shape[0]):
        date = _as_date(df.iat[r, time_col])
        if not date:                      # 平均值/最大值/最小值/累计值 等汇总行
            continue
        ent = str(df.iat[r, ent_col] or '').strip()
        subname = str(df.iat[r, sub_col] or '').strip()
        if not ent or not subname:
            continue
        for param, col in param_emis_col.items():
            t = _as_float(df.iat[r, col])
            if t is None:
                continue
            key = f"{ent}|{subname}|{param}"
            rec = out.setdefault(key, {
                'ent': ent, 'subname': subname, 'param': param,
                'unit_src': 't', 'values_kg': {},
            })
            rec['values_kg'][date] = round(t * _T_ON_KG, 6)

    for rec in out.values():
        rec['dates'] = sorted(rec['values_kg'].keys())
    return out


class WebDailyStore:
    """官网导入日排放量（kg）的持久化存储"""

    def __init__(self, path: Optional[str] = None):
        self.path = path or _store_path()
        self.series: Dict[str, Dict] = {}
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
        """合并导入结果，返回新增/更新的日期点数"""
        n = 0
        for key, rec in (parsed or {}).items():
            cur = self.series.get(key)
            if not cur:
                self.series[key] = rec
                n += len(rec.get('values_kg') or {})
                continue
            cur.setdefault('values_kg', {}).update(rec.get('values_kg') or {})
            cur['dates'] = sorted(cur['values_kg'].keys())
            cur['ent'] = rec.get('ent', cur.get('ent', ''))
            cur['subname'] = rec.get('subname', cur.get('subname', ''))
            cur['param'] = rec.get('param', cur.get('param', ''))
            n += len(rec.get('values_kg') or {})
        self.save()
        return n

    def get_series(self, ent: str, subname: str, param: str,
                   start: Optional[str] = None,
                   end: Optional[str] = None) -> Tuple[List[float], List[str]]:
        """取某排口某参数在 [start, end]（YYYY-MM-DD）内的日排放量（kg）"""
        rec = self.series.get(f"{ent}|{subname}|{param}")
        if not rec:
            return [], []
        vals, dates = [], []
        for d in sorted((rec.get('values_kg') or {}).keys()):
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
    return get_store().merge(parsed)
