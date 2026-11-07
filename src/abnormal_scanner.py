# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 异常数据扫描与记录（v5.69）

功能：
1. classify_data_state: 解析服务端返回的 state_{code}/status_{code} 标记，
   分类为 超标/故障/停产/正常（官网手机端图例：超标=红色，故障=紫色，停产=灰色）。
2. AbnormalStore: 异常记录持久化存储（data/abnormal_records.json），
   支持去重写入、按企业/类型/时间范围条件查询。
3. scan_all: 登录后扫描近 N 小时（默认24小时）的小时数据，
   识别 超标/故障/停产/数据异常，并合并预警系统产出的 预警 记录。
"""

import json
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from data_processor import CODE_TO_NAME, classify_data_state
from param_units import get_param_unit

# 记录类型
TYPE_EXCEED = '超标'
TYPE_FAULT = '故障'
TYPE_STOP = '停产'
TYPE_ABNORMAL = '异常'
TYPE_WARNING = '预警'
ALL_TYPES = (TYPE_EXCEED, TYPE_FAULT, TYPE_STOP, TYPE_ABNORMAL, TYPE_WARNING)

# 故障/停产标记兼容：数字型(2=故障,3=停产)、字母型(F/S)、中文描述
_FAULT_TOKENS = ('2', 'F', 'f')
_STOP_TOKENS = ('3', 'S', 's')

# v5.72：一次性清除旧逻辑产生的"数据缺失"误报记录后，在存储文件里写下此标记
_PURGE_FLAG = 'purge_missing_false_positives_v572_done'


def _records_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'data', 'abnormal_records.json'
    )


def _parse_dt(s) -> Optional[datetime]:
    """解析服务端/记录里的时间字符串，失败返回 None"""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d %H',
                '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _is_invalid_val(v) -> bool:
    """-9999 等哨兵值/空值/非数值都视为无效数据"""
    if v in (None, '', '--'):
        return True
    try:
        return float(v) <= -9998
    except (ValueError, TypeError):
        return True


class AbnormalStore:
    """异常记录持久化存储（线程安全，data/abnormal_records.json）"""

    def __init__(self, path: Optional[str] = None):
        self.path = path or _records_path()
        self._lock = threading.Lock()
        self.records: List[dict] = []   # 按时间倒序（最新在前）
        self._index: Dict[str, dict] = {}  # dedupe key -> record
        self._purged = False            # v5.72: 误报清理标记
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._load()

    @staticmethod
    def _is_missing_record(rec) -> bool:
        """v5.72 前旧逻辑会把未报送参数记成'数据缺失'，一次性清除"""
        return (isinstance(rec, dict) and rec.get('type') == TYPE_ABNORMAL
                and str(rec.get('desc', '')).startswith('数据缺失'))

    @staticmethod
    def dedupe_key(rec: dict) -> str:
        return '|'.join([
            str(rec.get('ent', '')), str(rec.get('subid', '')),
            str(rec.get('code', '')), str(rec.get('time', '')),
            str(rec.get('type', '')),
        ])

    def _load(self):
        data = None
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = None
        recs: List[dict] = []
        if isinstance(data, list):
            recs = [r for r in data if isinstance(r, dict)]
        elif isinstance(data, dict):
            recs = [r for r in (data.get('records') or [])
                    if isinstance(r, dict)]
            self._purged = bool(data.get(_PURGE_FLAG))
        if data is None:
            # 首次运行（无历史文件），无需清理
            self._purged = True
        if not self._purged:
            # v5.72 一次性清除"数据缺失"误报（真实缺数会在下次扫描重新生成）
            recs = [r for r in recs if not self._is_missing_record(r)]
            self._purged = True
        for r in recs:
            self.records.append(r)
            self._index[self.dedupe_key(r)] = r

    def _save(self):
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump({'records': self.records, _PURGE_FLAG: self._purged},
                          f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def add_records(self, records: List[dict]) -> int:
        """批量写入（去重），返回新增条数"""
        added = 0
        with self._lock:
            for rec in records or []:
                if not isinstance(rec, dict):
                    continue
                key = self.dedupe_key(rec)
                if key in self._index:
                    continue
                self._index[key] = rec
                self.records.append(rec)
                added += 1
            if added:
                self._prune_locked()
                self._save()
        return added

    def _prune_locked(self, max_records: int = 10000, keep_days: int = 180):
        """限制总量与保留时长，防止无限膨胀"""
        cutoff = datetime.now() - timedelta(days=keep_days)
        kept = []
        for r in self.records:
            dt = _parse_dt(r.get('detected_at') or r.get('time'))
            if dt is None or dt >= cutoff:
                kept.append(r)
        if len(kept) > max_records:
            kept = kept[-max_records:]
        self.records = kept
        self._index = {self.dedupe_key(r): r for r in kept}

    def query(self, ent: Optional[str] = None, rtype: Optional[str] = None,
              start: Optional[str] = None, end: Optional[str] = None,
              limit: int = 5000) -> List[dict]:
        """条件查询：企业/类型/时间范围（按记录 time 字段过滤），最新在前"""
        dt_start = _parse_dt(start)
        dt_end = _parse_dt(end)
        with self._lock:
            result = []
            for r in reversed(self.records):
                if ent and r.get('ent', '') != ent:
                    continue
                if rtype and r.get('type', '') != rtype:
                    continue
                if dt_start or dt_end:
                    dt = _parse_dt(r.get('time'))
                    if dt is None:
                        continue
                    if dt_start and dt < dt_start:
                        continue
                    if dt_end and dt > dt_end:
                        continue
                result.append(r)
                if len(result) >= limit:
                    break
            return result

    def flush(self):
        with self._lock:
            self._save()


# ── 扫描器 ────────────────────────────────────────────────────────────────

def _match_ent_id(ent_list: list, username: str):
    """按用户名匹配企业ID（完全/包含/去空格匹配，与主窗口逻辑一致）"""
    for ent in ent_list:
        name = str(ent.get('name', ''))
        if name == username:
            return ent.get('id')
    for ent in ent_list:
        name = str(ent.get('name', ''))
        if username in name or name in username:
            return ent.get('id')
    for ent in ent_list:
        name = str(ent.get('name', '')).replace(' ', '')
        if username.replace(' ', '') == name:
            return ent.get('id')
    return None


def _scan_enterprise(client, username: str, hours: int = 24) -> List[dict]:
    """扫描单个企业近 N 小时的小时数据，返回异常记录列表"""
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(hours=hours)
    start_s = start_dt.strftime('%Y-%m-%d %H:%M')
    end_s = end_dt.strftime('%Y-%m-%d %H:%M')
    now_s = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    records = []
    for subtype_code in ('64', '51'):   # 废气/VOCs + 废水
        try:
            ent_list = client.get_enterprise_list(subtype_code)
        except Exception:
            ent_list = []
        if not ent_list:
            continue
        ent_id = _match_ent_id(ent_list, username)
        if ent_id is None:
            ent_id = ent_list[0].get('id')
        try:
            subs = client.get_sub_list(ent_id, subtype_code)
        except Exception:
            subs = []
        for sub in subs or []:
            subid = sub.get('id') or sub.get('subid') or sub.get('SubID')
            subname = sub.get('name') or sub.get('subname') or sub.get('SubName') or ''
            if subid is None:
                continue
            codes_raw = (sub.get('itemCode') or sub.get('itemcode')
                         or sub.get('ItemCode') or '')
            code_list = [c.strip() for c in str(codes_raw).split(',') if c.strip()]
            if not code_list:
                continue
            try:
                raw = client.query_history(
                    subid=str(subid), subtype=subtype_code,
                    codes=','.join(code_list),
                    start=start_s, end=end_s, index=1, rows=500)
            except Exception:
                continue
            rows = raw.get('rows', []) or []
            records.extend(_classify_rows(
                rows, code_list, username, str(subid), str(subname), now_s))
    return records


def _classify_rows(rows: List[dict], code_list: List[str], ent: str,
                   subid: str, subname: str, detected_at: str) -> List[dict]:
    """逐行逐参数分类：超标/故障/停产/异常（数据缺失或未知标记）"""
    # v5.72：整个扫描窗口内从未报送过值的 code，视为该排口未启用此参数，
    # 不参与"数据缺失"判定。否则像总排口同时配置 废水流量/累计流量/流量
    # 多个 code、实际只报送其中一部分时，未报送的 code 会被每小时误报缺失。
    codes_with_data = {
        c for c in code_list
        if any(not _is_invalid_val(row.get(f'val_{c}')) for row in rows)
    }
    records = []
    for row in rows:
        dt = str(row.get('DateTime', ''))
        row_has_valid = any(
            not _is_invalid_val(row.get(f'val_{c}')) for c in code_list)
        for code in code_list:
            val = row.get(f'val_{code}')
            state = row.get(f'state_{code}', '')
            status = row.get(f'status_{code}', '')
            cls = classify_data_state(state, status)
            invalid = _is_invalid_val(val)

            rtype, desc = None, ''
            if cls == TYPE_EXCEED:
                rtype = TYPE_EXCEED
            elif cls == TYPE_FAULT:
                rtype = TYPE_FAULT
            elif cls == TYPE_STOP:
                rtype = TYPE_STOP
            elif invalid and row_has_valid and code in codes_with_data:
                # 数值缺失/无效，但同周期其他参数有值，且该参数本窗口报送过
                # → 真实缺数异常
                rtype, desc = TYPE_ABNORMAL, '数据缺失（同周期其他参数有值）'
            elif cls is None and not invalid:
                # 服务端返回了无法识别的标记 → 异常
                rtype, desc = TYPE_ABNORMAL, f'未知标记 state={state} status={status}'
            if not rtype:
                continue

            records.append({
                'time': dt,
                'ent': ent,
                'subname': subname,
                'subid': subid,
                'param': CODE_TO_NAME.get(code, code),
                'code': code,
                'type': rtype,
                'value': '' if invalid else val,
                'unit': get_param_unit(code),
                'std': row.get(f'stand_{code}', ''),
                'desc': desc,
                'state_raw': str(state),
                'status_raw': str(status),
                'detected_at': detected_at,
                'source': '24h扫描',
            })
    return records


def _warning_records(warning_history: List[dict], hours: int = 24) -> List[dict]:
    """把预警系统历史中近 N 小时的预警转为记录"""
    cutoff = datetime.now() - timedelta(hours=hours)
    now_s = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    out = []
    for w in warning_history or []:
        dt = _parse_dt(w.get('datetime'))
        if dt is None or dt < cutoff:
            continue
        out.append({
            'time': w.get('datetime', ''),
            'ent': w.get('ent_name', ''),
            'subname': w.get('subname', ''),
            'subid': '',
            'param': w.get('param', ''),
            'code': '',
            'type': TYPE_WARNING,
            'value': w.get('value', ''),
            'unit': '',
            'std': w.get('threshold', ''),
            'desc': f"{w.get('level', '')} {w.get('type', '')}".strip(),
            'state_raw': '',
            'status_raw': '',
            'detected_at': now_s,
            'source': '预警系统',
        })
    return out


def scan_all(multi_client, warning_history: Optional[List[dict]] = None,
             hours: int = 24) -> List[dict]:
    """扫描所有已登录企业，合并预警记录（在后台线程调用）"""
    all_records: List[dict] = []
    clients = getattr(multi_client, 'clients', {}) or {}
    for username, client in clients.items():
        try:
            all_records.extend(_scan_enterprise(client, username, hours))
        except Exception:
            continue
    all_records.extend(_warning_records(warning_history, hours))
    return all_records
