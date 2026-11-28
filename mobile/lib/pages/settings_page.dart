// v1.4.0 预警设置页：自定义阈值范围 / 声音报警 / 后台监测 / 微信推送
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';

import '../core/background_monitor.dart';
import '../core/constants.dart';
import '../core/push_service.dart';
import '../core/warn_config.dart';
import '../core/warning_engine.dart';

class SettingsPage extends StatefulWidget {
  final WarningEngine engine; // 阈值保存后回写，前台立即生效
  const SettingsPage({super.key, required this.engine});
  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  WarnConfig _cfg = WarnConfig();
  bool _loaded = false;
  bool _testing = false;
  final Map<String, TextEditingController> _lowC = {};
  final Map<String, TextEditingController> _highC = {};
  final _tokenC = TextEditingController();
  final _topicC = TextEditingController();
  final _keyC = TextEditingController();

  static String _fmt(double? v) => v == null ? '' : '$v';

  @override
  void initState() {
    super.initState();
    WarnConfig.load().then((cfg) {
      if (!mounted) return;
      setState(() {
        _cfg = cfg;
        for (final name in kWarnThresholds.keys) {
          final th = cfg.thresholdFor(name);
          _lowC[name] = TextEditingController(text: _fmt(th?[0]));
          _highC[name] = TextEditingController(text: _fmt(th?[1]));
        }
        _tokenC.text = cfg.pushplusToken;
        _topicC.text = cfg.pushplusTopic;
        _keyC.text = cfg.serverchanKey;
        _loaded = true;
      });
    });
  }

  @override
  void dispose() {
    for (final c in [..._lowC.values, ..._highC.values]) {
      c.dispose();
    }
    _tokenC.dispose();
    _topicC.dispose();
    _keyC.dispose();
    super.dispose();
  }

  void _toast(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(msg), duration: const Duration(seconds: 3)));
  }

  void _saveThreshold(String name) {
    double? low = double.tryParse(_lowC[name]!.text.trim());
    double? high = double.tryParse(_highC[name]!.text.trim());
    final def = kWarnThresholds[name]!;
    if (low == def[0] && high == def[1]) {
      _cfg.customThresholds.remove(name); // 与默认一致则取消覆盖
    } else {
      _cfg.customThresholds[name] = [low, high];
    }
    widget.engine.customThresholds = _cfg.customThresholds;
    _cfg.save();
  }

  void _resetThreshold(String name) {
    setState(() {
      _cfg.customThresholds.remove(name);
      final def = kWarnThresholds[name]!;
      _lowC[name]!.text = _fmt(def[0]);
      _highC[name]!.text = _fmt(def[1]);
    });
    widget.engine.customThresholds = _cfg.customThresholds;
    _cfg.save();
  }

  Future<void> _toggleBackground(bool v) async {
    if (v) {
      final err = await BackgroundMonitor.start();
      if (err != null) {
        _toast(err);
        return;
      }
    } else {
      await BackgroundMonitor.stop();
    }
    setState(() => _cfg.backgroundOn = v);
    _cfg.save();
  }

  Future<void> _testPush() async {
    setState(() => _testing = true);
    await _cfg.save();
    final r = await PushService.test(_cfg);
    if (mounted) setState(() => _testing = false);
    _toast(r);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('预警设置')),
      body: !_loaded
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 32),
              children: [
                _sectionTitle('自定义预警阈值', '留空表示该侧不限；与默认一致时自动取消覆盖'),
                ...kWarnThresholds.keys.map(_thresholdRow),
                const SizedBox(height: 16),
                _sectionTitle('声音报警', '新预警弹系统通知，提示音与震动可开关'),
                SwitchListTile(
                  dense: true,
                  title: const Text('预警提示音 + 震动'),
                  subtitle: const Text('关闭后通知仍弹出，但无声无震动'),
                  value: _cfg.soundOn,
                  onChanged: (v) {
                    setState(() => _cfg.soundOn = v);
                    _cfg.save();
                  },
                ),
                const SizedBox(height: 16),
                _sectionTitle('后台运行', '开启后通知栏常驻服务，退出 APP 仍每分钟监测并报警'),
                SwitchListTile(
                  dense: true,
                  title: const Text('后台监测（前台服务）'),
                  subtitle: const Text('请勿从最近任务中划掉 APP；建议同时加入电池优化白名单'),
                  value: _cfg.backgroundOn,
                  onChanged: _toggleBackground,
                ),
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    icon: const Icon(Icons.battery_saver, size: 18),
                    label: const Text('打开电池优化白名单设置'),
                    onPressed: () =>
                        FlutterForegroundTask.openIgnoreBatteryOptimizationSettings(),
                  ),
                ),
                const SizedBox(height: 16),
                _sectionTitle('微信推送', '普通微信群无官方机器人接口，走公众号消息提醒通道'),
                _buildPushSection(),
              ],
            ),
    );
  }

  Widget _sectionTitle(String title, String subtitle) {
    return Padding(
      padding: const EdgeInsets.only(left: 4, bottom: 6, top: 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style: const TextStyle(
                  fontSize: 15, fontWeight: FontWeight.w600, color: Color(0xFF2D9E60))),
          Text(subtitle, style: TextStyle(fontSize: 11, color: Colors.grey.shade500)),
        ],
      ),
    );
  }

  Widget _thresholdRow(String name) {
    final custom = _cfg.customThresholds.containsKey(name);
    return Card(
      margin: const EdgeInsets.only(bottom: 6),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 8, 10),
        child: Row(
          children: [
            Expanded(
              flex: 3,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(name, style: const TextStyle(fontSize: 13.5)),
                  if (custom)
                    const Text('已自定义',
                        style: TextStyle(fontSize: 10, color: Color(0xFFD29922))),
                ],
              ),
            ),
            Expanded(
              flex: 3,
              child: TextField(
                controller: _lowC[name],
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                inputFormatters: [
                  FilteringTextInputFormatter.allow(RegExp(r'[\d.\-]'))
                ],
                style: const TextStyle(fontSize: 13),
                decoration: const InputDecoration(
                    isDense: true, labelText: '下限', labelStyle: TextStyle(fontSize: 11)),
                onChanged: (_) => _saveThreshold(name),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              flex: 3,
              child: TextField(
                controller: _highC[name],
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                inputFormatters: [
                  FilteringTextInputFormatter.allow(RegExp(r'[\d.\-]'))
                ],
                style: const TextStyle(fontSize: 13),
                decoration: const InputDecoration(
                    isDense: true, labelText: '上限', labelStyle: TextStyle(fontSize: 11)),
                onChanged: (_) => _saveThreshold(name),
              ),
            ),
            IconButton(
              visualDensity: VisualDensity.compact,
              icon: const Icon(Icons.restart_alt, size: 18),
              tooltip: '恢复默认',
              onPressed: () => _resetThreshold(name),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPushSection() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SwitchListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: const Text('预警时推送到微信'),
              value: _cfg.pushOn,
              onChanged: (v) {
                setState(() => _cfg.pushOn = v);
                _cfg.save();
              },
            ),
            DropdownButtonFormField<String>(
              initialValue: _cfg.pushChannel,
              decoration: const InputDecoration(labelText: '推送通道', isDense: true),
              items: const [
                DropdownMenuItem(
                    value: 'pushplus', child: Text('Pushplus（推荐，支持群组推送）')),
                DropdownMenuItem(value: 'serverchan', child: Text('Server酱 Turbo（单推）')),
              ],
              onChanged: (v) {
                setState(() => _cfg.pushChannel = v ?? 'pushplus');
                _cfg.save();
              },
            ),
            if (_cfg.pushChannel == 'pushplus') ...[
              TextField(
                controller: _tokenC,
                style: const TextStyle(fontSize: 13),
                decoration: const InputDecoration(
                    labelText: 'Pushplus token', hintText: 'pushplus.plus 个人中心获取'),
                onChanged: (v) {
                  _cfg.pushplusToken = v.trim();
                  _cfg.save();
                },
              ),
              TextField(
                controller: _topicC,
                style: const TextStyle(fontSize: 13),
                decoration: const InputDecoration(
                    labelText: '群组码 topic（可选）',
                    hintText: '填入则推送给群组全部成员'),
                onChanged: (v) {
                  _cfg.pushplusTopic = v.trim();
                  _cfg.save();
                },
              ),
              const SizedBox(height: 8),
              Text(
                '群组推送步骤：\n'
                '1. 打开 pushplus.plus 注册，个人中心复制 token；\n'
                '2. 「群组推送」页创建群组，生成二维码；\n'
                '3. 把二维码发到你们的微信群，大家扫码加入；\n'
                '4. 群组码填入上方 topic。之后每次预警，'
                '每位成员的普通微信都会收到公众号提醒。',
                style: TextStyle(fontSize: 11.5, color: Colors.grey.shade400, height: 1.5),
              ),
            ] else ...[
              TextField(
                controller: _keyC,
                style: const TextStyle(fontSize: 13),
                decoration: const InputDecoration(
                    labelText: 'Server酱 SendKey',
                    hintText: 'sct.ftqq.com 登录后获取，推送到方糖服务号'),
                onChanged: (v) {
                  _cfg.serverchanKey = v.trim();
                  _cfg.save();
                },
              ),
            ],
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerLeft,
              child: FilledButton.tonalIcon(
                icon: _testing
                    ? const SizedBox(
                        width: 16, height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.send, size: 16),
                label: const Text('发送测试消息'),
                onPressed: _testing ? null : _testPush,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
