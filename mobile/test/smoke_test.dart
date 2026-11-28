// 预警引擎单元测试（flutter test，纯合成数据，不依赖网络）
// 真实服务端网络链路验证见 tool/smoke.dart（dart run）
// 运行：flutter test test/smoke_test.dart -r expanded
import 'package:flutter_test/flutter_test.dart';
import 'package:gz_monitor_mobile/core/constants.dart';
import 'package:gz_monitor_mobile/core/gz_api.dart';
import 'package:gz_monitor_mobile/core/push_service.dart';
import 'package:gz_monitor_mobile/core/warn_config.dart';
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

  // ── v1.3.0：真实接口参数名（带单位后缀）回归 ─────────────────────────
  // 旧版直接用 C0001_ITEM_NAME 原始名查阈值表，「氨氮(mg/L)」「PH」等
  // 全部不命中 → 本地预警静默失效（与桌面端 v5.90 同源 bug）。

  test('参数名归一化：code 优先反查，无 code 剥括号后缀', () {
    expect(normParamName('311', '氨氮(mg/L)'), '氨氮');
    expect(normParamName('302', 'PH'), 'pH值', reason: 'PH 原名大小写不符，须 code 反查');
    expect(normParamName('383', '非甲烷总烃(mg/m3)'), '非甲烷总烃');
    expect(normParamName('220', '碳氢化合物(总烃)(mg/m3)'), '碳氢化合物总烃',
        reason: '双括号名必须走 code 反查，剥括号会剥成「碳氢化合物」');
    expect(normParamName('', '氨氮(mg/L)'), '氨氮', reason: '无 code 时剥单位后缀');
    expect(normParamName('999', '某未知参数(mg/L)'), '某未知参数');
  });

  test('真实参数名：氨氮(mg/L) 16.0 触发本地超标（阈值 15）', () {
    final engine = WarningEngine();
    final g = syntheticGroup(
      subid: '1716',
      params: [OutletParam(name: '氨氮(mg/L)', code: '311', value: '16.0', std: '15', isExceed: false)],
    );
    final fresh = engine.ingest([g], now: _t(0));
    expect(fresh.where((w) => w.type == WarnType.exceed).length, 1,
        reason: '带单位后缀的实时名也必须命中本地阈值（旧版静默跳过）');
    expect(fresh.first.param, '氨氮', reason: '预警记录参数名为归一化后的无单位名');
    // PH 走 code 反查 pH值，10.2 > 上限 9
    final g2 = syntheticGroup(
      subid: '1716',
      params: [OutletParam(name: 'PH', code: '302', value: '10.2', std: '', isExceed: false)],
    );
    final fresh2 = engine.ingest([g2], now: _t(1));
    expect(fresh2.where((w) => w.type == WarnType.exceed).length, 1);
    expect(fresh2.first.param, 'pH值');
  });

  test('真实参数名：氨氮 3.01→8.9 触发急剧上升（196%）', () {
    // 2026-11-28 冠洲废水总排口实测阶梯上升片段
    final engine = WarningEngine();
    OutletParam p(String v) =>
        OutletParam(name: '氨氮(mg/L)', code: '311', value: v, std: '12', isExceed: false);
    engine.ingest([syntheticGroup(subid: '1716', params: [p('3.01')])], now: _t(0));
    final fresh = engine.ingest(
        [syntheticGroup(subid: '1716', params: [p('8.90')])], now: _t(60));
    expect(fresh.where((w) => w.type == WarnType.rapidRise).length, 1,
        reason: '(8.9-3.01)/3.01≈196% ≥ 氨氮 30% 阈值，应触发急剧上升');
    expect(fresh.first.param, '氨氮');
    expect(fresh.first.detail, contains('3.01 → 8.9'));
  });

  test('真实参数名：氨氮(mg/L) 同值持续 185 分钟触发同值预警', () {
    final engine = WarningEngine();
    OutletParam p(String v) =>
        OutletParam(name: '氨氮(mg/L)', code: '311', value: v, std: '', isExceed: false);
    engine.ingest([syntheticGroup(subid: '1716', params: [p('5.0')])], now: _t(0));
    final fresh = engine.ingest(
        [syntheticGroup(subid: '1716', params: [p('5.0')])], now: _t(185));
    expect(fresh.where((w) => w.type == WarnType.sameValue).length, 1,
        reason: '同值 185 分钟 ≥ 氨氮 180 分钟窗口');
  });

  // ── v1.4.0：自定义阈值 / 配置持久化 / 推送文本 ─────────────────────────

  test('自定义阈值覆盖默认：氨氮上限改为 5，8.9 也超标', () {
    final engine = WarningEngine();
    engine.customThresholds = {
      '氨氮': [null, 5.0]
    };
    final g = syntheticGroup(
      subid: '1716',
      params: [OutletParam(name: '氨氮(mg/L)', code: '311', value: '8.9', std: '12', isExceed: false)],
    );
    final fresh = engine.ingest([g], now: _t(0));
    expect(fresh.where((w) => w.type == WarnType.exceed).length, 1,
        reason: '默认上限 15 不超标，但自定义上限 5 应超标');
    expect(fresh.first.detail, contains('超过限值 5.0'));
    // 自定义下限也生效：pH 下限自定义为 7，6.5 低于下限
    final engine2 = WarningEngine();
    engine2.customThresholds = {
      'pH值': [7.0, 9.0]
    };
    final g2 = syntheticGroup(
      subid: '1716',
      params: [OutletParam(name: 'PH', code: '302', value: '6.5', std: '', isExceed: false)],
    );
    final fresh2 = engine2.ingest([g2], now: _t(0));
    expect(fresh2.where((w) => w.type == WarnType.exceed).length, 1);
    expect(fresh2.first.detail, contains('低于下限 7.0'));
  });

  test('配置持久化往返：自定义阈值/声音/推送字段 + 恢复默认回退', () async {
    final cfg = WarnConfig();
    cfg.customThresholds = {
      '氨氮': [null, 5.0],
      'pH值': [5.0, 10.0]
    };
    cfg.soundOn = false;
    cfg.pushplusToken = 'tk';
    cfg.pushplusTopic = 'tp';
    await cfg.save();
    final cfg2 = await WarnConfig.load();
    expect(cfg2.customThresholds['氨氮']![1], 5.0);
    expect(cfg2.thresholdFor('pH值'), [5.0, 10.0]);
    expect(cfg2.thresholdFor('化学需氧量'), kWarnThresholds['化学需氧量'],
        reason: '未覆盖参数回退默认');
    expect(cfg2.soundOn, false);
    expect(cfg2.pushplusToken, 'tk');
    expect(cfg2.pushplusTopic, 'tp');
    expect(cfg2.pushReady, true);
    cfg2.customThresholds.remove('氨氮');
    expect(cfg2.thresholdFor('氨氮'), kWarnThresholds['氨氮'], reason: '移除覆盖后恢复默认');
  });

  test('推送文本排版：8 条截断 + 超出计数', () {
    final items = List.generate(
        10,
        (i) => WarningItem(
            key: 'k$i',
            type: WarnType.exceed,
            entName: '企业',
            subid: '1',
            subname: '排口$i',
            param: '氨氮',
            value: '16.0',
            detail: '超过限值 15',
            time: _t(0)));
    final text = formatWarningsText(items);
    expect(text, contains('【超标】'));
    expect(text, contains('排口0'));
    expect(text, contains('排口7'));
    expect(text, isNot(contains('排口8')), reason: '第 9 条起截断');
    expect(text, contains('另有 2 条'));
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
