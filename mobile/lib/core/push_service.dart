// v1.4.0 微信消息推送：Pushplus（推荐，支持群组推送）/ Server酱 Turbo（单推）
//
// 说明：普通微信群聊没有官方机器人接口，本模块走「公众号消息提醒」通道：
// - Pushplus：token 单推；填 topic（群组码）则推给群组全部成员，
//   成员各自普通微信收到「pushplus 推送加」公众号消息（有提醒音）。
// - Server酱 Turbo：SendKey 单推到「方糖服务号」。
import 'dart:convert';

import 'package:dio/dio.dart';

import 'warn_config.dart';
import 'warning_engine.dart';

/// 预警内容排版（纯函数，便于单测）
String formatWarningsText(List<WarningItem> items) {
  final lines = <String>[];
  for (final w in items.take(8)) {
    final ent = w.entName.isNotEmpty ? w.entName : '未知企业';
    lines.add('【${w.type.label}】$ent ${w.subname}\n'
        '${w.param}：${w.value}（${w.detail}）\n'
        '${w.time.hour.toString().padLeft(2, '0')}:'
        '${w.time.minute.toString().padLeft(2, '0')}');
  }
  if (items.length > 8) lines.add('……另有 ${items.length - 8} 条，请打开 APP 查看');
  return lines.join('\n\n');
}

class PushService {
  /// 发送预警推送。null=成功或未启用；非 null=错误信息（不阻断本地预警）。
  static Future<String?> send(WarnConfig cfg, List<WarningItem> items) async {
    if (!cfg.pushOn || items.isEmpty) return null;
    if (!cfg.pushReady) return '推送未配置 token/key';
    final title = 'GZ安环预警 ${items.length} 条';
    final content = formatWarningsText(items);
    try {
      if (cfg.pushChannel == 'pushplus') {
        return await _pushplus(cfg, title, content);
      }
      return await _serverchan(cfg, title, content);
    } catch (e) {
      return '推送异常: $e';
    }
  }

  /// 配置测试：发一条测试消息，返回可读结果（不修改配置对象）。
  static Future<String> test(WarnConfig cfg) async {
    if (!cfg.pushReady) return '请先填写 token/key 并保存';
    final fake = WarningItem(
      key: 'test|0|0',
      type: WarnType.exceed,
      entName: '测试企业',
      subid: '0',
      subname: '测试排口',
      param: '氨氮',
      value: '16.0',
      detail: '这是一条推送配置测试消息',
      time: DateTime.now(),
    );
    try {
      final err = cfg.pushChannel == 'pushplus'
          ? await _pushplus(cfg, 'GZ安环推送测试', formatWarningsText([fake]))
          : await _serverchan(cfg, 'GZ安环推送测试', formatWarningsText([fake]));
      return err == null ? '测试消息已发送，请检查微信是否收到' : '发送失败：$err';
    } catch (e) {
      return '推送异常: $e';
    }
  }

  static Future<String?> _pushplus(
      WarnConfig cfg, String title, String content) async {
    final dio = Dio(BaseOptions(
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 20),
    ));
    final body = <String, dynamic>{
      'token': cfg.pushplusToken,
      'title': title,
      'content': content,
      'template': 'txt',
    };
    if (cfg.pushplusTopic.isNotEmpty) body['topic'] = cfg.pushplusTopic;
    final r = await dio.post(
      'https://www.pushplus.plus/send',
      data: jsonEncode(body),
      options: Options(contentType: 'application/json'),
    );
    final data = r.data is String ? jsonDecode(r.data as String) : r.data;
    if (data is Map && data['code'] == 200) return null;
    return 'pushplus: ${data is Map ? (data['msg'] ?? data) : data}';
  }

  static Future<String?> _serverchan(
      WarnConfig cfg, String title, String content) async {
    final dio = Dio(BaseOptions(
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 20),
    ));
    final r = await dio.post(
      'https://sctapi.ftqq.com/${cfg.serverchanKey}.send',
      data: {'title': title, 'desp': content},
      options: Options(contentType: Headers.formUrlEncodedContentType),
    );
    final data = r.data is String ? jsonDecode(r.data as String) : r.data;
    if (data is Map && data['code'] == 0) return null;
    return 'serverchan: ${data is Map ? (data['message'] ?? data) : data}';
  }
}
