# -*- coding: utf-8 -*-
"""
GZ安环监测系统 - 账户管理模块
支持三个版本：
  版本一：内置账户可改密码，不可新增/修改账户
  版本二：可输入权限密码3C123@后新增2个账户
  版本三：输入权限密码3C323@后自由管理
"""

import json
import os
import hashlib
from config import BUILTIN_ACCOUNTS, VERSION2_ADD_PASS, VERSION3_MANAGE_PASS


def get_config_path():
    """获取配置文件路径（EXE同目录）"""
    if hasattr(__import__('sys'), 'frozen'):
        base = os.path.dirname(__import__('sys').executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'gz_accounts.json')


def load_accounts() -> list:
    """加载账户列表（优先读取本地配置，否则用内置）"""
    path = get_config_path()
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('accounts', list(BUILTIN_ACCOUNTS))
        except Exception:
            pass
    return list(BUILTIN_ACCOUNTS)


def save_accounts(accounts: list):
    """保存账户列表到本地配置"""
    path = get_config_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'accounts': accounts}, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get_builtin_names() -> list:
    """获取内置账户名称列表"""
    return [a['name'] for a in BUILTIN_ACCOUNTS]


def verify_version2_pass(password: str) -> bool:
    return password == VERSION2_ADD_PASS


def verify_version3_pass(password: str) -> bool:
    return password == VERSION3_MANAGE_PASS


def load_warn_thresholds() -> dict:
    """加载预警阈值配置"""
    from config import DEFAULT_WARN_THRESHOLDS
    # 获取配置文件所在目录
    config_dir = os.path.dirname(get_config_path())
    path = os.path.join(config_dir, 'gz_thresholds.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return dict(DEFAULT_WARN_THRESHOLDS)


def save_warn_thresholds(thresholds: dict):
    """保存预警阈值配置"""
    # 获取配置文件所在目录
    config_dir = os.path.dirname(get_config_path())
    path = os.path.join(config_dir, 'gz_thresholds.json')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(thresholds, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False
