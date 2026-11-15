// 登录页：内置企业账号 + 密码，自动完成滑块验证
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/constants.dart';
import '../core/gz_api.dart';
import 'home_page.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});
  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _api = GzApi();
  late String _account;
  final _pwdCtrl = TextEditingController();
  bool _busy = false;
  String _progress = '';
  String? _error;
  bool _obscure = true;

  @override
  void initState() {
    super.initState();
    _account = kBuiltinAccounts.first['name']!;
    _pwdCtrl.text = kBuiltinAccounts.first['password']!;
    _loadLastAccount();
  }

  Future<void> _loadLastAccount() async {
    final prefs = await SharedPreferences.getInstance();
    final last = prefs.getString('last_account');
    if (last != null && mounted) {
      final hit = kBuiltinAccounts.where((a) => a['name'] == last).toList();
      setState(() {
        _account = last;
        _pwdCtrl.text =
            (hit.isNotEmpty ? hit.first['password'] : prefs.getString('last_pwd_$last')) ?? '';
      });
    }
  }

  Future<void> _doLogin() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _progress = '准备登录...';
    });
    final err = await _api.login(_account, _pwdCtrl.text,
        onProgress: (m) => mounted ? setState(() => _progress = m) : null);
    if (!mounted) return;
    if (err == null) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('last_account', _account);
      await prefs.setString('last_pwd_$_account', _pwdCtrl.text);
      Navigator.of(context).pushReplacement(MaterialPageRoute(
        builder: (_) => HomePage(api: _api, enterpriseName: _account),
      ));
    } else {
      setState(() {
        _busy = false;
        _progress = '';
        _error = err;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 16),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: 24),
                  CircleAvatar(
                    radius: 34,
                    backgroundColor: const Color(0xFF1A6B3C).withOpacity(0.35),
                    child: const Icon(Icons.verified_user,
                        size: 38, color: Color(0xFF2D9E60)),
                  ),
                  const SizedBox(height: 14),
                  const Text('GZ 安环监测系统',
                      textAlign: TextAlign.center,
                      style:
                          TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Text('移动端 · 企业排污数据监控',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                          fontSize: 13, color: Colors.grey.shade500)),
                  const SizedBox(height: 32),
                  DropdownButtonFormField<String>(
                    value: _account,
                    decoration: const InputDecoration(
                      labelText: '企业账号',
                      prefixIcon: Icon(Icons.business),
                      border: OutlineInputBorder(),
                    ),
                    items: kBuiltinAccounts
                        .map((a) => DropdownMenuItem(
                            value: a['name'], child: Text(a['name']!)))
                        .toList(),
                    onChanged: (v) {
                      if (v == null) return;
                      setState(() {
                        _account = v;
                        final hit = kBuiltinAccounts
                            .where((a) => a['name'] == v)
                            .toList();
                        _pwdCtrl.text = hit.isNotEmpty ? hit.first['password']! : '';
                        _error = null;
                      });
                    },
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _pwdCtrl,
                    obscureText: _obscure,
                    autofillHints: const [AutofillHints.password],
                    inputFormatters: [FilteringTextInputFormatter.singleLineFormatter],
                    decoration: InputDecoration(
                      labelText: '密码',
                      prefixIcon: const Icon(Icons.lock_outline),
                      border: const OutlineInputBorder(),
                      suffixIcon: IconButton(
                        icon: Icon(_obscure
                            ? Icons.visibility_off_outlined
                            : Icons.visibility_outlined),
                        onPressed: () => setState(() => _obscure = !_obscure),
                      ),
                    ),
                  ),
                  const SizedBox(height: 22),
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
                    label: Text(_busy ? '登录中' : '登 录',
                        style: const TextStyle(fontSize: 16)),
                  ),
                  const SizedBox(height: 10),
                  if (_progress.isNotEmpty)
                    Text(_progress,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                            fontSize: 12, color: Colors.grey.shade400)),
                  if (_error != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(_error!,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                              fontSize: 13, color: Color(0xFFF85149))),
                    ),
                  const SizedBox(height: 24),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
