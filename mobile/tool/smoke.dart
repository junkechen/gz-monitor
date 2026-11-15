// 冒烟测试：真实服务端全链路验证（纯 Dart，可 dart run 直连网络）
// v1.1：多账号登录 → 合并实时 → subid 路由 → 跨企业历史查询
// 运行：dart run tool/smoke.dart （须在 ASCII 路径目录，如 D:\GZMobile）
// 预警引擎用例见 test/smoke_test.dart（flutter test，含合成用例与持久化验证）
import 'package:gz_monitor_mobile/core/account_manager.dart';
import 'package:gz_monitor_mobile/core/constants.dart';
import 'package:gz_monitor_mobile/core/gz_api.dart';

Future<void> main() async {
  final manager = AccountManager();

  // ── 1. 多账号登录（取前 2 个账号验证合并链路，避免全量登录触发风控）──
  final accounts = kBuiltinAccounts.take(2).toList();
  print('== 多账号登录 (${accounts.length} 个)');
  final outcomes = await manager.loginAll(accounts,
      progress: (acc, idx, total, msg) =>
          print('  [$idx/$total] $acc  $msg'));
  final okCount = outcomes.where((o) => o.ok).length;
  print('登录成功: $okCount/${accounts.length}');
  if (okCount == 0) {
    print('全部登录失败，终止');
    return;
  }

  // ── 2. 合并实时数据 + subid 路由 ──
  print('== 合并实时数据');
  final groups = await manager.fetchMergedRealtime();
  manager.buildRoutes();
  final ents = groups.map((g) => g.entName).toSet();
  print('排口数: ${groups.length}  企业数: ${ents.length}');
  for (final g in groups) {
    print(
        '  [${g.entName}] subid=${g.subid} ${g.subname} [${g.subtypeText}] codes=${g.itemCodes.length} status=${g.status}');
  }
  final firstSub = groups.first;
  print('路由验证: clientFor(${firstSub.subid}) -> ${manager.clientFor(firstSub.subid) != null ? "OK" : "FAIL"}');

  // ── 3. 跨企业历史查询（用第一个企业的排口查日数据）──
  final gas = groups.where((g) => !g.isWater).toList();
  final target = gas.isNotEmpty ? gas.first : groups.first;
  final codes = target.itemCodes.isNotEmpty
      ? target.itemCodes.join(',')
      : (target.isWater
          ? kDefaultWaterCodes.join(',')
          : kDefaultGasCodes.join(','));
  print('== 历史日数据: [${target.entName}] subid=${target.subid} subtype=${target.subtypeCode}');
  final client = manager.clientFor(target.subid);
  if (client == null) {
    print('路由失败，终止');
    return;
  }
  final res = await client.queryHistory(
    subid: target.subid,
    subtype: target.subtypeCode,
    codes: codes,
    start: '2026-11-02',
    end: '2026-11-08',
    index: 2,
  );
  final rows = (res['rows'] as List).whereType<Map>().toList();
  print('日数据行数: ${rows.length} total=${res['total']}');
  final mainCode = target.isWater ? kWaterEmissionCode : kGasEmissionCode;
  final flowCode = target.isWater ? null : '210';
  double total = 0;
  for (final r in rows) {
    final kg = dayEmissionKg(r, mainCode, flowCode);
    total += kg;
  }
  print('排放量合计: ${total.toStringAsFixed(3)} kg');
  final pass = okCount >= 1 && groups.isNotEmpty && rows.length >= 5 && total > 1;
  print(pass ? 'SMOKE OK' : 'SMOKE CHECK: 结果异常，请人工核对');
}
