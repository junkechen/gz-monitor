// 实时数据页：多企业合并排口卡片，按企业分节；下拉/自动刷新；联动预警引擎
import 'dart:async';

import 'package:flutter/material.dart';

import '../core/account_manager.dart';
import '../core/constants.dart';
import '../core/gz_api.dart';
import '../core/warning_engine.dart';

class RealtimePage extends StatefulWidget {
  final AccountManager manager;
  final WarningEngine engine;
  final void Function(List<OutletGroup>) onOutletsLoaded;
  final void Function(List<WarningItem> fresh) onWarnings;
  const RealtimePage({
    super.key,
    required this.manager,
    required this.engine,
    required this.onOutletsLoaded,
    required this.onWarnings,
  });
  @override
  State<RealtimePage> createState() => _RealtimePageState();
}

class _RealtimePageState extends State<RealtimePage>
    with AutomaticKeepAliveClientMixin {
  bool _loading = true;
  String? _error;
  List<OutletGroup> _groups = [];
  bool _autoRefresh = true;
  Timer? _timer;
  DateTime? _lastUpdated;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _refresh();
    _startTimer();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _startTimer() {
    _timer?.cancel();
    _timer = Timer.periodic(
        const Duration(seconds: kAutoRefreshSeconds), (_) => _refresh());
  }

  Color _statusColor(String status) {
    if (status.contains('超标')) return const Color(0xFFF85149);
    if (status.contains('故障')) return const Color(0xFFD29922);
    if (status.contains('停产')) return Colors.grey;
    return const Color(0xFF3FB950);
  }

  Future<void> _refresh() async {
    if (!widget.manager.isLoggedIn) return;
    setState(() {
      _loading = _groups.isEmpty;
      _error = null;
    });
    try {
      final g = await widget.manager.fetchMergedRealtime();
      widget.manager.buildRoutes();
      widget.onOutletsLoaded(g);
      final fresh = widget.engine.ingest(g);
      if (!mounted) return;
      setState(() {
        _groups = g;
        _loading = false;
        _lastUpdated = DateTime.now();
      });
      widget.onWarnings(fresh);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = '获取实时数据失败：$e';
      });
    }
  }

  String _fmtVal(String? v) {
    if (v == null) return '—';
    final d = double.tryParse(v);
    if (d == null) return v;
    return d == d.roundToDouble() ? d.toStringAsFixed(0) : d.toStringAsFixed(3);
  }

  String _hhmm(DateTime t) =>
      '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

  List<String> get _entNames =>
      _groups.map((g) => g.entName).toSet().toList();

  @override
  Widget build(BuildContext context) {
    super.build(context);
    Widget body;
    if (_loading) {
      body = const Center(child: CircularProgressIndicator());
    } else if (_error != null) {
      body = Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off, size: 46, color: Colors.grey.shade600),
            const SizedBox(height: 10),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 28),
              child: Text(_error!,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.grey.shade400, fontSize: 13)),
            ),
            const SizedBox(height: 14),
            FilledButton.tonal(onPressed: _refresh, child: const Text('重试')),
          ],
        ),
      );
    } else if (_groups.isEmpty) {
      body = Center(
        child: Text('暂无实时数据', style: TextStyle(color: Colors.grey.shade500)),
      );
    } else {
      body = RefreshIndicator(
        onRefresh: _refresh,
        child: ListView.builder(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(12, 6, 12, 24),
          itemCount: _groups.length + _entNames.length + 1,
          itemBuilder: (_, i) {
            // 头部：自动刷新开关 + 更新时间
            if (i == 0) {
              return _buildHeader();
            }
            // 分节标题
            int offset = 1;
            for (final ent in _entNames) {
              final entGroups =
                  _groups.where((g) => g.entName == ent).toList();
              if (i == offset) {
                return Padding(
                  padding: const EdgeInsets.only(top: 8, bottom: 4),
                  child: Row(
                    children: [
                      const Icon(Icons.business, size: 14,
                          color: Color(0xFF2D9E60)),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(ent,
                            style: const TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                color: Color(0xFF2D9E60)),
                            overflow: TextOverflow.ellipsis),
                      ),
                      Text('${entGroups.length} 个排口',
                          style: TextStyle(
                              fontSize: 11, color: Colors.grey.shade600)),
                    ],
                  ),
                );
              }
              offset += 1 + entGroups.length;
              if (i < offset) {
                return _buildOutletCard(
                    entGroups[i - (offset - entGroups.length)]);
              }
            }
            return const SizedBox.shrink();
          },
        ),
      );
    }
    return Scaffold(body: body);
  }

  Widget _buildHeader() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(2, 4, 2, 2),
      child: Row(
        children: [
          Text(
            _lastUpdated == null ? '' : '更新于 ${_hhmm(_lastUpdated!)}',
            style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
          ),
          const Spacer(),
          const Text('自动刷新',
              style: TextStyle(fontSize: 12, color: Colors.grey)),
          SizedBox(
            height: 28,
            child: Switch(
              value: _autoRefresh,
              activeThumbColor: const Color(0xFF2D9E60),
              onChanged: (v) {
                setState(() => _autoRefresh = v);
                if (v) {
                  _startTimer();
                } else {
                  _timer?.cancel();
                }
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildOutletCard(OutletGroup g) {
    final exceedCnt = g.params.where((p) => p.isExceed).length;
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(g.subname,
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.bold),
                      overflow: TextOverflow.ellipsis),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: _statusColor(g.status).withOpacity(0.16),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    g.status.isEmpty ? '—' : g.status,
                    style:
                        TextStyle(fontSize: 11, color: _statusColor(g.status)),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 2),
            Text(
              '${g.subtypeText} · ${g.datetime}',
              style: TextStyle(fontSize: 11, color: Colors.grey.shade500),
            ),
            const Divider(height: 16),
            ...g.params.map((p) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2.5),
                  child: Row(
                    children: [
                      Expanded(
                        flex: 5,
                        child: Text(p.name,
                            style: TextStyle(
                                fontSize: 13,
                                color: p.isExceed
                                    ? const Color(0xFFF85149)
                                    : Colors.grey.shade300)),
                      ),
                      Expanded(
                        flex: 4,
                        child: Text(
                          _fmtVal(p.value),
                          textAlign: TextAlign.right,
                          style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                              color: p.isExceed
                                  ? const Color(0xFFF85149)
                                  : Colors.white),
                        ),
                      ),
                      Expanded(
                        flex: 3,
                        child: Text(
                          p.std.isEmpty ? '' : ' 限值${_fmtVal(p.std)}',
                          textAlign: TextAlign.right,
                          style: TextStyle(
                              fontSize: 11, color: Colors.grey.shade600),
                        ),
                      ),
                    ],
                  ),
                )),
            if (exceedCnt > 0)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text('⚠ $exceedCnt 项超标',
                    style: const TextStyle(
                        fontSize: 12, color: Color(0xFFF85149))),
              ),
          ],
        ),
      ),
    );
  }
}
