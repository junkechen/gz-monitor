// 预警引擎：移植桌面端三类预警规则（阈值上下限 / 同值检测 / 急剧变化）
// 输入实时数据分组，输出并维护预警列表；状态可持久化（SharedPreferences）
import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'constants.dart';
import 'gz_api.dart';

enum WarnType { exceed, sameValue, rapidRise, rapidDrop }

extension WarnTypeX on WarnType {
  String get label {
    switch (this) {
      case WarnType.exceed:
        return '超标';
      case WarnType.sameValue:
        return '同值';
      case WarnType.rapidRise:
        return '急剧上升';
      case WarnType.rapidDrop:
        return '急剧下降';
    }
  }
}

class WarningItem {
  final String key; // 去重键 type|subid|code
  final WarnType type;
  final String entName;
  final String subid;
  final String subname;
  final String param; // 参数名
  final String value; // 当前值
  final String detail; // 附加说明
  final DateTime time;
  WarningItem({
    required this.key,
    required this.type,
    required this.entName,
    required this.subid,
    required this.subname,
    required this.param,
    required this.value,
    required this.detail,
    required this.time,
  });

  Map<String, dynamic> toJson() => {
        'key': key,
        'type': type.index,
        'ent': entName,
        'subid': subid,
        'subname': subname,
        'param': param,
        'value': value,
        'detail': detail,
        'time': time.millisecondsSinceEpoch,
      };

  static WarningItem fromJson(Map<String, dynamic> j) => WarningItem(
        key: j['key'] as String,
        type: WarnType.values[j['type'] as int],
        entName: (j['ent'] ?? '') as String,
        subid: (j['subid'] ?? '') as String,
        subname: (j['subname'] ?? '') as String,
        param: (j['param'] ?? '') as String,
        value: (j['value'] ?? '') as String,
        detail: (j['detail'] ?? '') as String,
        time: DateTime.fromMillisecondsSinceEpoch(j['time'] as int),
      );
}

/// v1.3.0：参数名归一化（与桌面端 v5.90 _norm_param_name 对齐）。
///
/// 实时接口 C0001_ITEM_NAME 带单位后缀且大小写不一（实测：「氨氮(mg/L)」
/// 「PH」「化学需氧量(mg/L)」「非甲烷总烃(mg/m3)」「碳氢化合物(总烃)(mg/m3)」），
/// 而 kWarnThresholds / kSameValueMinutes / kRapidChangePct 均为无单位键
/// （「氨氮」「pH值」「非甲烷总烃」…）。旧版直接用原始名查表，全部不命中 →
/// 本地阈值/同值/急变三类检测全部跳过（2026-11-28 冠洲氨氮持续上升
/// 无主动提醒的根因，与桌面端同源）。
///
/// 归一化策略：优先用监测项代码反查 kCodeToName（最可靠，code 已经
/// _normIdCode 规整数值格式）；无映射时剥离「(」起的单位后缀并去空白。
String normParamName(String code, String rawName) {
  if (code.isNotEmpty) {
    final byCode = codeName(code);
    if (byCode != null) return byCode;
  }
  final stripped = rawName.replaceAll(RegExp(r'\s*\(.*$'), '').trim();
  if (stripped.isNotEmpty) return stripped;
  return rawName.isNotEmpty ? rawName : code;
}

class _Obs {
  double? lastValue;
  DateTime? sameSince; // 同值起始时刻
  DateTime? lastRapidWarn; // 急变预警上次触发时刻
}

class WarningEngine {
  final List<WarningItem> items = []; // 历史记录（新在前）
  final Set<String> _active = {}; // 当前处于预警状态的去重键
  final Map<String, _Obs> _obs = {};
  int changeSerial = 0; // 每次新增预警自增，驱动角标动画

  /// v1.4.0：自定义阈值覆盖（键=归一化参数名，值=[下限, 上限]）。
  /// 由 WarnConfig.customThresholds 注入；命中覆盖默认 kWarnThresholds。
  Map<String, List<double?>> customThresholds = {};

  int get activeCount => _active.length;

  static const _prefItems = 'warn_items_v1';
  static const _prefObs = 'warn_obs_v1';

  Future<void> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_prefItems);
      if (raw != null) {
        final list = (jsonDecode(raw) as List)
            .whereType<Map>()
            .map((m) => WarningItem.fromJson(Map<String, dynamic>.from(m)))
            .toList();
        items
          ..clear()
          ..addAll(list);
      }
      final obsRaw = prefs.getString(_prefObs);
      if (obsRaw != null) {
        final m = jsonDecode(obsRaw) as Map<String, dynamic>;
        _obs.clear();
        m.forEach((k, v) {
          final o = _Obs();
          o.lastValue = (v['v'] as num?)?.toDouble();
          if (v['s'] != null) {
            o.sameSince = DateTime.fromMillisecondsSinceEpoch(v['s'] as int);
          }
          if (v['r'] != null) {
            o.lastRapidWarn =
                DateTime.fromMillisecondsSinceEpoch(v['r'] as int);
          }
          _obs[k] = o;
        });
        // 恢复同值/超标激活态（急变不跨重启恢复，避免旧数据误报）
        for (final it in items) {
          if (it.type == WarnType.exceed || it.type == WarnType.sameValue) {
            _active.add(it.key);
          }
        }
      }
    } catch (_) {}
  }

  Future<void> _persist() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_prefItems,
          jsonEncode(items.take(300).map((e) => e.toJson()).toList()));
      final obs = <String, dynamic>{};
      _obs.forEach((k, o) {
        obs[k] = {
          'v': o.lastValue,
          's': o.sameSince?.millisecondsSinceEpoch,
          'r': o.lastRapidWarn?.millisecondsSinceEpoch,
        };
      });
      await prefs.setString(_prefObs, jsonEncode(obs));
    } catch (_) {}
  }

  void clearAll() {
    items.clear();
    _active.clear();
    _obs.clear();
    changeSerial++;
    _persist();
  }

  void _add(WarningItem it) {
    _active.add(it.key);
    items.insert(0, it);
    if (items.length > 300) items.removeRange(300, items.length);
    changeSerial++;
  }

  /// 摄入一次实时数据，返回本次新增的预警
  List<WarningItem> ingest(List<OutletGroup> groups, {DateTime? now}) {
    final t = now ?? DateTime.now();
    final added = <WarningItem>[];
    final seenKeys = <String>{};

    for (final g in groups) {
      for (final p in g.params) {
        final v = double.tryParse(p.value ?? '');
        if (v == null || v == -9999) continue;
        final keyBase = '${g.subid}|${p.code}';
        seenKeys.add(keyBase);
        // v1.3.0：归一化后再查阈值/同值/急变配置——实时名带单位后缀
        // （氨氮(mg/L)、PH…），直接用原名查表全部不命中，检测被静默跳过
        final name = normParamName(p.code, p.name);

        // 1) 阈值上下限（自定义覆盖优先，v1.4.0）+ 服务端超标标记（CBBS）
        final th = customThresholds.containsKey(name)
            ? customThresholds[name]
            : kWarnThresholds[name];
        final bool overLocal = th != null &&
            ((th[0] != null && v < th[0]!) || (th[1] != null && v > th[1]!));
        final exceedKey = 'exceed|$keyBase';
        if (overLocal || p.isExceed) {
          if (!_active.contains(exceedKey)) {
            final lim = overLocal
                ? (th[0] != null && v < th[0]!
                    ? '低于下限 ${th[0]}'
                    : '超过限值 ${th[1]}')
                : '服务端超标标记';
            _add(WarningItem(
              key: exceedKey,
              type: WarnType.exceed,
              entName: g.entName,
              subid: g.subid,
              subname: g.subname,
              param: name,
              value: v.toString(),
              detail: lim,
              time: t,
            ));
            added.add(items.first);
          }
        } else {
          _active.remove(exceedKey);
        }

        // 2) 同值检测（阈值内的参数才参与）
        final sameMin = kSameValueMinutes[name];
        if (sameMin != null) {
          final o = _obs.putIfAbsent(keyBase, _Obs.new);
          if (o.lastValue != null && o.lastValue == v) {
            o.sameSince ??= t;
            final hold = t.difference(o.sameSince!).inMinutes;
            final sameKey = 'same|$keyBase';
            if (hold >= sameMin && !_active.contains(sameKey)) {
              _add(WarningItem(
                key: sameKey,
                type: WarnType.sameValue,
                entName: g.entName,
                subid: g.subid,
                subname: g.subname,
                param: name,
                value: v.toString(),
                detail: '连续 $hold 分钟保持 $v',
                time: t,
              ));
              added.add(items.first);
            }
          } else {
            o.sameSince = t;
            _active.remove('same|$keyBase');
          }
        }

        // 3) 急剧变化（相对上一个采样值）
        final pct = kRapidChangePct[name];
        if (pct != null) {
          final o = _obs.putIfAbsent(keyBase, _Obs.new);
          final prev = o.lastValue;
          if (prev != null && prev != 0 && prev != v) {
            final chg = (v - prev).abs() / prev.abs() * 100;
            final rapidKey = '${v > prev ? 'rapid-up' : 'rapid-down'}|$keyBase';
            final dedupOk = o.lastRapidWarn == null ||
                t.difference(o.lastRapidWarn!).inMinutes >= kRapidDedupeMinutes;
            if (chg >= pct && dedupOk && !_active.contains(rapidKey)) {
              o.lastRapidWarn = t;
              _add(WarningItem(
                key: rapidKey,
                type: v > prev ? WarnType.rapidRise : WarnType.rapidDrop,
                entName: g.entName,
                subid: g.subid,
                subname: g.subname,
                param: name,
                value: v.toString(),
                detail:
                    '${chg.toStringAsFixed(0)}%（$prev → $v），阈值 $pct%',
                time: t,
              ));
              added.add(items.first);
            }
          }
        }

        // 更新采样值（放在急变检测之后）
        _obs.putIfAbsent(keyBase, _Obs.new).lastValue = v;
      }
    }

    // 清理已消失参数的激活态
    _active.removeWhere((k) {
      final parts = k.split('|');
      if (parts.length < 3) return false;
      final subid = parts[1], code = parts[2];
      return !groups.any((g) =>
          g.subid == subid && g.params.any((p) => p.code == code));
    });

    if (added.isNotEmpty) _persist();
    return added;
  }
}

// OutletGroup 的 entName 字段在 gz_api.dart 中定义；此处仅引用。
