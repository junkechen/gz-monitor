# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 滑块验证码缺口自动求解器

背景（v5.44 重大发现）
----------------------
服务端滑块接口契约（已实测确认，非猜测）：

1. ``GET  /ajax/SliderValidImg.ashx?method=GetSliderImg``
   返回 JSON：``{"background": "data:image/jpeg;base64,...", "slider": "data:image/png;base64,..."}``
   - background：300x150 JPEG，**上面已绘制拼图缺口**
   - slider   ：62x150 PNG，高度与背景一致，说明拼图块原始内容就是从背景图裁下的
   - 该响应会 Set-Cookie 建立 ASP.NET_SessionId，后续请求必须复用同一 Session

2. ``GET  /ajax/SliderValidImg.ashx?method=CheckSliderImg&p={aes_encrypt(偏移量)}``
   - 正确：``{"Code":0,"Mess":"success"}``
   - 错误：``{"Code":500,"Mess":"error"}``
   - 服务端容差为 ±4px（实测区间宽度 9）
   - 旧文档记载的 ``{"Code":-1,"Mess":"error"}`` 是**密钥错误**时的表现，
     并非"服务端升级为校验鼠标轨迹"

3. ``POST /Ajax/Login.ashx?Method=CheckLogin``
   body: ``p1={enc(用户名)}&p2={enc(密码)}&p3={enc(滑块偏移量)}``
   响应为纯文本：ok / errorpassword / errorvalid / haslock|N / error

**AES 密钥已变更（本次故障的真正根因）**
--------------------------------------
通过反混淆服务端前端 ``/Assets/scripts/chunk.min.js`` 中的
``Security.EncryptAES`` 并在 Node 中实跑拦截，还原出真实密钥：

    KEY = b'i7t483eitnweh6phbi0jemr965dhbr63'   (32 字节)
    IV  = b'i7t483eitnweh6ph'                   (16 字节)

原代码使用的 ``b'1234567890abcdefghijklmnopqrstuv'`` **已失效**，
这才是"枚举滑块答案全部失败"的根本原因——与服务端防自动化升级无关。
详见 ``config.AES_KEY`` / ``config.AES_IV``。

服务端前端计算偏移量的真值（已还原）
------------------------------------
``Login.min.js`` 的 ``SliderCaptcha.handleDragEnd``：

    var v = $(".bg_slider")[0].offsetLeft;      // 拼图块画布的 CSS left
    $.ajax({ url: ".../CheckSliderImg&p=" + Security.EncryptAES(v), type: "Post" })

而 ``handleDragMove`` 中：

    bg_slider.style.left = (dx / 202 * 180)      // dx 为鼠标水平位移(0~202)

即服务端收到的是**拼图块在其画布中的最终 left 值**，等价于把拼图块
平移到缺口处的偏移量。本模块用 NCC 归一化互相关直接求出该偏移量。

实测：连续 8 轮真实验证，Top-1 猜测 8/8 命中（每轮仅 1 次请求）。
"""

import base64
import io
import json

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy 缺失时降级为不可用
    np = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover - PIL 缺失时降级为不可用
    Image = None


# 服务端背景图/拼图块的原始尺寸（用于坐标换算）
BG_WIDTH = 300
BG_HEIGHT = 150
SLIDER_WIDTH = 62
SLIDER_HEIGHT = 150

# 缺口只在背景中部出现（服务端不会把缺口放在最左/最右边缘），
# 该范围同时用于排除 NCC 误匹配到纯色边缘的假峰。
MIN_GAP_X = 10
MAX_GAP_X = BG_WIDTH - SLIDER_WIDTH - 10  # = 228


class SliderSolverError(Exception):
    """滑块求解相关异常（网络失败、图片解码失败等）"""


def is_available() -> bool:
    """求解器依赖是否就绪（numpy + PIL）"""
    return np is not None and Image is not None


def decode_data_url(data_url: str):
    """把 ``data:image/xxx;base64,....`` 转为 PIL Image（RGB）"""
    if not data_url:
        raise SliderSolverError("空的图片数据")
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    raw = base64.b64decode(data_url)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def fetch_slider_images(session, timeout: int = 15):
    """
    拉取滑块图片（步骤1）。

    该 GET 会建立/续用 ASP.NET_SessionId，**必须**复用传入的同一 Session。

    Args:
        session: requests.Session 实例
        timeout: 超时秒数

    Returns:
        (background_pil, slider_pil) 二元组
    """
    from config import BASE_URL

    if not is_available():
        raise SliderSolverError("缺少 numpy 或 PIL，无法解码滑块图片")

    url = BASE_URL + "/ajax/SliderValidImg.ashx?method=GetSliderImg"
    resp = session.get(url, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=timeout)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        # 服务端曾以 text/plain 返回 JSON，这里兼容处理
        data = json.loads(resp.text.strip().strip('"'))

    if "background" not in data or "slider" not in data:
        raise SliderSolverError("滑块接口返回缺少 background/slider 字段")

    return decode_data_url(data["background"]), decode_data_url(data["slider"])


def _to_gray_array(pil_image):
    """PIL Image -> 灰度 numpy 数组（float64）"""
    return np.asarray(pil_image.convert("L"), dtype=np.float64)


def _build_mask(slider_gray):
    """
    定位滑块 PNG 中的有效拼图块区域。

    PNG 转灰度后，透明区域为 0，而真实拼图块内容不会整体均匀，
    因此用「与均值的偏差」构造掩膜，排除四周透明留白。
    """
    mask = np.abs(slider_gray - slider_gray.mean()) > 12
    if mask.sum() < 50:
        # 极端情况：整张图近乎均匀，退化为全图参与匹配
        mask = np.ones_like(slider_gray, dtype=bool)
    return mask


def ncc_scores(background_gray, slider_gray):
    """
    计算每个候选 x 位置的归一化互相关（NCC）得分。

    返回按得分降序排列的 ``[(x, score), ...]`` 列表。
    """
    height, width = background_gray.shape
    mask = _build_mask(slider_gray)
    ys, xs = np.where(mask)
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())

    patch = slider_gray[y0:y1 + 1, x0:x1 + 1]
    pmask = mask[y0:y1 + 1, x0:x1 + 1]
    ph, pw = patch.shape

    # 拼图块在自身画布中的左边界 x0：拼图块需被平移 (best_x - x0) 才能覆盖缺口
    piece_offset = x0

    if ph > height or pw > width:
        raise SliderSolverError("拼图块尺寸大于背景图，无法匹配")

    scores = []
    for x in range(MIN_GAP_X, MAX_GAP_X + 1):
        if x + pw > width:
            break
        window = background_gray[y0:y0 + ph, x:x + pw]
        if window.shape != patch.shape:
            break
        a = patch[pmask] - patch[pmask].mean()
        b = window[pmask] - window[pmask].mean()
        denom = np.sqrt((a * a).sum() * (b * b).sum())
        scores.append((x, float((a * b).sum() / denom) if denom > 1e-9 else 0.0))

    scores.sort(key=lambda t: -t[1])
    return scores, piece_offset


def solve_trail(background_pil, slider_pil):
    """
    求解拼图块偏移量（无需人工拖动）。

    算法：把 slider 拼图块当作模板，在 background 上做归一化互相关（NCC），
    取相关峰位置。拼图块原始内容来自背景图同一区域，故峰值即为缺口位置。

    Args:
        background_pil: 背景图 PIL Image
        slider_pil: 滑块拼图块 PIL Image

    Returns:
        (trail, score, margin) —— trail 为提交给服务端的偏移量（int），
        score 为峰值相关系数，margin 为与次峰的差值（越大越可信）。
        无法求解时返回 (None, 0.0, 0.0)。
    """
    if not is_available():
        return None, 0.0, 0.0

    try:
        bg = _to_gray_array(background_pil)
        sl = _to_gray_array(slider_pil)
        scores, piece_offset = ncc_scores(bg, sl)
    except SliderSolverError:
        raise
    except Exception:
        return None, 0.0, 0.0

    if not scores:
        return None, 0.0, 0.0

    best_x, best_score = scores[0]
    margin = best_score - scores[1][1] if len(scores) > 1 else best_score

    # 服务端拿到的是拼图块在其画布中的最终 left，即 缺口x - 拼图块自身左边界
    trail = int(best_x - piece_offset)
    trail = max(0, min(BG_WIDTH, trail))
    return trail, float(best_score), float(margin)


def refine_candidates(trail: int, span: int = 6):
    """
    生成围绕初次猜测的候选偏移量（按「先近后远」排序）。

    服务端容差实测为 ±4px，正常情况下 Top-1 即命中；此列表仅用于
    极端图像（强压缩/低对比）导致 NCC 偏移时的兜底重试。

    Args:
        trail: 初次猜测的偏移量
        span: 向两侧扩展的最大像素数

    Returns:
        去重后的候选偏移量列表，trail 本身排在最前
    """
    ordered = [trail]
    for delta in range(1, span + 1):
        ordered.append(trail - delta)
        ordered.append(trail + delta)
    # 去重并保持顺序，同时过滤越界值
    seen = set()
    result = []
    for value in ordered:
        if value in seen:
            continue
        if value < 0 or value > BG_WIDTH:
            continue
        seen.add(value)
        result.append(value)
    return result
