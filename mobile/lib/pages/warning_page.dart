// 预警页：预警记录列表（新在前），类型筛选，清空
import 'package:flutter/material.dart';

import '../core/warning_engine.dart';

class WarningPage extends StatefulWidget {
  final WarningEngine engine;
  const WarningPage({super.key, required this.engine});
  @override
  State<WarningPage> createState() => _WarningPageState();
}

class _WarningPageState extends State<WarningPage>
    with AutomaticKeepAliveClientMixin {
  String _filter = '全部';

  @override
  bool get wantKeepAlive => true;

  static const _types = ['全部', '超标', '同值', '急剧上升', '急剧下降'];

  Color _typeColor(WarnType t) {
    switch (t) {
      case WarnType.exceed:
        return const Color(0xFFF85149);
      case WarnType.sameValue:
        return const Color(0xFFD29922);
      case WarnType.rapidRise:
        return const Color(0xFFFF7B72);
      case WarnType.rapidDrop:
        return const Color(0xFF58A6FF);
    }
  }

  IconData _typeIcon(WarnType t) {
    switch (t) {
      case WarnType.exceed:
        return Icons.error_outline;
      case WarnType.sameValue:
        return Icons.horizontal_rule;
      case WarnType.rapidRise:
        return Icons.trending_up;
      case WarnType.rapidDrop:
        return Icons.trending_down;
    }
  }

  String _fmtTime(DateTime t) =>
      '${t.month.toString().padLeft(2, '0')}-${t.day.toString().padLeft(2, '0')} '
      '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    super.build(context);
    widget.engine.changeSerial; // 依赖角标序列触发重建
    final all = widget.engine.items;
    final list = _filter == '全部'
        ? all
        : all.where((w) => w.type.label == _filter).toList();

    return Scaffold(
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
            child: Row(
              children: [
                Expanded(
                  child: SizedBox(
                    height: 34,
                    child: ListView.separated(
                      scrollDirection: Axis.horizontal,
                      itemCount: _types.length,
                      separatorBuilder: (_, __) => const SizedBox(width: 6),
                      itemBuilder: (_, i) => ChoiceChip(
                        label: Text(_types[i], style: const TextStyle(fontSize: 12)),
                        selected: _filter == _types[i],
                        selectedColor: const Color(0xFF1A6B3C),
                        showCheckmark: false,
                        visualDensity: VisualDensity.compact,
                        onSelected: (_) => setState(() => _filter = _types[i]),
                      ),
                    ),
                  ),
                ),
                TextButton.icon(
                  onPressed: all.isEmpty
                      ? null
                      : () => _confirmClear(),
                  icon: const Icon(Icons.clear_all, size: 16),
                  label: const Text('清空', style: TextStyle(fontSize: 12)),
                ),
              ],
            ),
          ),
          Expanded(
            child: list.isEmpty
                ? Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.verified_outlined,
                            size: 46, color: Colors.grey.shade700),
                        const SizedBox(height: 10),
                        Text(
                          _filter == '全部' ? '暂无预警记录' : '暂无「$_filter」预警',
                          style: TextStyle(
                              color: Colors.grey.shade500, fontSize: 14),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          '预警规则：浓度超限值 / 持续同值（废气30min·废水3h）/ 急剧变化',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                              color: Colors.grey.shade700, fontSize: 11),
                        ),
                      ],
                    ),
                  )
                : RefreshIndicator(
                    onRefresh: () async {
                      setState(() {});
                    },
                    child: ListView.separated(
                      physics: const AlwaysScrollableScrollPhysics(),
                      padding: const EdgeInsets.fromLTRB(12, 4, 12, 24),
                      itemCount: list.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 8),
                      itemBuilder: (_, i) {
                        final w = list[i];
                        final c = _typeColor(w.type);
                        return Card(
                          margin: EdgeInsets.zero,
                          clipBehavior: Clip.antiAlias,
                          child: Padding(
                            padding: const EdgeInsets.all(12),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Container(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 8, vertical: 3),
                                      decoration: BoxDecoration(
                                        color: c.withOpacity(0.16),
                                        borderRadius:
                                            BorderRadius.circular(20),
                                      ),
                                      child: Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          Icon(_typeIcon(w.type),
                                              size: 13, color: c),
                                          const SizedBox(width: 4),
                                          Text(w.type.label,
                                              style: TextStyle(
                                                  fontSize: 11, color: c)),
                                        ],
                                      ),
                                    ),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: Text(
                                        '${w.param}  ${w.value}',
                                        style: const TextStyle(
                                            fontSize: 15,
                                            fontWeight: FontWeight.bold),
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                    Text(_fmtTime(w.time),
                                        style: TextStyle(
                                            fontSize: 11,
                                            color: Colors.grey.shade600)),
                                  ],
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  '${w.entName.isNotEmpty ? "${w.entName} · " : ""}${w.subname}',
                                  style: TextStyle(
                                      fontSize: 12,
                                      color: Colors.grey.shade400),
                                  overflow: TextOverflow.ellipsis,
                                ),
                                if (w.detail.isNotEmpty)
                                  Padding(
                                    padding: const EdgeInsets.only(top: 2),
                                    child: Text(w.detail,
                                        style: TextStyle(
                                            fontSize: 12, color: c)),
                                  ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmClear() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('清空预警记录'),
        content: const Text('将清除本机保存的全部预警历史，确定吗？'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('清空')),
        ],
      ),
    );
    if (ok == true) {
      widget.engine.clearAll();
      setState(() {});
    }
  }
}
