// 登录页：多选企业账号（默认全选，与桌面端登录全部账号一致），自动滑块验证
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/account_manager.dart';
import '../core/constants.dart';
import 'home_page.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});
  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _manager = AccountManager();
  late List<bool> _checked;
  bool _busy = false;
  String _progress = '';
  final List<LoginOutcome> _outcomes = [];

  @override
  void initState() {
    super.initState();
    _checked = List.filled(kBuiltinAccounts.length, true);
    _restoreLastSelection();
  }

  Future<void> _restoreLastSelection() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getStringList('login_accounts');
    if (saved != null && mounted) {
      setState(() {
        for (var i = 0; i < kBuiltinAccounts.length; i++) {
          _checked[i] = saved.contains(kBuiltinAccounts[i]['name']);
        }
      });
    }
  }

  List<Map<String, String>> get _selectedAccounts => [
        for (var i = 0; i < kBuiltinAccounts.length; i++)
          if (_checked[i]) kBuiltinAccounts[i]
      ];

  Future<void> _doLogin() async {
    if (_busy) return;
    final accounts = _selectedAccounts;
    if (accounts.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('请至少选择一个企业账号')));
      return;
    }
    setState(() {
      _busy = true;
      _progress = '准备登录 ${accounts.length} 个账号...';
      _outcomes.clear();
    });
    final outcomes = await _manager.loginAll(accounts,
        progress: (acc, idx, total, msg) {
      if (mounted) {
        setState(() => _progress = '[$idx/$total] $acc  $msg');
      }
    });
    if (!mounted) return;
    final okList = outcomes.where((o) => o.ok).toList();
    // 记住本次选择
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(
        'login_accounts', okList.map((o) => o.account).toList());

    if (okList.isEmpty) {
      setState(() {
        _busy = false;
        _progress = '';
        _outcomes.addAll(outcomes);
      });
      return;
    }
    _manager.buildRoutes();
    Navigator.of(context).pushReplacement(MaterialPageRoute(
      builder: (_) => HomePage(manager: _manager),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final allChecked = _checked.every((c) => c);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: 16),
                  CircleAvatar(
                    radius: 32,
                    backgroundColor: const Color(0xFF1A6B3C).withOpacity(0.35),
                    child: const Icon(Icons.verified_user,
                        size: 36, color: Color(0xFF2D9E60)),
                  ),
                  const SizedBox(height: 12),
                  const Text('GZ 安环监测系统',
                      textAlign: TextAlign.center,
                      style:
                          TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Text('移动端 · 多企业合并监控',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                          fontSize: 13, color: Colors.grey.shade500)),
                  const SizedBox(height: 22),
                  Card(
                    margin: EdgeInsets.zero,
                    child: Column(
                      children: [
                        CheckboxListTile(
                          dense: true,
                          value: allChecked,
                          onChanged: (v) => setState(() =>
                              _checked = List.filled(_checked.length, v ?? false)),
                          title: const Text('全选',
                              style: TextStyle(fontWeight: FontWeight.w600)),
                          secondary: const Icon(Icons.select_all),
                          controlAffinity: ListTileControlAffinity.leading,
                        ),
                        const Divider(height: 1),
                        for (var i = 0; i < kBuiltinAccounts.length; i++)
                          CheckboxListTile(
                            dense: true,
                            value: _checked[i],
                            onChanged: (v) =>
                                setState(() => _checked[i] = v ?? false),
                            title: Text(kBuiltinAccounts[i]['name']!,
                                style: const TextStyle(fontSize: 13.5)),
                            secondary:
                                const Icon(Icons.business_outlined, size: 20),
                            controlAffinity: ListTileControlAffinity.leading,
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF1A6B3C),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                    onPressed: _busy ? null : _doLogin,
                    icon: _busy
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: Colors.white))
                        : const Icon(Icons.login),
                    label: Text(
                        _busy
                            ? '登录中'
                            : '登录选中账号（${_selectedAccounts.length}）',
                        style: const TextStyle(fontSize: 15)),
                  ),
                  const SizedBox(height: 10),
                  if (_progress.isNotEmpty)
                    Text(_progress,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                            fontSize: 12, color: Colors.grey.shade400)),
                  for (final o in _outcomes)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Row(
                        children: [
                          Icon(
                            o.ok ? Icons.check_circle : Icons.error_outline,
                            size: 15,
                            color: o.ok
                                ? const Color(0xFF3FB950)
                                : const Color(0xFFF85149),
                          ),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(
                              '${o.account}${o.ok ? " 登录成功" : " ${o.error}"}',
                              style: TextStyle(
                                  fontSize: 12,
                                  color: o.ok
                                      ? Colors.grey.shade400
                                      : const Color(0xFFF85149)),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ),
                    ),
                  const SizedBox(height: 16),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
