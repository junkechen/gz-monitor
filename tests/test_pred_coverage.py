# -*- coding: utf-8 -*-
"""
预测覆盖范围回归测试（守护「预测结果栏排放口不全」类回归）。

构造多排放口分组数据（跨多个企业、废水+废气混合）+ 假客户端（返回合成有效监测行）
+ 预置 itemcode 缓存，直接同步执行 PredictionWorker.run()，断言：
    【所有排放口的每个参数都生成预测，不遗漏任何排放口】。

只要任一排放口被静默跳过（无 codes / 无 client / 无有效数据 / 异常），测试即失败，
并打印每个排放口的覆盖情况，便于定位根因。

运行（必须用 Python 3.8 环境 + 项目根目录）：
    set QT_QPA_PLATFORM=offscreen
    C:\Python38\python.exe tests/test_pred_coverage.py
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


class _FakeClient:
    """模拟单企业客户端，返回合成有效监测行，绝不触发真实网络。"""
    def __init__(self, subids):
        self._subids = set(int(float(s)) for s in subids)

    def get_client_by_subid(self, subid):
        return {"client": self, "username": "test_ent"}

    def get_enterprise_subs(self):
        return [{"SubId": s} for s in self._subids]

    def get_minute_data_current_hour(self, subid, subtype_code, codes, use_corrected=False):
        # 废气：分钟级当前小时数据
        rows = []
        for i, c in enumerate(codes.split(",")):
            c = c.strip()
            rows.append({f"val_{c}": 10.0 + i})
        return {"rows": rows}

    def get_today_hour_data(self, subid, subtype_code, codes, use_corrected=False):
        # 废水：当日小时数据
        rows = []
        for i, c in enumerate(codes.split(",")):
            c = c.strip()
            rows.append({f"val_{c}": 5.0 + i})
        return {"rows": rows}


def _build_grouped_data():
    """构造 4 个排放口（2 废水 + 2 废气，跨 2 企业），每个 2 参数。"""
    subs = [
        dict(subid="1001", subtype="废水", subname="废水排口A", ent_name="企业甲",
             params=[{"code": "302", "name": "化学需氧量"}, {"code": "301", "name": "pH值"}]),
        dict(subid="1002", subtype="废水", subname="废水排口B", ent_name="企业甲",
             params=[{"code": "302", "name": "化学需氧量"}, {"code": "316", "name": "氨氮"}]),
        dict(subid="2001", subtype="废气", subname="废气排口A", ent_name="企业乙",
             params=[{"code": "201", "name": "非甲烷总烃"}, {"code": "203", "name": "二氧化硫"}]),
        dict(subid="2002", subtype="废气", subname="废气排口B", ent_name="企业乙",
             params=[{"code": "201", "name": "非甲烷总烃"}, {"code": "207", "name": "氮氧化物"}]),
    ]
    gd = {}
    for s in subs:
        key = f"{s['ent_name']}|{s['subname']}"
        gd[key] = s
    return gd, subs


def _expected_params(subs):
    """
    期望每个排放口被预测的参数集合。

    注意：PredictionWorker 实际产出的 param 字段 = CODE_TO_NAME.get(code, code)
    （见 main_window.PredictionWorker.run 中 param_name = code_to_name.get(code)），
    而非测试数据里随意填的 params[].name。因此期望集合必须以真实 CODE_TO_NAME 为准，
    否则会出现"实得2 MISSING"的伪失败。
    """
    from main_window import CODE_TO_NAME
    exp = {}
    for s in subs:
        exp[(s["ent_name"], s["subname"])] = set(
            CODE_TO_NAME.get(p["code"], p["code"]) for p in s["params"]
        )
    return exp


def main():
    from main_window import PredictionWorker, get_subtype_code, is_water_sub, CODE_TO_NAME

    grouped_data, subs = _build_grouped_data()

    # 预置 itemcode 缓存（模拟历史取数已填充），避免触发 _get_sub_itemcodes 的 API
    itemcode_cache = {}
    for s in subs:
        stc = get_subtype_code(s["subtype"])
        codes = ",".join(p["code"] for p in s["params"])
        itemcode_cache[f"{s['subid']}_{stc}"] = codes

    fake = _FakeClient([s["subid"] for s in subs])

    class _FakeMultiClient:
        def __init__(self, fc):
            self._fc = fc
        def get_client_by_subid(self, subid):
            return self._fc.get_client_by_subid(subid)

    captured = []
    def _on_done(preds):
        captured.append(preds)

    worker = PredictionWorker(
        grouped_data=grouped_data,
        multi_client=_FakeMultiClient(fake),
        prediction_horizon=3,
        prediction_params=[],  # 预测全部参数
        pred_type="小时数据预测",
        thresholds={},
        sub_itemcodes_cache=itemcode_cache,
        api_data_cache={},
        thresholds_cache={},
        get_subtype_code_fn=get_subtype_code,
        is_water_sub_fn=is_water_sub,
        code_to_name_map=CODE_TO_NAME,
        intervention_sm=None,
        get_sub_itemcodes_fn=lambda *a, **k: "",  # 不依赖兜底提取
    )
    worker.prediction_done.connect(_on_done)
    worker.run()  # 直接同步执行（测试用，等价于后台线程 run）

    preds = captured[0] if captured else []
    print(f"[DIAG] 生成预测条数: {len(preds)}")

    covered = {}
    for p in preds:
        k = (p["ent_name"], p["subname"])
        covered.setdefault(k, set()).add(p["param"])

    expected = _expected_params(subs)

    print("[DIAG] 覆盖情况：")
    all_ok = True
    for k in expected:
        got = covered.get(k, set())
        want = expected[k]
        status = "OK" if got == want else "MISSING"
        if got != want:
            all_ok = False
        print(f"  {k[1]}@{k[0]}: 期望{len(want)}参数 实得{len(got)} {status} 缺={sorted(want - got)}")

    if not captured:
        print("[FAIL] worker 未通过 prediction_done 信号返回任何结果（run 抛异常或被捕获）")
        return 1
    if all_ok:
        print("\n=== 预测覆盖完整：所有排放口全部参数均已预测 ===")
        return 0
    print("\n=== 预测覆盖不全：存在排放口/参数被跳过 ===")
    return 1


def main_fallback():
    """
    兜底分支专项用例（回归本次 NameError 根因）。

    构造 sub_itemcodes_cache={} 且 _get_sub_itemcodes_fn 返回空字符串的 worker，
    使每个排放口都进入 line 159-178 的兜底分支；断言其 run() 不抛 NameError，
    且每个带 params 的排放口都产生预测（覆盖率=全部）。
    """
    from main_window import PredictionWorker, get_subtype_code, is_water_sub, CODE_TO_NAME

    grouped_data, subs = _build_grouped_data()

    # 关键：缓存为空 + _get_sub_itemcodes 始终返回空 -> 强制走兜底分支
    fake = _FakeClient([s["subid"] for s in subs])

    class _FakeMultiClient:
        def __init__(self, fc):
            self._fc = fc
        def get_client_by_subid(self, subid):
            return self._fc.get_client_by_subid(subid)

    captured = []
    def _on_done(preds):
        captured.append(preds)

    worker = PredictionWorker(
        grouped_data=grouped_data,
        multi_client=_FakeMultiClient(fake),
        prediction_horizon=3,
        prediction_params=[],
        pred_type="小时数据预测",
        thresholds={},
        sub_itemcodes_cache={},  # 空缓存
        api_data_cache={},
        thresholds_cache={},
        get_subtype_code_fn=get_subtype_code,
        is_water_sub_fn=is_water_sub,
        code_to_name_map=CODE_TO_NAME,
        intervention_sm=None,
        get_sub_itemcodes_fn=lambda *a, **k: "",  # 始终返回空 -> 走兜底
    )
    # 兜底分支若仍引用未定义变量 group_data，这里会抛 NameError 未捕获 -> 测试失败
    worker.prediction_done.connect(_on_done)
    try:
        worker.run()
    except NameError as e:
        print(f"[FAIL] 兜底分支抛出未捕获 NameError: {e}")
        return 1
    except Exception as e:  # noqa
        print(f"[FAIL] 兜底分支抛出未捕获异常: {type(e).__name__}: {e}")
        return 1

    preds = captured[0] if captured else []
    print(f"[DIAG][兜底] 生成预测条数: {len(preds)}")

    covered = {}
    for p in preds:
        k = (p["ent_name"], p["subname"])
        covered.setdefault(k, set()).add(p["param"])

    expected = _expected_params(subs)

    print("[DIAG][兜底] 覆盖情况：")
    all_ok = True
    for k in expected:
        got = covered.get(k, set())
        want = expected[k]
        status = "OK" if got == want else "MISSING"
        if got != want:
            all_ok = False
        print(f"  {k[1]}@{k[0]}: 期望{len(want)}参数 实得{len(got)} {status} 缺={sorted(want - got)}")

    if not captured:
        print("[FAIL][兜底] worker 未返回结果（run 抛异常）")
        return 1
    if all_ok:
        print("\n=== 兜底分支通过：缓存无 codes 的排放口全部产生预测，未抛 NameError ===")
        return 0
    print("\n=== 兜底分支覆盖不全：存在排放口被跳过 ===")
    return 1


if __name__ == "__main__":
    rc1 = main()
    rc2 = main_fallback()
    sys.exit(rc1 or rc2)
