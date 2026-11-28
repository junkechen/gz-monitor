// v1.4.0 本地通知：预警系统通知（提示音可开关），前台/后台 isolate 均可调用。
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'warning_engine.dart';

class NotifyService {
  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  static const _channelSound = 'gz_warn_sound';
  static const _channelMute = 'gz_warn_mute';
  static const _warnNotifId = 9001;

  static Future<void> init() async {
    const settings = InitializationSettings(
      android: AndroidInitializationSettings('@mipmap/ic_launcher'),
    );
    await _plugin.initialize(settings: settings);
  }

  /// Android 13+ 运行时通知权限
  static Future<void> requestPermission() async {
    await _plugin
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.requestNotificationsPermission();
  }

  /// 弹预警汇总通知（多条合并一条，Inbox 展开）。
  /// sound=true 走有声渠道（系统默认提示音+震动），false 走静默渠道。
  static Future<void> showWarnings(
      List<WarningItem> items, {required bool sound}) async {
    if (items.isEmpty) return;
    await init(); // 后台 isolate 每次独立初始化，前台重复初始化无副作用
    final first = items.first;
    final title = items.length == 1
        ? '${first.param}${first.type.label}预警'
        : '新增 ${items.length} 条安环预警';
    final body = '${first.entName} ${first.subname} '
        '${first.param} ${first.value}';
    final lines = items
        .take(6)
        .map((w) => '${w.subname} ${w.param} ${w.type.label} ${w.value}')
        .toList();
    final details = NotificationDetails(
      android: AndroidNotificationDetails(
        sound ? _channelSound : _channelMute,
        sound ? '安环预警（有声）' : '安环预警（静默）',
        channelDescription: '排口超标/同值/急剧变化预警',
        importance: Importance.max,
        priority: Priority.high,
        playSound: sound,
        enableVibration: sound,
        styleInformation: InboxStyleInformation(lines),
      ),
    );
    await _plugin.show(
        id: _warnNotifId, title: title, body: body, notificationDetails: details);
  }
}
