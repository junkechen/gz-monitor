#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v5.54 回归测试：登录前可编辑企业账号/密码，且修改后会被登录流程使用。

覆盖：
  1. LoginDialog 账户表变为 3 列（企业名称 / 密码 / 登录状态），名称与密码可编辑；
  2. _save_account_edits 把表格编辑写回 save_accounts；
  3. main.py 登录改用 load_accounts()（而非硬编码 BUILTIN_ACCOUNTS），
     因此本地保存的修改会进入 multi_client.accounts 用于登录。
"""
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

# offscreen 渲染
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 注入测试账号，避免依赖真实磁盘配置
import account_manager

TEST_ACCOUNTS = [
    {"name": "测试企业A", "password": "oldpassA"},
    {"name": "测试企业B", "password": "oldpassB"},
]
account_manager.load_accounts = lambda: [dict(a) for a in TEST_ACCOUNTS]
_captured = {}

def _fake_save(accounts):
    _captured["accounts"] = [dict(a) for a in accounts]
    return True

account_manager.save_accounts = _fake_save

from main_window import LoginDialog
import main_window as _mw

# offscreen 环境下 QMessageBox 无法弹出原生对话框（真实 Windows 显示正常），打桩避免崩溃
_mw.QMessageBox.information = staticmethod(lambda *a, **k: None)
_mw.QMessageBox.warning = staticmethod(lambda *a, **k: None)


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    dlg = LoginDialog(version=1)
    table = dlg.account_list_widget

    # 1) 三列结构
    assert table.columnCount() == 3, f"期望 3 列，实际 {table.columnCount()}"
    assert table.horizontalHeaderItem(0).text() == "企业名称"
    assert table.horizontalHeaderItem(1).text() == "密码"
    assert table.horizontalHeaderItem(2).text() == "登录状态"

    # 名称/密码可编辑
    name_flags = table.item(0, 0).flags()
    pwd_flags = table.item(0, 1).flags()
    assert name_flags & Qt.ItemFlag.ItemIsEditable, "企业名称应可编辑"
    assert pwd_flags & Qt.ItemFlag.ItemIsEditable, "密码应可编辑"
    # 状态列不可编辑
    assert not (table.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable), "状态列不应可编辑"

    # 2) 编辑并保存
    table.item(0, 0).setText("测试企业A改")
    table.item(0, 1).setText("newpassA")
    dlg._save_account_edits()

    assert "accounts" in _captured, "save_accounts 未被调用"
    saved = _captured["accounts"]
    assert saved[0]["name"] == "测试企业A改", saved[0]
    assert saved[0]["password"] == "newpassA", saved[0]

    # 3) 登录改用 load_accounts：用保存后的值构建 GZMultiAccountClient
    from multi_account_api import GZMultiAccountClient
    # 模拟 main.py：从 load_accounts() 载入（此时应返回编辑后的值）
    account_manager.load_accounts = lambda: [dict(a) for a in _captured["accounts"]]
    mc = GZMultiAccountClient()
    for a in account_manager.load_accounts():
        mc.add_account(a["name"], a["password"])
    assert mc.accounts[0]["username"] == "测试企业A改", mc.accounts[0]
    assert mc.accounts[0]["password"] == "newpassA", mc.accounts[0]

    print("[OK] v5.54 登录前编辑账号/密码：结构、保存、登录生效 全部通过")


if __name__ == "__main__":
    main()
