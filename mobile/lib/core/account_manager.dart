// 多账号管理：顺序登录全部选中账号（账号间随机间隔防风控），
// 合并各企业实时数据（打标 entName），按 subid 路由历史查询客户端。
import 'dart:math';

import 'gz_api.dart';

class LoginOutcome {
  final String account;
  final String? error; // null=成功
  LoginOutcome(this.account, this.error);
  bool get ok => error == null;
}

class AccountManager {
  final Map<String, GzApi> _clients = {}; // account -> api

  bool get isLoggedIn => _clients.isNotEmpty;
  List<String> get loggedInNames => _clients.keys.toList();
  int get clientCount => _clients.length;

  /// 顺序登录选中账号；progress(account, idx, total, message)
  Future<List<LoginOutcome>> loginAll(
    List<Map<String, String>> accounts, {
    void Function(String account, int idx, int total, String message)? progress,
  }) async {
    _clients.clear();
    final outcomes = <LoginOutcome>[];
    final rnd = Random();
    for (var i = 0; i < accounts.length; i++) {
      final acc = accounts[i];
      final name = acc['name']!;
      final pwd = acc['password']!;
      progress?.call(name, i + 1, accounts.length, '开始登录...');
      final api = GzApi();
      String? err;
      // 最多 2 次重试（桌面端 MAX_LOGIN_RETRY=3，移动端取 2 控制耗时）
      for (var attempt = 0; attempt < 2; attempt++) {
        if (attempt > 0) {
          progress?.call(name, i + 1, accounts.length,
              '第 ${attempt + 1} 次重试...');
          await Future.delayed(const Duration(seconds: 2));
        }
        err = await api.login(name, pwd,
            onProgress: (m) => progress?.call(name, i + 1, accounts.length, m));
        if (err == null) break;
        // 确定性失败不重试
        if (err.contains('密码错误') || err.contains('用户不存在')) break;
      }
      outcomes.add(LoginOutcome(name, err));
      if (err == null) {
        _clients[name] = api;
        progress?.call(name, i + 1, accounts.length, '登录成功');
      } else {
        progress?.call(name, i + 1, accounts.length, '失败: $err');
      }
      // 账号间随机等待（桌面端 2~5s），最后一个不等待
      if (i < accounts.length - 1) {
        await Future.delayed(
            Duration(milliseconds: 2000 + rnd.nextInt(3000)));
      }
    }
    return outcomes;
  }

  /// 合并全部已登录企业的实时数据（并发拉取，单账号失败不拖垮整体）
  Future<List<OutletGroup>> fetchMergedRealtime() async {
    if (_clients.isEmpty) throw Exception('尚未登录');
    final entries = _clients.entries.toList();
    final results = await Future.wait(entries.map((e) async {
      try {
        return await e.value.fetchRealtimeGroups(entName: e.key);
      } catch (_) {
        return <OutletGroup>[];
      }
    }));
    return results.expand((l) => l).toList();
  }

  /// 按 subid 找到对应企业的客户端（桌面端 get_client_by_subid 同款逻辑）
  GzApi? clientFor(String subid) => _routeBySubid[subid];

  final Map<String, GzApi> _routeBySubid = {};

  /// 实时拉取后建立 subid -> client 路由
  void buildRoutes() {
    _routeBySubid.clear();
    _clients.forEach((name, api) {
      for (final subid in api.knownSubids) {
        _routeBySubid[subid] = api;
      }
    });
  }

  void logoutAll() {
    for (final api in _clients.values) {
      api.loggedIn = false;
    }
    _clients.clear();
    _routeBySubid.clear();
  }
}
