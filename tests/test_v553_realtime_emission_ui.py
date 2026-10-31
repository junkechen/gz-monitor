# -*- coding: utf-8 -*-
"""
v5.53 功能验证：端到端复现"排放量没数字"并确认已修复。

场景完全对齐用户截图（鼎鑫VOCs4#，非热电厂）：
  - 实时接口返回：非甲烷总烃 2.4 / 流速 7.77 / 烟气温度 89.9
  - 实时接口**不返回**烟气流量（210）→ 由「最近 2 小时历史」补充为 34195(历史)
  - 期望：非甲烷总烃排放量 = 2.4 × 34195 / 1e6 = 0.082 kg

修复前：补充行缺 'code' 字段 → find_flow_code 找不到流量 → 排放量全为 '--'。
修复后：应显示 0.082。

运行：QT_QPA_PLATFORM=offscreen C:/Python38/python.exe tests/test_v553_realtime_emission_ui.py
"""
import os
import sys
import logging

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
logging.getLogger("matplotlib").setLevel(logging.WARNING)

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from PyQt5.QtWidgets import QApplication
from main_window import MainWindow


class _FakeSubClient:
    """模拟排口客户端：只提供历史（分钟）查询，供补充参数使用。"""

    def query_history(self, *a, **k):
        return {
            'rows': [
                {'DateTime': '2026-10-13 03:06:00', 'val_210': 34195, 'val_209': 19.1},
                {'DateTime': '2026-10-13 03:07:00', 'val_210': 34195, 'val_209': 19.1},
            ],
            'total': 2,
        }

    def get_realtime_data(self, *a, **k):
        return {'rows': []}


class _FakeMultiClient:
    clients = {}

    def get_all_realtime_data(self, *a, **k):
        return {}

    def get_client_by_subid(self, subid, *a, **k):
        return {'client': _FakeSubClient(), 'username': '山东冠洲股份有限公司'}


def main():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    w = MainWindow(_FakeMultiClient())

    # 让 itemCode 固定返回 VOCs 排口的参数集合（避免真实网络）
    w._get_sub_itemcodes = lambda subid, subname, subtype_code: '383,211,210,525,209'

    grouped = {
        'uk_vocs': {
            'subid': '9910',
            'subtype': 'VOCs',
            'ent_name': '山东冠洲股份有限公司',
            'subname': '鼎鑫VOCs4#(VOCs)',
            'status': '正常',
            'params': [
                {'code': 383, 'name': '非甲烷总烃', 'value': 2.4, 'std': '50', 'is_exceed': False},
                {'code': 211, 'name': '流速', 'value': 7.77, 'std': '', 'is_exceed': False},
                {'code': 525, 'name': '烟气温度', 'value': 89.9, 'std': '', 'is_exceed': False},
            ],
        }
    }
    w.current_grouped_data = grouped
    w.selected_subid = '9910'

    w._show_sub_realtime('uk_vocs')

    tbl = w.realtime_table
    print(f"[INFO] 实时表 {tbl.rowCount()} 行 × {tbl.columnCount()} 列")
    got = {}
    for r in range(tbl.rowCount()):
        cells = []
        for c in range(tbl.columnCount()):
            it = tbl.item(r, c)
            cells.append(it.text() if it else '')
        print("   | " + " | ".join(cells))
        got[cells[0]] = cells

    ok = True
    # 1) 补充的流量行必须带值且显示为历史
    flow_row = got.get('烟气流量')
    if not flow_row or '34195' not in flow_row[1]:
        print("[FAIL] 烟气流量(历史补充) 行缺失或无值")
        ok = False
    else:
        print("[OK] 烟气流量已由历史补充: " + flow_row[1])

    # 2) 非甲烷总烃排放量应为 0.082
    nmth_row = got.get('非甲烷总烃')
    if not nmth_row:
        print("[FAIL] 非甲烷总烃 行缺失")
        ok = False
    elif nmth_row[4] != '0.082':
        print(f"[FAIL] 非甲烷总烃 排放量应为 0.082，实际 {nmth_row[4]!r}"
              f"（单位={nmth_row[3]!r}，实测={nmth_row[1]!r}）")
        ok = False
    else:
        print(f"[OK] 非甲烷总烃 排放量 = {nmth_row[4]} kg"
              f"（{nmth_row[1]} mg/m³ × 34195 m³ / 1e6）")

    # 3) 非浓度参数必须显示 --
    if nmth_row and '流速' in got and got['流速'][4] != '--':
        print(f"[FAIL] 流速（m/s）不应有排放量，实际 {got['流速'][4]!r}")
        ok = False

    # 4) 历史表：同样验证排放量列
    w._history_is_thermal_power = False
    rows = [
        {'DateTime': '2026-10-13 03:00:00', 'val_383': 2.4, 'val_210': 34195, 'val_211': 7.77},
        {'DateTime': '2026-10-13 03:07:00', 'val_383': 2.5, 'val_210': -9999, 'val_211': 7.7},
    ]
    w._display_history_table(rows, ['非甲烷总烃', '流速', '烟气流量'], '383,211,210')
    h = w.history_table
    hdr = [h.horizontalHeaderItem(c).text() if h.horizontalHeaderItem(c) else ''
           for c in range(h.columnCount())]
    print("[INFO] 历史表表头: " + " | ".join(hdr))
    for r in range(h.rowCount()):
        print("   | " + " | ".join(
            (h.item(r, c).text() if h.item(r, c) else '') for c in range(h.columnCount())))
    # 代码顺序 383,211,210 -> 列: 时间 | 383实测 | 383排放量 | 211实测 | 211排放量 | 210实测 | 210排放量
    if h.item(0, 2) is None or h.item(0, 2).text() != '0.082':
        print(f"[FAIL] 历史表第0行非甲烷总烃排放量应为 0.082，实际 "
              f"{h.item(0, 2).text() if h.item(0, 2) else None!r}")
        ok = False
    else:
        print("[OK] 历史表 排放量(第0行) = 0.082")
    if h.item(1, 2) is None or h.item(1, 2).text() != '--':
        print(f"[FAIL] 历史表无效流量(-9999)行排放量应为 --，实际 "
              f"{h.item(1, 2).text() if h.item(1, 2) else None!r}")
        ok = False
    else:
        print("[OK] 历史表 无效流量(-9999) 排放量显示 --")

    print("\n=== 通过 ===" if ok else "\n=== 失败 ===")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())