// 实时数据页：排口卡片列表，下拉刷新，超标高亮
import 'package:flutter/material.dart';

import '../core/gz_api.dart';

class RealtimePage extends StatefulWidget {
  final GzApi api;
  final void Function(List<OutletGroup>) onOutletsLoaded;
  const RealtimePage({super.key, required this.api, required this.onOutletsLoaded});
  @override
  State<RealtimePage> createState() => _RealtimePageState();
}

class _RealtimePageState extends State<RealtimePage>
    with AutomaticKeepAliveClientMixin {
  bool _loading = true;
  String? _error;
  List<OutletGroup> _groups = [];

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Color _statusColor(String status) {
    if (status.contains('超标')) return const Color(0xFFF85149);
    if (status.contains('故障')) return const Color(0xFFD29922);
    if (status.contains('停产')) return Colors.grey;
    return const Color(0xFF3FB950);
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = _groups.isEmpty;
      _error = null;
    });
    try {
      final g = await widget.api.fetchRealtimeGroups();
      widget.onOutletsLoaded(g);
      if (!mounted) return;
      setState(() {
        _groups = g;
        _loading = false;
      });
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
        child: Text('暂无实时数据',
            style: TextStyle(color: Colors.grey.shade500)),
      );
    } else {
      body = RefreshIndicator(
        onRefresh: _refresh,
        child: ListView.separated(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 24),
          itemCount: _groups.length,
          separatorBuilder: (_, __) => const SizedBox(height: 10),
          itemBuilder: (_, i) {
            final g = _groups[i];
            final exceedCnt = g.params.where((p) => p.isExceed).length;
            return Card(
              margin: EdgeInsets.zero,
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
                          padding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: _statusColor(g.status).withOpacity(0.16),
                            borderRadius: BorderRadius.circular(20),
                          ),
                          child: Text(
                            g.status.isEmpty ? '—' : g.status,
                            style: TextStyle(
                                fontSize: 11,
                                color: _statusColor(g.status)),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${g.subtypeText} · ${g.datetime}',
                      style: TextStyle(
                          fontSize: 11, color: Colors.grey.shade500),
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
                                      fontSize: 11,
                                      color: Colors.grey.shade600),
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
          },
        ),
      );
    }
    return Scaffold(body: body, floatingActionButton: _loading ? null : FloatingActionButton.small(
      onPressed: _refresh,
      child: const Icon(Icons.refresh),
    ));
  }
}
