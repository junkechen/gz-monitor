# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 多账户API客户端
支持多账户登录并合并所有企业数据
"""

import sys
import requests
import time
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from config import BASE_URL, AES_KEY, AES_IV


def _get_log_dir() -> str:
    """获取日志目录：打包后用 EXE 同级 logs/，开发时用 src/../logs/"""
    import os as _os
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后：日志写到 EXE 文件同级 logs/ 目录
        base = _os.path.dirname(sys.executable)
    else:
        # 开发时：src/../logs/
        base = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')
    log_dir = _os.path.join(base, 'logs')
    _os.makedirs(log_dir, exist_ok=True)
    return log_dir



def aes_encrypt(text: str) -> str:
    """AES-256-CBC 加密，输出 hex 字符串"""
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    ct = cipher.encrypt(pad(text.encode('utf-8'), AES.block_size))
    return ct.hex()


class GZMultiAccountClient:
    """多账户API客户端 - 支持获取所有企业数据"""

    def __init__(self):
        self.accounts = []  # 账户列表
        self.clients = {}   # {username: GZApiClient}
        self.all_realtime_data = []  # 合并的实时数据
        self.all_subs_data = {}      # 合并的排口数据 {username: subs}

    def add_account(self, username: str, password: str):
        """添加账户"""
        self.accounts.append({"username": username, "password": password})

    def login_all(self, progress_callback=None) -> dict:
        """
        登录所有账户
        返回: {"success": bool, "message": str, "success_count": int, "fail_count": int}
        """
        success_count = 0
        fail_count = 0
        total = len(self.accounts)

        for idx, account in enumerate(self.accounts):
            username = account["username"]
            password = account["password"]

            if progress_callback:
                progress_callback(f"正在登录 {username} ({idx+1}/{total})...")

            # 创建单独的客户端
            client = GZApiClient()
            result = client.login(username, password, progress_callback=None)

            # 无论登录成功还是失败，都保留client实例
            self.clients[username] = client

            if result["success"]:
                success_count += 1
                if progress_callback:
                    progress_callback(f"✓ {username} 登录成功")
            else:
                fail_count += 1
                if progress_callback:
                    progress_callback(f"✗ {username} 登录失败: {result['message']}")

            time.sleep(0.5)  # 避免请求过快

        if success_count == 0:
            return {
                "success": False,
                "message": "所有账户登录失败",
                "success_count": 0,
                "fail_count": fail_count,
                "total": total
            }
        elif fail_count == 0:
            return {
                "success": True,
                "message": "所有账户登录成功",
                "success_count": success_count,
                "fail_count": 0,
                "total": total
            }
        else:
            return {
                "success": True,
                "message": f"部分账户登录成功 ({success_count}/{total})",
                "success_count": success_count,
                "fail_count": fail_count,
                "total": total
            }

    def get_all_enterprise_subs(self) -> dict:
        """
        获取所有企业的排口列表
        返回: {username: [sub_list]}
        """
        result = {}
        for username, client in self.clients.items():
            try:
                subs = client.get_enterprise_subs()
                result[username] = subs
            except Exception:
                result[username] = []
        return result

    def get_all_realtime_data(self) -> dict:
        """
        获取所有企业的实时数据（并发请求，避免主线程阻塞）
        返回: 合并后的实时数据，rows中包含企业名称字段
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        all_rows = []
        all_s_rows = []

        # 并发获取所有企业数据（每个client有独立session，线程安全）
        def _fetch_one(username_client_tuple):
            username, client = username_client_tuple
            try:
                data = client.get_realtime_data()
                rows = data.get('rows', [])
                s_rows = data.get('sRows', [])
                for row in rows:
                    row['ENTERPRISE_NAME'] = username
                for s_row in s_rows:
                    s_row['ENTERPRISE_NAME'] = username
                return (rows, s_rows)
            except Exception as e:
                print(f"获取 {username} 数据失败: {e}")
                return ([], [])

        # 最多8个并发线程
        max_workers = min(8, max(2, len(self.clients)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_fetch_one, item): item[0] for item in self.clients.items()}
            for future in as_completed(futures):
                username = futures[future]
                try:
                    rows, s_rows = future.result()
                    all_rows.extend(rows)
                    all_s_rows.extend(s_rows)
                except Exception as e:
                    print(f"获取 {username} 结果失败: {e}")
                    continue

        return {
            "total": len(all_rows),
            "rows": all_rows,
            "sRows": all_s_rows
        }

    def get_client_by_subid(self, subid: str) -> dict:
        """
        根据排口ID获取对应的客户端和企业信息
        返回: {"client": GZApiClient, "username": str} 或 None
        """
        # 将subid转换为整数进行比较（因为API返回的SubId是整数，但实时数据中可能是浮点数）
        try:
            subid_int = int(float(subid))
        except (ValueError, TypeError):
            subid_int = None

        for username, client in self.clients.items():
            try:
                subs = client.get_enterprise_subs()
                for sub in subs:
                    sub_subid = sub.get('SubId')
                    if sub_subid is not None:
                        try:
                            sub_subid_int = int(float(sub_subid))
                            if subid_int is not None and sub_subid_int == subid_int:
                                return {"client": client, "username": username}
                        except (ValueError, TypeError):
                            # 如果转换失败，尝试字符串比较
                            if str(sub_subid) == str(subid):
                                return {"client": client, "username": username}
            except Exception:
                continue
        return None

    def query_history(self, subid: str, subtype: str, codes: str,
                     start: str, end: str, index: int = 1, page: int = 1, rows: int = 1000,
                     use_corrected: bool = False) -> dict:
        """
        查询历史数据（根据排口ID找到对应的企业）

        Args:
            subid: 排口ID
            subtype: 排口类型（51=废水, 64=VOCs）
            codes: 监测项目代码逗号分隔
            start: 开始时间
            end: 结束时间
            index: 时间类型 (-1=分钟, 1=小时, 2=日, 3=月)
            page: 页码
            rows: 每页条数
            use_corrected: True=折算数据(showUpload=1)，用于热电厂；False=实测数据(showUpload=0)

        Returns:
            {"total": 总条数, "rows": 数据列表, "error": 错误信息}
        """
        client_info = self.get_client_by_subid(subid)
        if not client_info:
            return {"total": 0, "rows": [], "error": "未找到对应的企业"}

        client = client_info["client"]
        return client.query_history(subid, subtype, codes, start, end, index, page=page, rows=rows, use_corrected=use_corrected)

    def logout_all(self):
        """登出所有账户"""
        for client in self.clients.values():
            try:
                client.logout()
            except Exception:
                pass
        self.clients.clear()
        self.all_realtime_data.clear()


class GZApiClient:
    """单个账户API客户端"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
            # 防止服务端/代理缓存返回旧数据
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        })
        self.logged_in = False
        self.enterprise_name = ""
        self._session_id = ""  # 保存ASP.NET_SessionId用于调试

    def _url(self, path: str) -> str:
        return BASE_URL + path

    def login(self, username: str, password: str, progress_callback=None) -> dict:
        """
        完整4步登录流程（带重试机制）
        返回: {"success": bool, "message": str}
        """
        MAX_LOGIN_RETRY = 3
        import os as _os
        _log_dir = _get_log_dir()
        _os.makedirs(_log_dir, exist_ok=True)
        _log_file = _os.path.join(_log_dir, 'login_debug.log')
        def _log(msg):
            try:
                with open(_log_file, 'a', encoding='utf-8') as f:
                    import time as _tm
                    f.write(f"[{_tm.strftime('%H:%M:%S')}] [{username}] {msg}\n")
            except Exception:
                pass
        _log(f"开始登录 (最多{MAX_LOGIN_RETRY}次重试)")
        
        for _retry in range(MAX_LOGIN_RETRY):
            if _retry > 0:
                _log(f"第{_retry+1}次重试...")
                if progress_callback:
                    progress_callback(f"登录重试 ({_retry+1}/{MAX_LOGIN_RETRY})...")
                time.sleep(2)  # 重试前等待2秒
            try:
                # 步骤1: 获取初始Session Cookie
                if progress_callback:
                    progress_callback("步骤1/4: 获取会话...")
                _log("步骤1: 获取会话...")
                resp = self.session.get(self._url('/'), timeout=15)
                resp.raise_for_status()
                if 'ASP.NET_SessionId' not in self.session.cookies:
                    _log("无法获取会话Cookie")
                    if _retry < MAX_LOGIN_RETRY - 1:
                        continue
                    return {"success": False, "message": "无法获取会话Cookie，请检查网络连接"}

                # 步骤2: 获取滑块验证码
                if progress_callback:
                    progress_callback("步骤2/4: 获取验证码...")
                _log("步骤2: 获取滑块验证码...")
                resp = self.session.get(
                    self._url('/ajax/SliderValidImg.ashx?method=GetSliderImg'),
                    headers={'X-Requested-With': 'XMLHttpRequest'},
                    timeout=15
                )
                resp.raise_for_status()

                # 步骤3: 枚举滑块偏移量（40~200，步长3）
                if progress_callback:
                    progress_callback("步骤3/4: 破解滑块验证...")
                _log("步骤3: 枚举滑块偏移量...")
                trail_found = None
                fail_count = 0  # 失败计数器
                for trail in range(40, 201, 3):
                    enc_trail = aes_encrypt(str(trail))
                    try:
                        check_resp = self.session.get(
                            self._url(f'/ajax/SliderValidImg.ashx?method=CheckSliderImg&p={enc_trail}'),
                            timeout=5  # 增加超时到5秒
                        )
                        result = check_resp.json()
                        if result.get('Code') == 0:
                            trail_found = trail
                            break
                    except requests.exceptions.ConnectionError:
                        fail_count += 1
                        _log(f"连接失败 {fail_count}/3")
                        # 如果连续3次连接失败，快速返回
                        if fail_count >= 3:
                            _log("连续3次连接失败")
                            break
                    except requests.exceptions.Timeout:
                        fail_count += 1
                        _log(f"超时 {fail_count}/3")
                        # 如果连续3次超时，快速返回
                        if fail_count >= 3:
                            _log("连续3次超时")
                            break
                    except Exception as e:
                        _log(f"枚举异常: {str(e)[:50]}")
                        pass
                    time.sleep(0.05)

                if trail_found is None:
                    _log("滑块验证失败")
                    if _retry < MAX_LOGIN_RETRY - 1:
                        continue
                    return {"success": False, "message": "滑块验证失败，请稍后重试"}

                # 步骤4: 提交用户名和密码
                if progress_callback:
                    progress_callback("步骤4/4: 验证账户...")
                _log("步骤4: 提交登录...")
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
                _log(f"登录返回: {result_text}")

                if result_text == 'ok':
                    self.logged_in = True
                    self.enterprise_name = username
                    self._session_id = self.session.cookies.get('ASP.NET_SessionId', '')
                    _log("登录成功")
                    return {"success": True, "message": "登录成功"}
                elif result_text == 'errorvalid':
                    _log("验证码错误")
                    return {"success": False, "message": "验证码错误，请重试"}
                elif result_text == 'errorpassword':
                    _log("密码错误")
                    return {"success": False, "message": "密码错误"}
                elif result_text == 'usernotexist':
                    _log("用户不存在")
                    return {"success": False, "message": "用户不存在"}
                else:
                    _log(f"登录失败: {result_text}")
                    if _retry < MAX_LOGIN_RETRY - 1:
                        continue
                    return {"success": False, "message": f"登录失败: {result_text}"}

            except requests.exceptions.ConnectionError:
                _log(f"网络连接失败 (重试{_retry+1}/{MAX_LOGIN_RETRY})")
                if _retry >= MAX_LOGIN_RETRY - 1:
                    return {"success": False, "message": "网络连接失败，请检查网络"}
            except requests.exceptions.Timeout:
                _log(f"连接超时 (重试{_retry+1}/{MAX_LOGIN_RETRY})")
                if _retry >= MAX_LOGIN_RETRY - 1:
                    return {"success": False, "message": "连接超时，请检查网络"}
            except Exception as e:
                _log(f"登录异常: {str(e)[:100]} (重试{_retry+1}/{MAX_LOGIN_RETRY})")
                if _retry >= MAX_LOGIN_RETRY - 1:
                    return {"success": False, "message": f"登录异常: {str(e)}"}
        
        return {"success": False, "message": "登录失败（已达最大重试次数）"}

    def _ensure_session(self):
        """确保Session有效，如果ASP.NET_SessionId丢失则尝试重新获取"""
        current_sid = self.session.cookies.get('ASP.NET_SessionId', '')
        if not current_sid and self._session_id:
            # SessionId丢失，尝试恢复
            self.session.cookies.set('ASP.NET_SessionId', self._session_id)
        if not self.logged_in:
            return False
        return True

    def get_enterprise_subs(self) -> list:
        """获取企业排口列表（先GET页面触发刷新，再POST获取数据）"""
        try:
            if not self._ensure_session():
                return []
            import time as _time
            ts = str(int(_time.time() * 1000))

            # ── 先 GET 监控页面，触发服务端数据刷新 ───────────────────────────
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

            # ── 再 POST 获取排口列表 ─────────────────────────────────────────
            resp = self.session.post(
                self._url(f'/Web6/ajax/MonitorControl/Enterprise/EnterPriseRealTimeData.ashx?Method=GetEnterPriseTotalSubs&_={ts}'),
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'Referer': self._url('/Web6/MonitorControl/Enterprise/EnterPriseRealTimeData.aspx'),
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                },
                data='',
                timeout=15
            )
            return resp.json()
        except Exception as e:
            print(f"[API] get_enterprise_subs 异常 ({self.enterprise_name}): {e}")
            return []

    def get_realtime_data(self) -> dict:
        """
        获取企业实时监测数据（先GET页面触发刷新，再POST获取数据）
        优化(v5.6)：
          - GET 页面后等待1.5秒，给服务端完成数据刷新的时间
          - 增加重试机制：如果返回数据大部分为"历史参考"，等待后重试（最多3次）
          - 详细日志：将每次请求结果写入 logs/api_debug.log
        """
        import os as _os, json as _json

        MAX_RETRY = 2
        RETRY_WAIT = 1   # 秒（减少等待，避免卡顿）
        GET_WAIT   = 0.3  # GET 后等待秒数（减少，服务端刷新很快）

        # 日志目录
        _log_dir = _get_log_dir()
        _os.makedirs(_log_dir, exist_ok=True)
        _log_file = _os.path.join(_log_dir, 'api_debug.log')

        def _log(msg):
            print(msg)
            try:
                with open(_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            except Exception:
                pass

        for attempt in range(MAX_RETRY):
            try:
                if not self._ensure_session():
                    return {"total": 0, "rows": [], "sRows": []}
                ts = str(int(time.time() * 1000))

                # ── 1. GET 监控页面，触发服务端 Page_Load 刷新数据 ─────────
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
                    _log(f"[API] Session已过期 ({self.enterprise_name})，需要重新登录")
                    self.logged_in = False
                    return {"total": 0, "rows": [], "sRows": []}

                # ── 1.5 等待服务端完成数据刷新（监测周期1分钟）───────────
                _log(f"[API] GET页面完成，等待 {GET_WAIT}s 让服务端刷新数据...")
                time.sleep(GET_WAIT)

                # ── 2. POST 获取实时数据 ────────────────────────────────
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
                    _log(f"[API] 返回HTML而非JSON ({self.enterprise_name})，可能Session过期")
                    self.logged_in = False
                    return {"total": 0, "rows": [], "sRows": []}

                result = resp.json()
                rows   = result.get('rows', [])
                s_rows = result.get('sRows', [])
                total_rows = len(rows) + len(s_rows)

                # ── 3. 检查是否包含"历史参考" ──────────────────────────
                history_count = 0
                for row in rows:
                    row_str = _json.dumps(row, ensure_ascii=False) if isinstance(row, dict) else str(row)
                    if '历史参考' in row_str:
                        history_count += 1
                for s_row in s_rows:
                    row_str = _json.dumps(s_row, ensure_ascii=False) if isinstance(s_row, dict) else str(s_row)
                    if '历史参考' in row_str:
                        history_count += 1

                _log(f"[API] 尝试 {attempt+1}/{MAX_RETRY}: {total_rows} 条数据, 历史参考={history_count}")

                # 如果超过一半是"历史参考"，且还有重试次数，则等待后重试
                if history_count > total_rows // 2 and attempt < MAX_RETRY - 1:
                    _log(f"[API] 大部分数据为历史参考，{RETRY_WAIT}s后重试...")
                    time.sleep(RETRY_WAIT)
                    continue

                # 成功或已重试完，记录日志并返回结果
                if total_rows > 0:
                    first_row = (rows[0] if rows else None) or (s_rows[0] if s_rows else None) or {}
                    dt = first_row.get('DATETIME', first_row.get('DateTime', '?'))
                    _log(f"[API] 获取成功 ({self.enterprise_name}): {total_rows}条, 时间={dt}, 历史参考={history_count}")
                else:
                    _log(f"[API] 返回空数据 ({self.enterprise_name})")

                return result

            except Exception as e:
                _log(f"[API] 异常 ({self.enterprise_name}, 尝试 {attempt+1}/{MAX_RETRY}): {e}")
                if attempt < MAX_RETRY - 1:
                    time.sleep(RETRY_WAIT)
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
                      start: str, end: str, index: int = 1, page: int = 1, rows: int = 1000,
                      use_corrected: bool = False) -> dict:
        """
        查询历史数据（支持分页获取全量数据）

        Args:
            subid: 排口ID
            subtype: 排口类型（51=废水, 64=VOCs）
            codes: 监测项目代码逗号分隔（如 "302,311,316"）
            start: 开始时间
            end: 结束时间
            index: 时间类型 (-1=分钟, 1=小时, 2=日, 3=月)
            page: 页码（默认1，获取全量数据时传入1）
            rows: 每页条数（默认1000，尽可能多获取）
            use_corrected: True=折算数据(showUpload=1)，用于热电厂；False=实测数据(showUpload=0)

        Returns:
            {"total": 总条数, "rows": 数据列表, "error": 错误信息}
        """
        import urllib.parse
        
        encoded_codes = urllib.parse.quote(codes)
        show_upload = 1 if use_corrected else 0
        body = (
            f"Method=QueryHistoryReport&subid={subid}&subtype={subtype}&index={index}"
            f"&start={urllib.parse.quote(start)}&end={urllib.parse.quote(end)}"
            f"&codes={encoded_codes}&sort=1&showValidate=1&showUpload={show_upload}&selectcity=0"
            f"&page={page}&rows={rows}"
        )
        
        try:
            # ── v5.17: 日/月查询前 GET HistoryData.aspx 初始化 Session ───
            # 浏览器先加载历史数据页面再 AJAX 查询，软件直接 POST 会返回空数据
            if index >= 2:
                try:
                    self.session.get(
                        self._url('/Web6/MonitorControl/Enterprise/HistoryData.aspx'),
                        headers={
                            'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
                            'Referer': self._url('/Web6/Main.aspx'),
                        },
                        timeout=10
                    )
                except Exception:
                    pass

            resp = self.session.post(
                self._url('/ajax/WasteGas/QueryAnalysis/HistoryReportQUIDYN/HistoryReport.ashx'),
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Referer': self._url('/Web6/MonitorControl/Enterprise/HistoryData.aspx'),
                },
                data=body,
                timeout=30
            )
            result = resp.json()
            if not isinstance(result, dict):
                result = {"total": 0, "rows": [], "pf_flow": ""}
            
            # 防御：服务端可能返回 "rows": null
            _rows = result.get('rows') or []
            _row_count = len(_rows)
            _total = result.get('total', 0) or 0
            print(f"[HIST-DEBUG] index={index} subid={subid} start={start} end={end}")
            print(f"[HIST-DEBUG] 响应: rows={_row_count} total={_total}")
            try:
                import os as _os2, time as _t2
                _log_dir2 = _get_log_dir()
                _os2.makedirs(_log_dir2, exist_ok=True)
                with open(_os2.path.join(_log_dir2, 'history_debug.log'), 'a', encoding='utf-8') as _hf:
                    _hf.write(f"[{_t2.strftime('%H:%M:%S')}] [HIST-DEBUG] index={index} subid={subid} start={start} end={end}\n")
                    _hf.write(f"  rows={_row_count} total={_total} http={resp.status_code}\n")
                    if _row_count == 0:
                        _hf.write(f"  返回空! 响应前300字符: {resp.text[:300]}\n")
                        # 日/月返回空时，额外打印完整的 body 参数
                        _hf.write(f"  完整body: {body}\n")
            except Exception:
                pass
            
            return result
            
        except Exception as e:
            print(f"[HIST-DEBUG] 查询异常(index={index}): {e}")
            try:
                import os as _os3, time as _t3
                _log_dir3 = _get_log_dir()
                _os3.makedirs(_log_dir3, exist_ok=True)
                with open(_os3.path.join(_log_dir3, 'history_debug.log'), 'a', encoding='utf-8') as _hf2:
                    _hf2.write(f"[{_t3.strftime('%H:%M:%S')}] [HIST-ERROR] index={index}: {str(e)}\n")
            except Exception:
                pass
            return {"total": 0, "rows": [], "error": str(e)}

    def logout(self):
        """登出"""
        self.logged_in = False
        self.session.cookies.clear()
