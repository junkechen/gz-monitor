// v1.4.0 后台监测：Android 前台服务（specialUse 类型，避开 dataSync 6h/天限制）。
// 后台 isolate 每 60s：按需自动登录（内置账号+自动滑块）→ 合并实时数据 →
// 预警引擎 → 系统通知（可带提示音）+ 微信推送。配置每轮重读，前台改即生效。
import 'dart:async';

import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'account_manager.dart';
import 'constants.dart';
import 'notify_service.dart';
import 'push_service.dart';
import 'warn_config.dart';
import 'warning_engine.dart';

/// 后台任务入口（必须顶层函数 + vm:entry-point，供 isolate 反射调用）
@pragma('vm:entry-point')
void monitorCallback() {
  FlutterForegroundTask.setTaskHandler(MonitorTaskHandler());
}

class BackgroundMonitor {
  static void init() {
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'gz_monitor_bg',
        channelName: '后台监测服务',
        channelDescription: '保持实时数据监测与预警在后台运行',
        onlyAlertOnce: true,
      ),
      iosNotificationOptions: const IOSNotificationOptions(),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.repeat(60000), // 60s 一轮
        autoRunOnBoot: false,
        allowWakeLock: true,
        allowWifiLock: true,
      ),
    );
  }

  /// 启动后台监测；返回 null=成功，否则错误信息。
  static Future<String?> start() async {
    init();
    var perm = await FlutterForegroundTask.checkNotificationPermission();
    if (perm != NotificationPermission.granted) {
      perm = await FlutterForegroundTask.requestNotificationPermission();
      if (perm != NotificationPermission.granted) {
        return '需要通知权限才能后台报警，请在系统设置中允许通知';
      }
    }
    if (await FlutterForegroundTask.isRunningService) {
      return null; // 已在运行
    }
    final r = await FlutterForegroundTask.startService(
      serviceTypes: const [ForegroundServiceTypes.specialUse],
      notificationTitle: 'GZ安环监测 · 后台运行中',
      notificationText: '每分钟自动拉取实时数据并预警',
      callback: monitorCallback,
    );
    return r is ServiceRequestSuccess ? null : '后台服务启动失败：$r';
  }

  static Future<void> stop() async {
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.stopService();
    }
  }
}

class MonitorTaskHandler extends TaskHandler {
  AccountManager? _manager;
  final WarningEngine _engine = WarningEngine();
  WarnConfig _cfg = WarnConfig();
  bool _busy = false;

  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {
    _cfg = await WarnConfig.load();
    _engine.customThresholds = _cfg.customThresholds;
    await _engine.load();
  }

  Future<List<Map<String, String>>> _selectedAccounts() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getStringList('login_accounts');
    final names = (saved == null || saved.isEmpty)
        ? kBuiltinAccounts.map((a) => a['name']!).toList()
        : saved;
    return [
      for (final a in kBuiltinAccounts)
        if (names.contains(a['name'])) a,
    ];
  }

  void _updateNotice(String text) {
    unawaited(FlutterForegroundTask.updateService(
      notificationTitle: 'GZ安环监测 · 后台运行中',
      notificationText: text,
    ));
  }

  Future<void> _tick() async {
    if (_busy) return;
    _busy = true;
    try {
      // 每轮重读配置：前台修改阈值/开关，后台立即生效
      _cfg = await WarnConfig.load();
      _engine.customThresholds = _cfg.customThresholds;

      final accounts = await _selectedAccounts();
      if (accounts.isEmpty) {
        _updateNotice('未选择账号，请打开 APP 登录');
        return;
      }
      if (_manager == null) {
        final m = AccountManager();
        await m.loginAll(accounts);
        if (!m.isLoggedIn) {
          _updateNotice('登录失败，下一分钟自动重试');
          return;
        }
        _manager = m;
      }
      var groups = await _manager!.fetchMergedRealtime();
      if (groups.isEmpty) {
        // 会话可能过期：重登再拉一次
        await _manager!.loginAll(accounts);
        groups = await _manager!.fetchMergedRealtime();
      }
      final fresh = _engine.ingest(groups);
      if (fresh.isNotEmpty) {
        await NotifyService.showWarnings(fresh, sound: _cfg.soundOn);
        await PushService.send(_cfg, fresh); // 推送失败不阻断本地预警
      }
      final now = DateTime.now();
      final hhmm = '${now.hour.toString().padLeft(2, '0')}:'
          '${now.minute.toString().padLeft(2, '0')}';
      _updateNotice('$hhmm 已检查 · ${groups.length} 排口 · '
          '活跃预警 ${_engine.activeCount} 条');
    } catch (e) {
      _updateNotice('监测异常：$e');
    } finally {
      _busy = false;
    }
  }

  @override
  void onRepeatEvent(DateTime timestamp) {
    unawaited(_tick());
  }

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async {}
}
