// 主页：底部导航（实时数据 / 历史查询）
import 'package:flutter/material.dart';

import '../core/gz_api.dart';
import 'realtime_page.dart';
import 'history_page.dart';

class HomePage extends StatefulWidget {
  final GzApi api;
  final String enterpriseName;
  const HomePage({super.key, required this.api, required this.enterpriseName});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  int _tab = 0;
  List<OutletGroup>? _outlets; // 实时数据解析出的排口（供历史页选择）

  void _onOutletsLoaded(List<OutletGroup> g) {
    _outlets = g;
  }

  Future<void> _logout() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('退出登录'),
        content: Text('确定退出「${widget.enterpriseName}」吗？'),
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
      widget.api.loggedIn = false;
      Navigator.of(context).popUntil((r) => r.isFirst);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.enterpriseName,
            overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 17)),
        actions: [
          IconButton(icon: const Icon(Icons.logout), onPressed: _logout,
              tooltip: '退出登录'),
        ],
      ),
      body: IndexedStack(
        index: _tab,
        children: [
          RealtimePage(api: widget.api, onOutletsLoaded: _onOutletsLoaded),
          HistoryPage(api: widget.api, outlets: _outlets),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.monitor_heart_outlined),
              selectedIcon: Icon(Icons.monitor_heart),
              label: '实时数据'),
          NavigationDestination(
              icon: Icon(Icons.query_stats_outlined),
              selectedIcon: Icon(Icons.query_stats),
              label: '历史查询'),
        ],
      ),
    );
  }
}
