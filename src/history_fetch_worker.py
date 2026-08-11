# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 历史数据后台取数 Worker（三项优化 · 问题一 + P1）

在后台线程中按 sub 批量请求历史数据，把结果写回主线程持有的共享
``history_cache``（带 TTL），逐 sub 通过 ``history_result`` 信号把解析好的
series 回传给主线程，全部完成后发 ``fetch_finished``。

主线程只负责"数据组装 + draw_idle()"，网络 I/O 与同步重绘彻底移出主线程，
消除切指标卡顿。

缓存模式复刻 ``PredictionWorker`` 的 ``_get_cached(key, ttl, fetch_fn)``：
dict 在主线程创建、跨线程读写（Python GIL 下对"读多写少"的缓存安全，
PredictionWorker 已验证多年无碍）。
"""

from datetime import datetime, timedelta
import time
import traceback

from PyQt5.QtCore import QThread, pyqtSignal

from config import HISTORY_INDEX


def make_history_cache_key(subid, subtype_code, codes, start, end, index, use_corrected):
    """生成历史缓存键（主线程预检与 worker 写回必须一致）。

    键 = (subid, subtype_code, codes, start, end, index, use_corrected)
    """
    return (subid, subtype_code, codes, start, end, index, use_corrected)


class HistoryFetchWorker(QThread):
    """后台按 sub 批量取历史数据。

    Signals:
        history_result(dict): 每完成一个 sub 发出一次，payload 为
            ``{subid, subname, ent_name, subtype_code, window, series:[...]}``。
        fetch_finished(): 全部 sub 完成后发出。
    """

    history_result = pyqtSignal(dict)
    fetch_finished = pyqtSignal()

    def __init__(self, multi_client, sub_tasks, history_cache, ttl):
        """初始化。

        Args:
            multi_client: GZMultiAccountClient 实例（含 get_client_by_subid）。
            sub_tasks: 任务列表，每元素结构见设计 §3：
                ``{subid, subtype_code, codes, params:[(code,name,axis)],
                   start, end, index, use_corrected, subname, ent_name}``。
            history_cache: 主线程持有的共享 dict，value=(timestamp, rows)。
            ttl: 缓存有效期（秒），对应 config.HISTORY_TTL。
        """
        super().__init__()
        self.multi_client = multi_client
        self.sub_tasks = list(sub_tasks or [])
        self.history_cache = history_cache
        self._ttl = ttl

    def _get_cached(self, key, ttl, fetch_fn, *args, **kwargs):
        """复刻 PredictionWorker 的缓存模式。

        先查 ``history_cache[key]``，未过期直接返回；否则 ``fetch_fn`` 取数并
        写回 ``(now, data)``。
        """
        now = time.time()
        entry = self.history_cache.get(key)
        if entry is not None:
            ts, data = entry
            if now - ts < ttl:
                return data
        data = fetch_fn(*args, **kwargs)
        self.history_cache[key] = (now, data)
        return data

    def _fetch_one(self, task):
        """取单个 sub 的原始 rows（带缓存）。返回 rows 列表。"""
        subid = task.get('subid')
        subtype_code = task.get('subtype_code')
        codes = task.get('codes', '')
        start = task.get('start', '')
        end = task.get('end', '')
        index = task.get('index', HISTORY_INDEX)
        use_corrected = task.get('use_corrected', False)

        client_info = self.multi_client.get_client_by_subid(subid)
        if not client_info:
            return []
        client = client_info["client"]

        try:
            result = self._get_cached(
                make_history_cache_key(
                    subid, subtype_code, codes, start, end, index, use_corrected
                ),
                self._ttl,
                client.query_history,
                subid, subtype_code, codes, start, end, index, 1, 1000, use_corrected,
            )
        except Exception as e:
            print(f"[WARN] HistoryFetchWorker 获取 {task.get('subname', subid)} 历史数据失败: {e}")
            traceback.print_exc()
            return []

        if isinstance(result, dict):
            return result.get('rows', [])
        return []

    def _build_series(self, rows, params):
        """把一个 sub 的原始 rows 按 params 拆成多条 series。"""
        series = []
        for (code, name, axis) in params:
            val_key = f"val_{code}"
            times = [r.get('DateTime', '') for r in rows]
            values = []
            for r in rows:
                v = r.get(val_key)
                if v is not None and v != '':
                    try:
                        values.append(float(v))
                    except (ValueError, TypeError):
                        values.append(None)
                else:
                    values.append(None)
            series.append({
                "param_name": name,
                "code": code,
                "axis": axis,
                "times": times,
                "values": values,
            })
        return series

    def run(self):
        """后台执行：遍历 sub_tasks，逐 sub 取数并回传 series。"""
        for task in self.sub_tasks:
            subid = task.get('subid')
            subname = task.get('subname', '')
            ent_name = task.get('ent_name', '')
            subtype_code = task.get('subtype_code', '')
            start = task.get('start', '')
            end = task.get('end', '')

            rows = self._fetch_one(task)
            params = task.get('params', [])
            series = self._build_series(rows, params)

            window = f"{start} ~ {end}" if (start and end) else ""
            self.history_result.emit({
                "subid": subid,
                "subname": subname,
                "ent_name": ent_name,
                "subtype_code": subtype_code,
                "window": window,
                "series": series,
            })

        self.fetch_finished.emit()
