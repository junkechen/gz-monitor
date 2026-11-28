// 主页：底部导航（实时数据 / 预警 / 历史查询），预警角标
import 'package:flutter/material.dart';

import '../core/account_manager.dart';
import '../core/gz_api.dart';
import '../core/notify_service.dart';
import '../core/push_service.dart';
import '../core/warn_config.dart';
import '../core/warning_engine.dart';
import 'realtime_page.dart';
import 'history_page.dart';
import 'settings_page.dart';
import 'warning_page.dart';

class HomePage extends StatefulWidget {
  final AccountManager manager;
  const HomePage({super.key, required this.manager});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  int _tab = 0;
  List<OutletGroup>? _outlets; // 合并后的排口（供历史页选择）
  final WarningEngine _engine = WarningEngine();
  WarnConfig _cfg = WarnConfig();

  @override
  void initState() {
    super.initState();
    _engine.load();
    WarnConfig.load().then((cfg) {
      _cfg = cfg;
      _engine.customThresholds = cfg.customThresholds;
    });
    NotifyService.init();
    NotifyService.requestPermission(); // Android 13+ 通知权限
  }

  void _onOutletsLoaded(List<OutletGroup> g) {
    _outlets = g;
  }

  void _onWarnings(List<WarningItem> fresh) {
    if (!mounted) return;
    setState(() {});
    if (fresh.isNotEmpty) {
      // v1.4.0：系统通知（提示音可关）+ 微信推送，失败均不阻断
      NotifyService.showWarnings(fresh, sound: _cfg.soundOn);
      PushService.send(_cfg, fresh);
    }
    if (fresh.isNotEmpty && _tab != 1) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text('⚠ 新增 ${fresh.length} 条预警：'
            '${fresh.first.param} ${fresh.first.type.label}'),
        backgroundColor: const Color(0xFF7A2E2E),
        duration: const Duration(seconds: 3),
      ));
    }
  }

  Future<void> _logout() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('退出登录'),
        content: Text(
            '确定退出全部 ${widget.manager.clientCount} 个企业账号吗？\n预警记录将保留在本机。'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('退出')),
        ],
      ),
    );
    if (ok == true && mounted) {
      widget.manager.logoutAll();
      Navigator.of(context).popUntil((r) => r.isFirst);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          'GZ安环监测 · ${widget.manager.loggedInNames.length} 企业',
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontSize: 17),
        ),
        actions: [
          IconButton(
              icon: const Icon(Icons.settings_outlined),
              tooltip: '预警设置',
              onPressed: () async {
                await Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => SettingsPage(engine: _engine),
                ));
                // 设置页可能改了推送/声音配置，回来重读
                _cfg = await WarnConfig.load();
                _engine.customThresholds = _cfg.customThresholds;
              }),
          IconButton(icon: const Icon(Icons.logout), onPressed: _logout,
              tooltip: '退出登录'),
        ],
      ),
      body: IndexedStack(
        index: _tab,
        children: [
          RealtimePage(
            manager: widget.manager,
            engine: _engine,
            onOutletsLoaded: _onOutletsLoaded,
            onWarnings: _onWarnings,
          ),
          WarningPage(engine: _engine),
          HistoryPage(manager: widget.manager, outlets: _outlets),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: [
          const NavigationDestination(
              icon: Icon(Icons.monitor_heart_outlined),
              selectedIcon: Icon(Icons.monitor_heart),
              label: '实时数据'),
          NavigationDestination(
            icon: Badge(
              isLabelVisible: _engine.activeCount > 0,
              label: Text('${_engine.activeCount}'),
              backgroundColor: const Color(0xFFF85149),
              child: const Icon(Icons.notification_important_outlined),
            ),
            selectedIcon: Badge(
              isLabelVisible: _engine.activeCount > 0,
              label: Text('${_engine.activeCount}'),
              backgroundColor: const Color(0xFFF85149),
              child: const Icon(Icons.notification_important),
            ),
            label: '预警',
          ),
          const NavigationDestination(
              icon: Icon(Icons.query_stats_outlined),
              selectedIcon: Icon(Icons.query_stats),
              label: '历史查询'),
        ],
      ),
    );
  }
}
