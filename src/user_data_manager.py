# -*- coding: utf-8 -*-
"""
用户数据管理模块
负责管理用户配置和数据存储，支持跨电脑使用
"""
import os
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# 用户数据目录配置
APP_NAME = "GZ_Monitor"

def get_user_data_dir() -> Path:
    """
    获取用户数据目录
    Windows: C:/Users/Username/AppData/Roaming/GZ_Monitor
    macOS: ~/Library/Application Support/GZ_Monitor
    Linux: ~/.local/share/GZ_Monitor
    """
    if sys.platform == "win32":
        data_dir = Path(os.getenv('APPDATA')) / APP_NAME
    elif sys.platform == "darwin":
        data_dir = Path.home() / "Library" / "Application Support" / APP_NAME
    else:  # Linux and others
        data_dir = Path.home() / ".local" / "share" / APP_NAME

    # 创建目录
    data_dir.mkdir(parents=True, exist_ok=True)

    return data_dir

def get_config_file_path() -> Path:
    """获取配置文件路径"""
    return get_user_data_dir() / "user_config.json"

def get_accounts_file_path() -> Path:
    """获取账户文件路径"""
    return get_user_data_dir() / "accounts.json"

def get_data_file_path() -> Path:
    """获取数据文件路径"""
    return get_user_data_dir() / "monitor_data.json"

def load_user_config() -> Dict[str, Any]:
    """加载用户配置"""
    config_file = get_config_file_path()

    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            return {}

    return {}

def save_user_config(config: Dict[str, Any]) -> bool:
    """保存用户配置"""
    config_file = get_config_file_path()

    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存配置文件失败: {e}")
        return False

def load_user_accounts() -> list:
    """加载用户账户"""
    accounts_file = get_accounts_file_path()

    if accounts_file.exists():
        try:
            with open(accounts_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载账户文件失败: {e}")
            return []

    return []

def save_user_accounts(accounts: list) -> bool:
    """保存用户账户"""
    accounts_file = get_accounts_file_path()

    try:
        with open(accounts_file, 'w', encoding='utf-8') as f:
            json.dump(accounts, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存账户文件失败: {e}")
        return False

def save_monitor_data(data: Dict[str, Any]) -> bool:
    """保存监测数据"""
    data_file = get_data_file_path()

    try:
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存数据文件失败: {e}")
        return False

def get_app_info_file_path() -> Path:
    """获取应用信息文件路径"""
    return get_user_data_dir() / "app_info.json"

def save_app_info(info: Dict[str, Any]) -> bool:
    """保存应用信息"""
    info_file = get_app_info_file_path()

    try:
        with open(info_file, 'w', encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存应用信息失败: {e}")
        return False

def load_app_info() -> Dict[str, Any]:
    """加载应用信息"""
    info_file = get_app_info_file_path()

    if info_file.exists():
        try:
            with open(info_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载应用信息失败: {e}")
            return {}

    return {
        "version": "1.0.0",
        "first_run": True,
        "install_date": None,
        "last_run": None,
    }

def is_first_run() -> bool:
    """检查是否首次运行"""
    info = load_app_info()
    return info.get("first_run", True)

def mark_first_run_completed():
    """标记首次运行已完成"""
    info = load_app_info()
    info["first_run"] = False
    from datetime import datetime
    info["install_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_app_info(info)

def update_last_run():
    """更新最后运行时间"""
    info = load_app_info()
    from datetime import datetime
    info["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_app_info(info)

def get_user_data_dir_info() -> Dict[str, str]:
    """获取用户数据目录信息"""
    data_dir = get_user_data_dir()

    return {
        "data_dir": str(data_dir),
        "config_file": str(get_config_file_path()),
        "accounts_file": str(get_accounts_file_path()),
        "data_file": str(get_data_file_path()),
        "app_info_file": str(get_app_info_file_path()),
        "exists": data_dir.exists(),
    }

if __name__ == "__main__":
    # 测试
    info = get_user_data_dir_info()
    print("用户数据目录信息:")
    for key, value in info.items():
        print(f"  {key}: {value}")

    # 测试保存和加载配置
    test_config = {"refresh_interval": 60, "theme": "dark"}
    save_user_config(test_config)
    loaded_config = load_user_config()
    print(f"\n测试配置: {loaded_config}")

    # 检查首次运行
    print(f"\n是否首次运行: {is_first_run()}")
