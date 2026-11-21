// 预警引擎单元测试（flutter test，纯合成数据，不依赖网络）
// 真实服务端网络链路验证见 tool/smoke.dart（dart run）
// 运行：flutter test test/smoke_test.dart -r expanded
import 'package:flutter_test/flutter_test.dart';
import 'package:gz_monitor_mobile/core/gz_api.dart';
import 'package:gz_monitor_mobile/core/warning_engine.dart';
import 'package:shared_preferences/shared_preferences.dart';

final _t0 = DateTime(2026, 11, 16, 7, 0, 0);
DateTime _t(int minutes) => _t0.add(Duration(minutes: minutes));

OutletGroup syntheticGroup({
  required String subid,
  required List<OutletParam> params,
  String subname = '合成测试排口',
  String entName = '合成测试企业',
}) {
  return OutletGroup(
    subid: subid,
    subname: subname,
    subtypeText: 'VOCs',
    datetime: '2026-11-16 07:00:00',
    status: '正常',
    params: params,
    itemCodes: params.map((p) => p.code).toSet(),
    entName: entName,
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  // WarningEngine 持久化使用 SharedPreferences，测试环境用 mock
  SharedPreferences.setMockInitialValues({});

  test('超标：本地阈值 + 服务端标记双通道，重复摄入去重', () {
    final engine = WarningEngine();
    final g = syntheticGroup(
      subid: '90001',
      params: [
        // 非甲烷总烃 80.5 > 限值 50 → 本地阈值超标
        OutletParam(name: '非甲烷总烃', code: '383', value: '80.5', std: '50', isExceed: false),
        // pH 10.2 > 上限 9 → 本地阈值超标
        OutletParam(name: 'pH值', code: '302', value: '10.2', std: '', isExceed: false),
        // 未知参数但服务端标记超标 → 服务端通道
        OutletParam(name: '未知参数', code: '999', value: '1.0', std: '', isExceed: true),
      ],
    );
    final fresh = engine.ingest([g], now: _t(0));
    expect(fresh.length, 3, reason: '两条本地阈值超标 + 一条服务端标记超标');
    expect(fresh.every((w) => w.type == WarnType.exceed), isTrue);
    // 去重：同值重复摄入不再报
    final fresh2 = engine.ingest([g], now: _t(5));
    expect(fresh2.length, 0, reason: '同值重复摄入不应重复报警');
  });

  test('同值检测：持续超窗口触发一次，激活期内不重复', () {
    final engine = WarningEngine();
    OutletParam p(String v) =>
        OutletParam(name: '非甲烷总烃', code: '383', value: v, std: '', isExceed: false);
    final g1 = syntheticGroup(subid: '90002', params: [p('42.0')]);
    engine.ingest([g1], now: _t(0)); // 首采样，记录同值起点
    final g2 = syntheticGroup(subid: '90002', params: [p('42.0')]);
    final fresh = engine.ingest([g2], now: _t(35)); // 同值 35 分钟 ≥ 30 分钟窗口
    expect(fresh.where((w) => w.type == WarnType.sameValue).length, 1,
        reason: '同值持续 35 分钟（≥30 分钟窗口）应触发一次同值预警');
    final g3 = syntheticGroup(subid: '90002', params: [p('42.0')]);
    final fresh3 = engine.ingest([g3], now: _t(40));
    expect(fresh3.where((w) => w.type == WarnType.sameValue).length, 0,
        reason: '同值预警激活期内不重复报警');
  });

  test('急剧下降：-94% 超过 50% 阈值', () {
    final engine = WarningEngine();
    OutletParam p(String v) =>
        OutletParam(name: '非甲烷总烃', code: '383', value: v, std: '50', isExceed: false);
    final g1 = syntheticGroup(subid: '90003', params: [p('80.5')]);
    engine.ingest([g1], now: _t(0));
    final g2 = syntheticGroup(subid: '90003', params: [p('5.0')]);
    final fresh = engine.ingest([g2], now: _t(10));
    expect(fresh.length, 1, reason: '浓度 80.5→5.0（-94%）应触发急剧下降预警');
    expect(fresh.first.type, WarnType.rapidDrop);
    expect(fresh.first.detail, contains('80.5 → 5.0'));
  });

  test('急剧上升 + 10 分钟去重窗口', () {
    final engine = WarningEngine();
    OutletParam p(String v) =>
        OutletParam(name: '非甲烷总烃', code: '383', value: v, std: '', isExceed: false);
    final g1 = syntheticGroup(subid: '90004', params: [p('10.0')]);
    engine.ingest([g1], now: _t(0));
    final g2 = syntheticGroup(subid: '90004', params: [p('20.0')]);
    final fresh = engine.ingest([g2], now: _t(5));
    expect(fresh.length, 1, reason: '+100% 应触发急剧上升');
    expect(fresh.first.type, WarnType.rapidRise);
    // 3 分钟后再次急变：处于 10 分钟去重窗口内，不重复报
    final g3 = syntheticGroup(subid: '90004', params: [p('40.0')]);
    final fresh3 = engine.ingest([g3], now: _t(8));
    expect(fresh3.where((w) => w.type == WarnType.rapidRise).length, 0,
        reason: '10 分钟去重窗口内不重复报急变');
  });

  test('持久化往返：items 恢复、超标激活态保持', () async {
    final engine = WarningEngine();
    OutletParam p(String v) =>
        OutletParam(name: '非甲烷总烃', code: '383', value: v, std: '50', isExceed: false);
    final g1 = syntheticGroup(subid: '90005', params: [p('80.5')]);
    engine.ingest([g1], now: _t(0));
    expect(engine.items.length, 1);
    await Future<void>.delayed(const Duration(milliseconds: 100)); // 等 _persist 完成

    // 新引擎从持久化恢复：同值再摄入不应重复报（超标仍激活）
    final engine2 = WarningEngine();
    await engine2.load();
    expect(engine2.items.length, 1, reason: '持久化 items 应完整恢复');
    final g2 = syntheticGroup(subid: '90005', params: [p('80.5')]);
    final fresh = engine2.ingest([g2], now: _t(5));
    expect(fresh.where((w) => w.type == WarnType.exceed).length, 0,
        reason: '恢复激活态后同值超标不重复报');
  });

  test('排口消失清理激活态 + 清空', () {
    final engine = WarningEngine();
    OutletParam p(String v) =>
        OutletParam(name: '非甲烷总烃', code: '383', value: v, std: '50', isExceed: false);
    final g1 = syntheticGroup(subid: '90006', params: [p('80.5')]);
    engine.ingest([g1], now: _t(0));
    expect(engine.items, isNotEmpty);
    // 排口 90006 从数据中消失 → 激活态清理
    final other = syntheticGroup(
      subid: '90007',
      params: [OutletParam(name: '非甲烷总烃', code: '383', value: '10.0', std: '50', isExceed: false)],
    );
    engine.ingest([other], now: _t(10));
    // 再次超标应重新报（激活态已被清理）
    final back = syntheticGroup(subid: '90006', params: [p('80.5')]);
    final fresh = engine.ingest([back], now: _t(20));
    expect(fresh.where((w) => w.type == WarnType.exceed).length, 1,
        reason: '排口消失后激活态清理，再次超标应重新报警');

    engine.clearAll();
    expect(engine.items, isEmpty);
    expect(engine.activeCount, 0);
  });

  test('历史排放量：服务端 ex_ 权威值直读，禁止本地重算', () {
    // 日数据：服务端 ex_ 为吨 → kg；无 ex 返回 0（不回退浓度×流量）
    final dayRow = {'ex_316': '0.00609', 'val_316': '9.77', 'val_494': '623'};
    expect(dayEmissionKg(dayRow, '316', '494'), closeTo(6.09, 0.001),
        reason: '日排放量 = 服务端 ex_ 吨值 ×1000');
    final noEx = {'val_316': '9.77', 'val_494': '623'};
    expect(dayEmissionKg(noEx, '316', '494'), 0.0,
        reason: '无服务端 ex_ 时返回 0，禁止用浓度×流量本地重算');
    // 小时数据：服务端 ex_ 为 kg 直读
    final hourRow = {'ex_383': '0.011', 'val_383': '1.98', 'val_210': '5000'};
    expect(hourEmissionKg(hourRow, '383'), closeTo(0.011, 0.0001),
        reason: '小时排放量 = 服务端 ex_ kg 值直读');
    // 脏数据防护：维护时段残留的异常巨值不得采信
    final dirty = {'ex_220': '188402703'};
    expect(hourEmissionKg(dirty, '220'), 0.0,
        reason: '超过硬上限的脏排放量返回 0');
  });
}
