// 冒烟测试：真实服务端全链路验证（登录→实时→历史→排放量）
// 运行：dart run tool/smoke.dart
import 'package:gz_monitor_mobile/core/constants.dart';
import 'package:gz_monitor_mobile/core/gz_api.dart';

Future<void> main() async {
  final api = GzApi();
  final acc = kBuiltinAccounts[1]; // 山东冠洲鼎鑫板材科技有限公司
  print('== 登录: ${acc['name']}');
  final err = await api.login(acc['name']!, acc['password']!,
      onProgress: (m) => print('  $m'));
  if (err != null) {
    print('登录失败: $err');
    return;
  }
  print('登录成功');

  print('== 实时数据');
  final groups = await api.fetchRealtimeGroups();
  print('排口数: ${groups.length}');
  for (final g in groups) {
    print(
        '  subid=${g.subid} ${g.subname} [${g.subtypeText}] codes=${g.itemCodes.join(",")} status=${g.status} params=${g.params.length}');
  }

  if (groups.isEmpty) return;

  // 找一个 VOCs/废气排口查日数据（验证吨→kg）
  final gas = groups.where((g) => !g.isWater).toList();
  final target = gas.isNotEmpty ? gas.first : groups.first;
  final codes = target.itemCodes.isNotEmpty
      ? target.itemCodes.join(',')
      : (target.isWater ? kDefaultWaterCodes.join(',') : kDefaultGasCodes.join(','));
  print('== 历史日数据: subid=${target.subid} subtype=${target.subtypeCode} codes=$codes');
  final res = await api.queryHistory(
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
    print(
        '  ${r['DateTime']} val_$mainCode=${r['val_$mainCode']} ex_$mainCode=${r['ex_$mainCode']} -> $kg kg');
  }
  print('排放量合计: ${total.toStringAsFixed(3)} kg');
  print(total > 10 ? 'SMOKE OK' : 'SMOKE CHECK: 合计偏低，请人工核对');
}
