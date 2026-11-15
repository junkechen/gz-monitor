// 历史查询页：排口选择 + 日/小时粒度 + 日期范围 + 排放量合计（v5.85 吨→kg 口径）
import 'package:flutter/material.dart';

import '../core/constants.dart';
import '../core/gz_api.dart';

class HistoryPage extends StatefulWidget {
  final GzApi api;
  final List<OutletGroup>? outlets;
  const HistoryPage({super.key, required this.api, this.outlets});
  @override
  State<HistoryPage> createState() => _HistoryPageState();
}

class _HistoryPageState extends State<HistoryPage>
    with AutomaticKeepAliveClientMixin {
  final _scaffoldKey = GlobalKey<ScaffoldState>();
  List<OutletGroup> _outlets = [];
  OutletGroup? _sel;
  int _index = 2; // 2=日 1=小时
  DateTime _start = DateTime.now().subtract(const Duration(days: 6));
  DateTime _end = DateTime.now();
  bool _querying = false;
  String? _error;
  List<Map> _rows = [];
  double _totalKg = 0;
  int _dataDays = 0;
  String _emissionName = '';

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _outlets = widget.outlets ?? const [];
    if (_outlets.isEmpty) _loadOutlets();
    _sel = _outlets.isEmpty ? null : _outlets.first;
  }

  Future<void> _loadOutlets() async {
    try {
      final g = await widget.api.fetchRealtimeGroups();
      if (!mounted) return;
      setState(() {
        _outlets = g;
        _sel = g.isEmpty ? null : g.first;
      });
    } catch (_) {
      // 静默：用户可下拉重试（切换到实时页刷新）
    }
  }

  List<String> get _codes {
    if (_sel == null) return const [];
    if (_sel!.itemCodes.isNotEmpty) {
      final list = _sel!.itemCodes.toList();
      list.sort((a, b) {
        final na = int.tryParse(a), nb = int.tryParse(b);
        if (na != null && nb != null) return na.compareTo(nb);
        return a.compareTo(b);
      });
      return list;
    }
    return _sel!.isWater ? kDefaultWaterCodes : kDefaultGasCodes;
  }

  String get _mainCode =>
      _sel == null ? kGasEmissionCode : (_sel!.isWater ? kWaterEmissionCode : kGasEmissionCode);

  Future<void> _pickDate({required bool isStart}) async {
    final initial = isStart ? _start : _end;
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2020),
      lastDate: DateTime.now(),
      helpText: isStart ? '选择开始日期' : '选择结束日期',
    );
    if (picked == null) return;
    setState(() {
      if (isStart) {
        _start = picked;
        if (_end.isBefore(_start)) _end = _start;
      } else {
        _end = picked;
        if (_end.isBefore(_start)) _start = _end;
      }
    });
  }

  String _d(DateTime t) =>
      '${t.year}-${t.month.toString().padLeft(2, '0')}-${t.day.toString().padLeft(2, '0')}';

  Future<void> _query() async {
    if (_sel == null || _querying) return;
    setState(() {
      _querying = true;
      _error = null;
      _rows = [];
      _totalKg = 0;
      _dataDays = 0;
    });
    try {
      final res = await widget.api.queryHistory(
        subid: _sel!.subid,
        subtype: _sel!.subtypeCode,
        codes: _codes.join(','),
        start: _d(_start),
        end: _d(_end),
        index: _index,
      );
      final rows = (res['rows'] as List).whereType<Map>().toList();
      final flowCode = _sel!.isWater ? null : '210';
      double total = 0;
      int days = 0;
      for (final r in rows) {
        final kg = _index == 2
            ? dayEmissionKg(r, _mainCode, flowCode)
            : hourEmissionKg(r, _mainCode);
        r['_kg'] = kg;
        total += kg;
        if (kg > 0) days++;
      }
      if (!mounted) return;
      setState(() {
        _rows = rows;
        _totalKg = total;
        _dataDays = days;
        _emissionName = codeName(_mainCode) ?? _mainCode;
        _querying = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _querying = false;
        _error = '查询失败：$e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Scaffold(
      key: _scaffoldKey,
      body: RefreshIndicator(
        onRefresh: _loadOutlets,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 24),
          children: [
            _buildSelectorCard(),
            const SizedBox(height: 10),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF1A6B3C),
                padding: const EdgeInsets.symmetric(vertical: 13),
              ),
              onPressed: (_querying || _sel == null) ? null : _query,
              icon: _querying
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.search),
              label: Text(_querying ? '查询中...' : '查 询'),
            ),
            const SizedBox(height: 12),
            if (_error != null)
              Card(
                color: const Color(0xFFF85149).withOpacity(0.12),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(_error!,
                      style: const TextStyle(
                          fontSize: 13, color: Color(0xFFF85149))),
                ),
              ),
            if (_rows.isNotEmpty) _buildSummaryCard(),
            const SizedBox(height: 10),
            ..._rows.map(_buildRowCard),
            if (!_querying && _rows.isEmpty && _error == null && _sel != null)
              Padding(
                padding: const EdgeInsets.only(top: 30),
                child: Center(
                  child: Text('选择排口与时段后点击「查询」',
                      style: TextStyle(color: Colors.grey.shade600)),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildSelectorCard() {
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            DropdownButtonFormField<OutletGroup>(
              value: _sel,
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: '排口',
                prefixIcon: Icon(Icons.factory_outlined),
                border: OutlineInputBorder(),
                contentPadding:
                    EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              ),
              items: _outlets
                  .map((g) => DropdownMenuItem(
                        value: g,
                        child: Text('${g.subname}（${g.subtypeText}）',
                            overflow: TextOverflow.ellipsis),
                      ))
                  .toList(),
              onChanged: (v) => setState(() {
                _sel = v;
                _rows = [];
              }),
            ),
            const SizedBox(height: 12),
            SegmentedButton<int>(
              segments: const [
                ButtonSegment(value: 2, label: Text('日数据'), icon: Icon(Icons.calendar_month)),
                ButtonSegment(value: 1, label: Text('小时数据'), icon: Icon(Icons.schedule)),
              ],
              selected: {_index},
              onSelectionChanged: (s) => setState(() {
                _index = s.first;
                _rows = [];
              }),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => _pickDate(isStart: true),
                    icon: const Icon(Icons.date_range, size: 16),
                    label: Text(_d(_start), style: const TextStyle(fontSize: 13)),
                  ),
                ),
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 6),
                  child: Text('至', style: TextStyle(color: Colors.grey)),
                ),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => _pickDate(isStart: false),
                    icon: const Icon(Icons.date_range, size: 16),
                    label: Text(_d(_end), style: const TextStyle(fontSize: 13)),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSummaryCard() {
    final avg = _dataDays > 0 ? _totalKg / _dataDays : 0.0;
    return Card(
      margin: EdgeInsets.zero,
      color: const Color(0xFF1A6B3C).withOpacity(0.22),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '$_emissionName 排放量合计  ${_totalKg.toStringAsFixed(_totalKg == _totalKg.roundToDouble() ? 0 : 3)} kg',
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            Text(
              _index == 2
                  ? '参与天数 $_dataDays 天 · 日均 ${avg.toStringAsFixed(3)} kg/天'
                  : '共 ${_rows.length} 小时数据',
              style: TextStyle(fontSize: 12, color: Colors.grey.shade400),
            ),
            if (_index == 2)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  '注：服务端日排放量单位为吨(t)，已按 1t=1000kg 换算，与官网导出同口径',
                  style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildRowCard(Map r) {
    final dt = (r['DateTime'] ?? '').toString();
    final kg = (r['_kg'] as num?) ?? 0.0;
    final codes = _codes;
    return Card(
      margin: EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(dt,
                      style: const TextStyle(
                          fontSize: 14, fontWeight: FontWeight.w600)),
                ),
                Text(
                  _index == 2 ? '${kg.toStringAsFixed(3)} kg' : (kg > 0 ? '${kg.toStringAsFixed(3)} kg' : ''),
                  style: TextStyle(
                      fontSize: 12,
                      color: kg > 0 ? const Color(0xFF2D9E60) : Colors.grey.shade600),
                ),
              ],
            ),
            const Divider(height: 12),
            ...codes.map((c) {
              final raw = numStr(r['val_$c']);
              final stand = numStr(r['stand_$c']);
              final state = numStr(r['state_$c']) ?? '0';
              final exceed = state != '0';
              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(
                  children: [
                    Expanded(
                      flex: 5,
                      child: Text(codeName(c) ?? '代码$c',
                          style: TextStyle(
                              fontSize: 13,
                              color: exceed
                                  ? const Color(0xFFF85149)
                                  : Colors.grey.shade300)),
                    ),
                    Expanded(
                      flex: 4,
                      child: Text(raw ?? '—',
                          textAlign: TextAlign.right,
                          style: TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w500,
                              color: exceed ? const Color(0xFFF85149) : Colors.white)),
                    ),
                    Expanded(
                      flex: 3,
                      child: Text(
                        stand == null ? '' : ' 限值$stand',
                        textAlign: TextAlign.right,
                        style: TextStyle(fontSize: 11, color: Colors.grey.shade600),
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
    );
  }
}
