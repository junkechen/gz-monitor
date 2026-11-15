// GZ安环监测 - 服务端 API 客户端（协议与桌面端 multi_account_api.py 完全对齐）
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:dio_cookie_manager/dio_cookie_manager.dart';
import 'package:cookie_jar/cookie_jar.dart';
import 'package:encrypt/encrypt.dart' as enc;

import 'constants.dart';
import 'slider_solver.dart';

class OutletParam {
  final String name;
  final String code;
  final String? value; // 原始值（可能是数字或 '-'）
  final String std; // 限值
  final bool isExceed;
  OutletParam(
      {required this.name,
      required this.code,
      required this.value,
      required this.std,
      required this.isExceed});
}

class OutletGroup {
  final String subid;
  final String subname;
  final String subtypeText; // 如 VOCs/废水
  final String datetime;
  final String status;
  final List<OutletParam> params;
  final Set<String> itemCodes;
  OutletGroup({
    required this.subid,
    required this.subname,
    required this.subtypeText,
    required this.datetime,
    required this.status,
    required this.params,
    required this.itemCodes,
  });

  bool get isWater => isWaterType(subtypeText);
  String get subtypeCode => subtypeCodeOf(subtypeText);
  String get displayName => codeName(subtypeCode) == null ? subtypeText : subtypeText;
}

String? _f2s(dynamic v) {
  if (v == null) return null;
  if (v is num) {
    if (v == -9999) return null;
    return v.toString();
  }
  final s = v.toString().trim();
  if (s.isEmpty || s == '-9999' || s == '-') return null;
  return s;
}

double? _toDouble(dynamic v) {
  if (v == null) return null;
  if (v is num) return v.toDouble();
  final s = v.toString().trim();
  if (s.isEmpty) return null;
  return double.tryParse(s);
}

/// 实时接口的 subid / itemCode 常为浮点字符串（如 "8191.0"），
/// 服务端历史接口只认整数形式（桌面端同样做 int(float(x)) 归一）。
String? _normIdCode(dynamic v) {
  if (v == null) return null;
  if (v is num) return v.toInt().toString();
  final s = v.toString().trim();
  if (s.isEmpty || s == '-9999') return null;
  final d = double.tryParse(s);
  return d != null ? d.toInt().toString() : s;
}

class GzApi {
  late final Dio dio;
  bool loggedIn = false;
  String? enterpriseName;

  GzApi() {
    dio = Dio(BaseOptions(
      baseUrl: kBaseUrl,
      connectTimeout: const Duration(seconds: 20),
      receiveTimeout: const Duration(seconds: 40),
      headers: {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
        'X-Requested-With': 'XMLHttpRequest',
        'Cache-Control': 'no-cache',
      },
    ));
    dio.interceptors.add(CookieManager(CookieJar()));
  }

  String _aesHex(String text) {
    final key = enc.Key.fromUtf8(kAesKey);
    final iv = enc.IV.fromUtf8(kAesIv);
    final e = enc.Encrypter(enc.AES(key, mode: enc.AESMode.cbc));
    final ct = e.encrypt(text, iv: iv); // PKCS7 默认
    return ct.bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  }

  /// 服务端部分接口以 text/plain 返回 JSON（dio 只对 application/json 自动解码），
  /// 这里统一归一为 Map/List。
  dynamic _jsonify(dynamic data) {
    if (data is String) {
      final t =
          data.trim().replaceAll(RegExp(r'^"'), '').replaceAll(RegExp(r'"$'), '');
      try {
        return jsonDecode(t);
      } catch (_) {
        return data;
      }
    }
    return data;
  }

  Future<int?> _checkSlider(int trail) async {
    try {
      final r = await dio.get('/ajax/SliderValidImg.ashx', queryParameters: {
        'method': 'CheckSliderImg',
        'p': _aesHex(trail.toString()),
      });
      final data = _jsonify(r.data);
      if (data is Map) return data['Code'] as int?;
      return null;
    } catch (_) {
      return null;
    }
  }

  /// 完整登录。成功返回 null，失败返回错误信息。
  Future<String?> login(String username, String password,
      {void Function(String)? onProgress}) async {
    try {
      onProgress?.call('步骤1/4: 获取会话...');
      await dio.get('/', options: Options(responseType: ResponseType.plain));

      onProgress?.call('步骤2/4: 获取验证码...');
      final r = await dio.get('/ajax/SliderValidImg.ashx',
          queryParameters: {'method': 'GetSliderImg'});
      // 服务端可能以 text/plain 返回 JSON（桌面端同款兼容），先归一为 Map
      dynamic data = _jsonify(r.data);
      if (data is! Map ||
          !data.containsKey('background') ||
          !data.containsKey('slider')) {
        return '滑块接口返回异常';
      }

      onProgress?.call('步骤3/4: 滑块验证...');
      final sol = solveSlider(data['background'] as String,
          data['slider'] as String);
      int? trailFound;
      if (sol != null) {
        for (final cand in refineCandidates(sol.trail)) {
          final code = await _checkSlider(cand);
          if (code == 0) {
            trailFound = cand;
            break;
          }
        }
      }
      if (trailFound == null) {
        return '滑块验证失败，请重试';
      }

      onProgress?.call('步骤4/4: 验证账户...');
      final resp = await dio.post(
        '/Ajax/Login.ashx',
        queryParameters: {'Method': 'CheckLogin'},
        data: 'p1=${_aesHex(username)}'
            '&p2=${_aesHex(password)}'
            '&p3=${_aesHex(trailFound.toString())}',
        options: Options(
          contentType: Headers.formUrlEncodedContentType,
          headers: {'Referer': '$kBaseUrl/Login/index.aspx'},
          responseType: ResponseType.plain,
        ),
      );
      final text = resp.data.toString().trim().replaceAll('"', '');
      if (text == 'ok') {
        loggedIn = true;
        enterpriseName = username;
        return null;
      } else if (text == 'errorpassword') {
        return '密码错误';
      } else if (text == 'errorvalid') {
        return '验证码错误，请重试';
      } else if (text == 'usernotexist') {
        return '用户不存在';
      } else if (text.startsWith('haslock')) {
        return '账号被锁定，请稍后再试或到网页端登录解锁';
      }
      return '登录失败: $text';
    } on DioException catch (e) {
      if (e.type == DioExceptionType.connectionError ||
          e.type == DioExceptionType.connectionTimeout) {
        return '网络连接失败，请检查网络';
      }
      return '登录异常: ${e.message}';
    } catch (e) {
      return '登录异常: $e';
    }
  }

  bool _ensureLoggedIn() => loggedIn;

  /// 获取实时数据，解析为按排口分组的列表
  Future<List<OutletGroup>> fetchRealtimeGroups() async {
    if (!_ensureLoggedIn()) throw Exception('未登录或会话已过期');
    final ts = DateTime.now().millisecondsSinceEpoch.toString();
    await dio.get(
      '/Web6/MonitorControl/Enterprise/EnterPriseRealTimeData.aspx',
      queryParameters: {'_': ts},
      options: Options(
        responseType: ResponseType.plain,
        headers: {
          'Accept':
              'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
          'Referer': '$kBaseUrl/Web6/Main.aspx',
        },
      ),
    );
    await Future.delayed(const Duration(milliseconds: 300));
    final resp = await dio.post(
      '/Web6/ajax/MonitorControl/Enterprise/EnterPriseRealTimeData.ashx',
      queryParameters: {'Method': 'GetEnterpriseRealtimeData', '_': ts},
      options: Options(
        contentType: Headers.formUrlEncodedContentType,
        headers: {
          'Referer':
              '$kBaseUrl/Web6/MonitorControl/Enterprise/EnterPriseRealTimeData.aspx'
        },
      ),
    );
    final result = _jsonify(resp.data);
    if (result is! Map) return [];
    final rows = (result['rows'] as List?) ?? const [];
    final map = <String, Map<String, dynamic>>{};
    for (final row in rows) {
      if (row is! Map) continue;
      final subid = _normIdCode(row['C0007_SUBSTATION_ID']);
      if (subid == null || subid.isEmpty) continue;
      final key = subid;
      final g = map.putIfAbsent(key, () {
        return {
          'subid': subid,
          'subname': (row['C0007_SUBNAME'] ?? '').toString(),
          'subtype': (row['SUBTYPE'] ?? '').toString(),
          'datetime': (row['DATETIME'] ?? row['DateTime'] ?? '').toString(),
          'status': (row['C0202_NAME'] ?? '').toString(),
          'params': <OutletParam>[],
          'codes': <String>{},
        };
      });
      final code = _normIdCode(row['C0001_ITEM_CODE']);
      (g['params'] as List<OutletParam>).add(OutletParam(
        name: (row['C0001_ITEM_NAME'] ?? '').toString(),
        code: code ?? '',
        value: _f2s(row['C1703_VALUE']),
        std: _f2s(row['C0115_STDVALUE']) ?? '',
        isExceed: () {
          final cbbs = row['CBBS'];
          if (cbbs == null) return false;
          final n = _toDouble(cbbs);
          return n != null && n != 0;
        }(),
      ));
      if (code != null && code.isNotEmpty) (g['codes'] as Set<String>).add(code);
    }
    return map.values.map((g) => OutletGroup(
          subid: g['subid'] as String,
          subname: g['subname'] as String,
          subtypeText: g['subtype'] as String,
          datetime: g['datetime'] as String,
          status: g['status'] as String,
          params: g['params'] as List<OutletParam>,
          itemCodes: g['codes'] as Set<String>,
        )).toList();
  }

  /// 历史查询。index: 1=小时 2=日 -1=分钟。
  /// 返回 {total, rows:[...]}
  Future<Map<String, dynamic>> queryHistory({
    required String subid,
    required String subtype,
    required String codes,
    required String start,
    required String end,
    int index = 1,
    int page = 1,
    int rows = 1000,
    bool useCorrected = false,
  }) async {
    if (!_ensureLoggedIn()) throw Exception('未登录或会话已过期');
    String s = start, e = end;
    // v5.83：日数据必须用裸日期 yyyy-MM-dd
    if (index == 2) {
      s = s.split(' ')[0];
      e = e.split(' ')[0];
      // 日/月查询前先 GET HistoryData.aspx 初始化会话
      try {
        await dio.get('/Web6/MonitorControl/Enterprise/HistoryData.aspx',
            options: Options(
              responseType: ResponseType.plain,
              headers: {'Referer': '$kBaseUrl/Web6/Main.aspx'},
            ));
      } catch (_) {}
    }
    final body = 'Method=QueryHistoryReport'
        '&subid=$subid&subtype=$subtype&index=$index'
        '&start=${Uri.encodeComponent(s)}&end=${Uri.encodeComponent(e)}'
        '&codes=${Uri.encodeComponent(codes)}'
        '&sort=1&showValidate=1&showUpload=${useCorrected ? 1 : 0}'
        '&selectcity=0&page=$page&rows=$rows';
    final resp = await dio.post(
      '/ajax/WasteGas/QueryAnalysis/HistoryReportQUIDYN/HistoryReport.ashx',
      data: body,
      options: Options(
        contentType: Headers.formUrlEncodedContentType,
        headers: {
          'Referer': '$kBaseUrl/Web6/MonitorControl/Enterprise/HistoryData.aspx'
        },
      ),
    );
    final result = _jsonify(resp.data);
    if (result is! Map) return {'total': 0, 'rows': []};
    return {
      'total': result['total'] ?? 0,
      'rows': (result['rows'] as List?) ?? [],
    };
  }
}

// ── 排放量计算（与桌面端 v5.85 口径一致）───────────────────────────────────

/// 日粒度：ex_{code} 单位为吨 → kg；无 ex 时回退 浓度×流量×小时数/1e6
double dayEmissionKg(Map row, String code, String? flowCode) {
  final ex = _toDouble(row['ex_$code']);
  if (ex != null && ex > 0) return ex * 1000.0;
  final v = _toDouble(row['val_$code']);
  final fl = flowCode == null ? null : _toDouble(row['val_$flowCode']);
  if (v != null && v > 0 && fl != null && fl > 0) {
    final hc = _toDouble(row['hourcount_$code']) ?? 24.0;
    return v * fl * hc / 1e6;
  }
  return 0.0;
}

/// 小时粒度：ex_{code} 单位已是 kg
double hourEmissionKg(Map row, String code) {
  final ex = _toDouble(row['ex_$code']);
  return (ex != null && ex > 0) ? ex : 0.0;
}

String fmtNum(num? v, {int digits = 3}) {
  if (v == null) return '—';
  final d = v.toDouble();
  if (d == d.roundToDouble()) return d.toStringAsFixed(0);
  return d.toStringAsFixed(digits);
}

String? numStr(dynamic v) {
  if (v == null) return null;
  if (v is num) return v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toString();
  final s = v.toString().trim();
  if (s.isEmpty || s == '-9999' || s == '-') return null;
  return s;
}
