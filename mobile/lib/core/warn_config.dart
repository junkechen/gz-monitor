// v1.4.0 预警配置层：自定义阈值 / 声音 / 后台监测 / 微信推送
// SharedPreferences 持久化，前台与后台 isolate 共用同一份配置。
import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'constants.dart';

class WarnConfig {
  /// 自定义阈值：只保存覆盖默认值的项；键=归一化参数名，值=[下限, 上限]
  Map<String, List<double?>> customThresholds = {};

  bool soundOn = true; // 预警通知提示音
  bool backgroundOn = false; // 后台监测（前台服务）
  bool pushOn = false; // 微信推送总开关
  String pushChannel = 'pushplus'; // 'pushplus' | 'serverchan'
  String pushplusToken = '';
  String pushplusTopic = ''; // Pushplus 群组码；空=单推给自己
  String serverchanKey = ''; // Server酱 Turbo SendKey

  static const _kCustom = 'warn_custom_thresholds';
  static const _kSound = 'warn_sound_on';
  static const _kBackground = 'warn_background_on';
  static const _kPushOn = 'warn_push_on';
  static const _kPushChannel = 'warn_push_channel';
  static const _kPushplusToken = 'warn_pushplus_token';
  static const _kPushplusTopic = 'warn_pushplus_topic';
  static const _kServerchanKey = 'warn_serverchan_key';

  static Future<WarnConfig> load() async {
    final cfg = WarnConfig();
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_kCustom);
      if (raw != null && raw.isNotEmpty) {
        final m = jsonDecode(raw) as Map<String, dynamic>;
        m.forEach((k, v) {
          if (v is List && v.length == 2) {
            cfg.customThresholds[k] = [
              (v[0] as num?)?.toDouble(),
              (v[1] as num?)?.toDouble(),
            ];
          }
        });
      }
      cfg.soundOn = prefs.getBool(_kSound) ?? true;
      cfg.backgroundOn = prefs.getBool(_kBackground) ?? false;
      cfg.pushOn = prefs.getBool(_kPushOn) ?? false;
      cfg.pushChannel = prefs.getString(_kPushChannel) ?? 'pushplus';
      cfg.pushplusToken = prefs.getString(_kPushplusToken) ?? '';
      cfg.pushplusTopic = prefs.getString(_kPushplusTopic) ?? '';
      cfg.serverchanKey = prefs.getString(_kServerchanKey) ?? '';
    } catch (_) {}
    return cfg;
  }

  Future<void> save() async {
    final prefs = await SharedPreferences.getInstance();
    final m = <String, dynamic>{};
    customThresholds.forEach((k, v) => m[k] = v);
    await prefs.setString(_kCustom, jsonEncode(m));
    await prefs.setBool(_kSound, soundOn);
    await prefs.setBool(_kBackground, backgroundOn);
    await prefs.setBool(_kPushOn, pushOn);
    await prefs.setString(_kPushChannel, pushChannel);
    await prefs.setString(_kPushplusToken, pushplusToken);
    await prefs.setString(_kPushplusTopic, pushplusTopic);
    await prefs.setString(_kServerchanKey, serverchanKey);
  }

  /// 生效阈值：自定义覆盖优先，否则回退默认 kWarnThresholds；无配置返回 null
  List<double?>? thresholdFor(String name) {
    if (customThresholds.containsKey(name)) return customThresholds[name];
    return kWarnThresholds[name];
  }

  /// 推送配置是否完整（开关另判）
  bool get pushReady {
    if (pushChannel == 'pushplus') return pushplusToken.isNotEmpty;
    return serverchanKey.isNotEmpty;
  }
}
