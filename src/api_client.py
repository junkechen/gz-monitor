# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - API通信模块
负责登录（含滑块验证自动化）、数据查询等
"""

import requests
import time
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from config import BASE_URL, AES_KEY, AES_IV


def aes_encrypt(text: str) -> str:
    """AES-256-CBC 加密，输出 hex 字符串"""
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    ct = cipher.encrypt(pad(text.encode('utf-8'), AES.block_size))
    return ct.hex()


class GZApiClient:
    """GZ安环API客户端"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        })
        self.logged_in = False
        self.enterprise_name = ""
        self._session_id = ""

        # ── 网络请求配置 ─────────────────────────────────────────────────────
        self._max_retries = 3           # 最大重试次数
        self._retry_delay = 1.0        # 重试间隔（秒）
        self._request_timeout = 30      # 默认请求超时（秒）

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        带重试机制的请求方法
        自动处理连接错误和超时
        """
        timeout = kwargs.pop('timeout', self._request_timeout)
        max_retries = kwargs.pop('max_retries', self._max_retries)

        last_error = None
        for attempt in range(max_retries):
            try:
                resp = self.session.request(method, url, timeout=timeout, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.exceptions.ConnectionError as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(self._retry_delay * (attempt + 1))  # 指数退避
            except requests.exceptions.Timeout as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(self._retry_delay * (attempt + 1))
            except requests.exceptions.HTTPError as e:
                # 4xx 错误不重试
                raise

        raise last_error

    def _url(self, path: str) -> str:
        return BASE_URL + path

    def login(self, username: str, password: str, progress_callback=None) -> dict:
        """
        完整4步登录流程
        返回: {"success": bool, "message": str}
        """
        try:
            # 步骤1: 获取初始Session Cookie
            if progress_callback:
                progress_callback("步骤1/4: 获取会话...")
            resp = self.session.get(self._url('/'), timeout=15)
            resp.raise_for_status()
            if 'ASP.NET_SessionId' not in self.session.cookies:
                return {"success": False, "message": "无法获取会话Cookie，请检查网络连接"}

            # 步骤2: 获取滑块验证码
            if progress_callback:
                progress_callback("步骤2/4: 获取验证码...")
            resp = self.session.get(
                self._url('/ajax/SliderValidImg.ashx?method=GetSliderImg'),
                headers={'X-Requested-With': 'XMLHttpRequest'},
                timeout=15
            )
            resp.raise_for_status()

            # 步骤3: 枚举滑块偏移量（40~200，步长3）
            if progress_callback:
                progress_callback("步骤3/4: 破解滑块验证...")
            trail_found = None
            fail_count = 0  # 失败计数器
            for trail in range(40, 201, 3):
                enc_trail = aes_encrypt(str(trail))
                try:
                    check_resp = self.session.get(
                        self._url(f'/ajax/SliderValidImg.ashx?method=CheckSliderImg&p={enc_trail}'),
                        timeout=3  # 减少超时时间到3秒
                    )
                    result = check_resp.json()
                    if result.get('Code') == 0:
                        trail_found = trail
                        break
                except requests.exceptions.ConnectionError:
                    fail_count += 1
                    # 如果连续3次连接失败，快速返回
                    if fail_count >= 3:
                        return {"success": False, "message": "网络连接失败，请检查网络"}
                except requests.exceptions.Timeout:
                    fail_count += 1
                    # 如果连续3次超时，快速返回
                    if fail_count >= 3:
                        return {"success": False, "message": "连接超时，请检查网络"}
                except Exception:
                    pass
                time.sleep(0.05)

            if trail_found is None:
                return {"success": False, "message": "滑块验证失败，请稍后重试"}

            # 步骤4: 提交用户名和密码
            if progress_callback:
                progress_callback("步骤4/4: 验证账户...")
            enc_user = aes_encrypt(username)
            enc_pass = aes_encrypt(password)
            enc_trail2 = aes_encrypt(str(trail_found))

            login_resp = self.session.post(
                self._url('/Ajax/Login.ashx?Method=CheckLogin'),
                data=f'p1={enc_user}&p2={enc_pass}&p3={enc_trail2}',
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Referer': self._url('/Login/index.aspx'),
                },
                timeout=15
            )
            result_text = login_resp.text.strip().strip('"')

            if result_text == 'ok':
                self.logged_in = True
                self.enterprise_name = username
                return {"success": True, "message": "登录成功"}
            elif result_text == 'errorvalid':
                return {"success": False, "message": "验证码错误，请重试"}
            elif result_text == 'errorpassword':
                return {"success": False, "message": "密码错误"}
            elif result_text == 'usernotexist':
                return {"success": False, "message": "用户不存在"}
            else:
                return {"success": False, "message": f"登录失败: {result_text}"}

        except requests.exceptions.ConnectionError:
            return {"success": False, "message": "网络连接失败，请检查网络"}
        except requests.exceptions.Timeout:
            return {"success": False, "message": "连接超时，请检查网络"}
        except Exception as e:
            return {"success": False, "message": f"登录异常: {str(e)}"}

    def get_enterprise_subs(self) -> list:
        """获取企业排口列表（先GET页面触发刷新，再POST获取数据）"""
        try:
            import time as _time
            ts = str(int(_time.time() * 1000))
            # 先 GET 监控页面触发数据刷新（必须临时覆盖 Accept 为 text/html）
            self.session.get(
                self._url(f'/Web6/MonitorControl/Enterprise/EnterPriseRealTimeData.aspx?_={ts}'),
                headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9',
                    'Referer': self._url('/Web6/Main.aspx'),
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Upgrade-Insecure-Requests': '1',
                },
                timeout=15
            )
            # 再 POST 获取排口列表
            resp = self.session.post(
                self._url(f'/Web6/ajax/MonitorControl/Enterprise/EnterPriseRealTimeData.ashx?Method=GetEnterPriseTotalSubs&_={ts}'),
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'Referer': self._url('/Web6/MonitorControl/Enterprise/EnterPriseRealTimeData.aspx'),
                    'Cache-Control': 'no-cache', 'Pragma': 'no-cache',
                },
                data='',
                timeout=15
            )
            return resp.json()
        except Exception as e:
            return []

    def get_realtime_data(self) -> dict:
        """
        获取企业实时监测数据（先GET页面触发刷新，再POST获取数据）
        优化(v5.6)：GET后等待1.5秒 + 重试机制（检测"历史参考"）
        """
        import json as _json
        MAX_RETRY = 3
        RETRY_WAIT = 3
        GET_WAIT   = 1.5

        # 日志
        if getattr(sys, 'frozen', False):
            _log_dir = os.path.join(os.path.dirname(sys.executable), 'logs')
        else:
            _log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
        try:
            os.makedirs(_log_dir, exist_ok=True)
        except Exception:
            pass
        _log_file = os.path.join(_log_dir, 'api_debug.log')

        def _log(msg):
            print(msg)
            try:
                with open(_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            except Exception:
                pass

        for attempt in range(MAX_RETRY):
            try:
                import time as _t
                ts = str(int(_t.time() * 1000))

                # ── 1. GET 监控页面，触发服务端刷新 ─────────────────
                page_resp = self.session.get(
                    self._url(f'/Web6/MonitorControl/Enterprise/EnterPriseRealTimeData.aspx?_={ts}'),
                    headers={
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'zh-CN,zh;q=0.9',
                        'Referer': self._url('/Web6/Main.aspx'),
                        'Cache-Control': 'no-cache',
                        'Pragma': 'no-cache',
                        'Upgrade-Insecure-Requests': '1',
                    },
                    timeout=15
                )
                if 'Login' in page_resp.text or page_resp.status_code == 302:
                    _log(f"[API-old] Session过期 ({self.enterprise_name})")
                    self.logged_in = False
                    return {"total": 0, "rows": [], "sRows": []}

                # ── 1.5 等待服务端完成数据刷新 ────────────────────
                _log(f"[API-old] GET完成，等待 {GET_WAIT}s...")
                _t.sleep(GET_WAIT)

                # ── 2. POST 获取实时数据 ───────────────────────────
                resp = self.session.post(
                    self._url(f'/Web6/ajax/MonitorControl/Enterprise/EnterPriseRealTimeData.ashx?Method=GetEnterpriseRealtimeData&_={ts}'),
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'Referer': self._url('/Web6/MonitorControl/Enterprise/EnterPriseRealTimeData.aspx'),
                        'Cache-Control': 'no-cache',
                        'Pragma': 'no-cache',
                    },
                    data='',
                    timeout=15
                )

                content_type = resp.headers.get('Content-Type', '')
                if 'html' in content_type.lower():
                    _log(f"[API-old] 返回HTML而非JSON")
                    self.logged_in = False
                    return {"total": 0, "rows": [], "sRows": []}

                result = resp.json()
                rows   = result.get('rows', [])
                s_rows = result.get('sRows', [])
                total_rows = len(rows) + len(s_rows)

                # ── 3. 检查"历史参考" ─────────────────────────────
                history_count = 0
                for row in rows:
                    row_str = _json.dumps(row, ensure_ascii=False) if isinstance(row, dict) else str(row)
                    if '历史参考' in row_str:
                        history_count += 1
                for s_row in s_rows:
                    row_str = _json.dumps(s_row, ensure_ascii=False) if isinstance(s_row, dict) else str(s_row)
                    if '历史参考' in row_str:
                        history_count += 1

                _log(f"[API-old] 尝试 {attempt+1}/{MAX_RETRY}: {total_rows}条, 历史参考={history_count}")

                if history_count > total_rows // 2 and attempt < MAX_RETRY - 1:
                    _log(f"[API-old] 大部分为历史参考，{RETRY_WAIT}s后重试...")
                    _t.sleep(RETRY_WAIT)
                    continue

                _log(f"[API-old] 获取成功: {total_rows}条, 历史参考={history_count}")
                return result

            except Exception as e:
                _log(f"[API-old] 异常(尝试 {attempt+1}/{MAX_RETRY}): {e}")
                if attempt < MAX_RETRY - 1:
                    _t.sleep(RETRY_WAIT)
                    continue
                return {"total": 0, "rows": [], "sRows": []}

        return {"total": 0, "rows": [], "sRows": []}

    def get_minute_data_current_hour(self, subid: str, subtype_code: str, codes: str,
                                      use_corrected: bool = False) -> dict:
        """获取当前小时内的分钟数据（用于预测）
        
        Args:
            use_corrected: True=折算数据(showUpload=1)，用于热电厂；False=实测数据(showUpload=0)
        """
        from datetime import datetime, timedelta
        now = datetime.now()
        start = now.strftime('%Y-%m-%d %H:00')
        end = now.strftime('%Y-%m-%d %H:%M')
        result = self.query_history(subid, subtype_code, codes, start, end, index=-1,
                                    use_corrected=use_corrected)
        
        # 如果当前小时没有数据，尝试获取前一个小时的数据（用于00:00等边界情况）
        if not result.get('rows') and now.minute < 5:
            prev_hour = now - timedelta(hours=1)
            start = prev_hour.strftime('%Y-%m-%d %H:00')
            end = prev_hour.strftime('%Y-%m-%d %H:59')
            print(f"[API] 当前小时无数据，尝试获取前一小时: {start} ~ {end}")
            result = self.query_history(subid, subtype_code, codes, start, end, index=-1,
                                        use_corrected=use_corrected)
        
        return result

    def get_today_hour_data(self, subid: str, subtype_code: str, codes: str,
                            use_corrected: bool = False) -> dict:
        """获取当日内的小时数据（用于当日均值预测）
        
        Args:
            use_corrected: True=折算数据(showUpload=1)，用于热电厂；False=实测数据(showUpload=0)
        """
        from datetime import datetime, timedelta
        now = datetime.now()
        
        # 如果当前时间早于00:05，获取前一天的数据（跨天边界情况）
        if now.hour == 0 and now.minute < 5:
            prev_day = now - timedelta(days=1)
            start = prev_day.strftime('%Y-%m-%d 00:00')
            end = prev_day.strftime('%Y-%m-%d 23:59')
            print(f"[API] 跨天边界，获取前一天数据: {start} ~ {end}")
        else:
            start = now.strftime('%Y-%m-%d 00:00')
            end = now.strftime('%Y-%m-%d %H:00')
        
        return self.query_history(subid, subtype_code, codes, start, end, index=1,
                                  use_corrected=use_corrected)

    def get_enterprise_list(self, subtype: str = '51') -> list:
        """获取历史查询企业列表"""
        try:
            resp = self.session.get(
                self._url(f'/Web6/ajax/MonitorControl/Enterprise/historydata.ashx?Method=GetEnterprise&subtype={subtype}&selectcity=0&menuid=2'),
                headers={'Referer': self._url('/Web6/MonitorControl/Enterprise/HistoryData.aspx')},
                timeout=15
            )
            return resp.json()
        except Exception:
            return []

    def get_sub_list(self, entid: str, subtype: str = '51') -> list:
        """获取排口列表（含itemCode）"""
        try:
            resp = self.session.get(
                self._url(f'/Web6/ajax/MonitorControl/Enterprise/historydata.ashx?Method=GetSubs&subtype={subtype}&entid={entid}&menuid=2'),
                headers={'Referer': self._url('/Web6/MonitorControl/Enterprise/HistoryData.aspx')},
                timeout=15
            )
            return resp.json()
        except Exception:
            return []

    def query_history(self, subid: str, subtype: str, codes: str,
                      start: str, end: str, index: int = 1,
                      use_corrected: bool = False) -> dict:
        """
        查询历史数据
        index: -1=分钟, 1=小时, 2=日, 3=月
        use_corrected: True=折算数据(showUpload=1)，用于热电厂；False=实测数据(showUpload=0)
        """
        try:
            import urllib.parse
            encoded_codes = urllib.parse.quote(codes)
            show_upload = 1 if use_corrected else 0
            body = (
                f"Method=QueryHistoryReport&subid={subid}&subtype={subtype}&index={index}"
                f"&start={urllib.parse.quote(start)}&end={urllib.parse.quote(end)}"
                f"&codes={encoded_codes}&sort=1&showValidate=1&showUpload={show_upload}&selectcity=0"
            )
            resp = self.session.post(
                self._url('/ajax/WasteGas/QueryAnalysis/HistoryReportQUIDYN/HistoryReport.ashx'),
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Referer': self._url('/Web6/MonitorControl/Enterprise/HistoryData.aspx'),
                },
                data=body,
                timeout=30
            )
            return resp.json()
        except Exception as e:
            return {"total": 0, "rows": [], "error": str(e)}

    def logout(self):
        """登出"""
        self.logged_in = False
        self.session.cookies.clear()
