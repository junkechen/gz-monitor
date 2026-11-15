// 滑块验证码缺口自动求解（复刻桌面端 slider_solver.py 的 NCC 算法）
//
// 服务端契约：
//   GET /ajax/SliderValidImg.ashx?method=GetSliderImg
//     -> {"background": "data:image/jpeg;base64,...", "slider": "data:image/png;base64,..."}
//     background 300x150 JPEG（已绘制缺口），slider 62x150 PNG（拼图块，含透明区）
//   偏移量 = 缺口x - 拼图块自身左边界(x0)；服务端容差 ±4px
import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';
import 'package:image/image.dart' as img;

const int kBgWidth = 300;
const int kSliderWidth = 62;
const int kMinGapX = 10;
const int kMaxGapX = kBgWidth - kSliderWidth - 10; // 228

class SliderSolution {
  final int trail;
  final double score;
  final double margin;
  SliderSolution(this.trail, this.score, this.margin);
}

List<int> _dataUrlBytes(String dataUrl) {
  final b64 = dataUrl.contains(',') ? dataUrl.split(',').last : dataUrl;
  return base64.decode(b64);
}

List<List<double>> _grayAlpha(img.Image im) {
  final h = im.height, w = im.width;
  final gray = List<double>.filled(h * w, 0);
  final alpha = List<double>.filled(h * w, 0);
  for (int y = 0; y < h; y++) {
    for (int x = 0; x < w; x++) {
      final p = im.getPixel(x, y);
      final idx = y * w + x;
      // ITU-R BT.601 亮度
      gray[idx] =
          0.299 * p.r.toDouble() + 0.587 * p.g.toDouble() + 0.114 * p.b.toDouble();
      alpha[idx] = p.a.toDouble();
    }
  }
  return [gray, alpha];
}

/// 求解滑块偏移量；失败返回 null
SliderSolution? solveSlider(String bgDataUrl, String sliderDataUrl) {
  try {
    final bgIm = img.decodeImage(Uint8List.fromList(_dataUrlBytes(bgDataUrl)));
    final slIm = img.decodeImage(Uint8List.fromList(_dataUrlBytes(sliderDataUrl)));
    if (bgIm == null || slIm == null) return null;
    final bg = _grayAlpha(bgIm)[0];
    final slPair = _grayAlpha(slIm);
    final sl = slPair[0], slA = slPair[1];

    final h = bgIm.height, w = bgIm.width;
    final sh = slIm.height, sw = slIm.width;

    // 用 alpha 定位有效拼图块（桌面端用灰度偏差掩膜，透明区 alpha=0 更直接）
    int y0 = sh, y1 = -1, x0 = sw, x1 = -1;
    for (int y = 0; y < sh; y++) {
      for (int x = 0; x < sw; x++) {
        if (slA[y * sw + x] > 128) {
          if (y < y0) y0 = y;
          if (y > y1) y1 = y;
          if (x < x0) x0 = x;
          if (x > x1) x1 = x;
        }
      }
    }
    if (y1 < 0) return null;
    final ph = y1 - y0 + 1, pw = x1 - x0 + 1;
    if (ph > h || pw > w) return null;

    // 预提取掩膜内 patch 像素
    final offs = <int>[]; // (i*ph+j) 之内使用 (i,j)
    final patch = <double>[];
    for (int i = 0; i < ph; i++) {
      for (int j = 0; j < pw; j++) {
        final a = slA[(y0 + i) * sw + (x0 + j)];
        if (a > 128) {
          offs.add(i * pw + j);
          patch.add(sl[(y0 + i) * sw + (x0 + j)]);
        }
      }
    }
    if (offs.length < 50) return null;

    double bestScore = -2, second = -2;
    int bestX = -1;
    for (int x = kMinGapX; x <= kMaxGapX; x++) {
      if (x + pw > w) break;
      double sumB = 0;
      final win = List<double>.filled(offs.length, 0);
      for (int k = 0; k < offs.length; k++) {
        final o = offs[k];
        final i = o ~/ pw, j = o % pw;
        final v = bg[(y0 + i) * w + (x + j)];
        win[k] = v;
        sumB += v;
      }
      final mb = sumB / offs.length;
      double sumA = 0;
      final a2 = List<double>.filled(offs.length, 0);
      for (int k = 0; k < patch.length; k++) {
        a2[k] = patch[k];
        sumA += patch[k];
      }
      final ma = sumA / offs.length;
      double sa = 0, sb = 0, ab = 0;
      for (int k = 0; k < offs.length; k++) {
        final da = a2[k] - ma, db = win[k] - mb;
        sa += da * da;
        sb += db * db;
        ab += da * db;
      }
      final denom = math.sqrt(sa * sb);
      final score = denom > 1e-9 ? ab / denom : 0.0;
      if (score > bestScore) {
        second = bestScore;
        bestScore = score;
        bestX = x;
      } else if (score > second) {
        second = score;
      }
    }
    if (bestX < 0) return null;

    int trail = bestX - x0;
    trail = trail.clamp(0, kBgWidth);
    return SliderSolution(trail, bestScore, bestScore - second);
  } catch (_) {
    return null;
  }
}

/// 围绕初猜的候选偏移（先近后远，去重，含原值）
List<int> refineCandidates(int trail, {int span = 6}) {
  final out = <int>[trail];
  for (int d = 1; d <= span; d++) {
    out.add(trail - d);
    out.add(trail + d);
  }
  final seen = <int>{};
  return out
      .where((v) => v >= 0 && v <= kBgWidth && !seen.contains(v))
      .map((v) {
        seen.add(v);
        return v;
      })
      .toList();
}
