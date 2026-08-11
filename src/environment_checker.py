# -*- coding: utf-8 -*-
"""
环境检测模块
检测Python环境和依赖包
"""
import sys
import subprocess
from typing import Dict, List, Tuple

# 必需的Python版本
REQUIRED_PYTHON_VERSION = (3, 8, 0)

# 必需的依赖包
REQUIRED_PACKAGES = {
    "PyQt5": "6.6.0",
    "PyQt5-WebEngine": "6.6.0",
    "requests": "2.31.0",
    "pycryptodome": "3.19.0",
    "plotly": "5.18.0",
    "pandas": "2.1.0",
    "openpyxl": "3.1.0",
    "kaleido": "0.2.1",
}

def check_python_version() -> Tuple[bool, str]:
    """检查Python版本"""
    current_version = sys.version_info[:3]

    if current_version >= REQUIRED_PYTHON_VERSION:
        return True, f"Python版本: {current_version[0]}.{current_version[1]}.{current_version[2]} ✓"
    else:
        required = ".".join(map(str, REQUIRED_PYTHON_VERSION))
        current = ".".join(map(str, current_version))
        msg = (f"Python版本过低\n"
               f"当前版本: {current}\n"
               f"需要版本: >= {required}")
        return False, msg

def check_package_installed(package_name: str) -> Tuple[bool, str, str]:
    """检查单个包是否已安装"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", package_name],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            # 提取版本号
            for line in result.stdout.split('\n'):
                if line.startswith('Version:'):
                    version = line.split(':', 1)[1].strip()
                    return True, version, "已安装"
            return True, "未知", "已安装"
        else:
            return False, "", "未安装"
    except Exception as e:
        return False, "", f"检查失败: {str(e)}"

def check_all_packages() -> Dict[str, Dict]:
    """检查所有依赖包"""
    results = {}

    for package_name, min_version in REQUIRED_PACKAGES.items():
        installed, version, status = check_package_installed(package_name)
        results[package_name] = {
            "installed": installed,
            "version": version,
            "min_version": min_version,
            "status": status
        }

    return results

def get_missing_packages() -> List[str]:
    """获取缺失的包"""
    missing = []

    results = check_all_packages()
    for package_name, info in results.items():
        if not info["installed"]:
            missing.append(package_name)

    return missing

def install_package(package_name: str) -> Tuple[bool, str]:
    """安装单个包"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package_name],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            return True, f"{package_name} 安装成功"
        else:
            return False, f"{package_name} 安装失败\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return False, f"{package_name} 安装超时"
    except Exception as e:
        return False, f"{package_name} 安装出错: {str(e)}"

def install_missing_packages() -> Tuple[bool, List[str]]:
    """安装所有缺失的包"""
    missing = get_missing_packages()

    if not missing:
        return True, ["所有依赖包已安装 ✓"]

    success_packages = []
    failed_packages = []

    for package_name in missing:
        success, msg = install_package(package_name)
        if success:
            success_packages.append(f"{package_name} 安装成功")
        else:
            failed_packages.append(f"{package_name} 安装失败")

    return len(failed_packages) == 0, success_packages + failed_packages

def run_environment_check() -> Dict:
    """运行完整的环境检查"""
    report = {
        "python_version": None,
        "packages": {},
        "missing_packages": [],
        "overall_status": "unknown",
    }

    # 检查Python版本
    py_ok, py_msg = check_python_version()
    report["python_version"] = {
        "ok": py_ok,
        "message": py_msg
    }

    # 检查所有包
    packages_result = check_all_packages()
    report["packages"] = packages_result

    # 找出缺失的包
    missing = [pkg for pkg, info in packages_result.items() if not info["installed"]]
    report["missing_packages"] = missing

    # 总体状态
    if py_ok and not missing:
        report["overall_status"] = "ready"
    elif py_ok and missing:
        report["overall_status"] = "missing_dependencies"
    else:
        report["overall_status"] = "python_version_issue"

    return report

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("GZ_Monitor 环境检测")
    print("=" * 60)

    report = run_environment_check()

    print(f"\n{report['python_version']['message']}\n")

    print("依赖包检查:")
    print("-" * 60)
    for package_name, info in report["packages"].items():
        status_symbol = "✓" if info["installed"] else "✗"
        version_str = info["version"] if info["installed"] else f"需要: {info['min_version']}"
        print(f"  {status_symbol} {package_name:25s} {version_str}")

    if report["missing_packages"]:
        print(f"\n缺失的包: {', '.join(report['missing_packages'])}")
        print("\n是否安装缺失的包? (y/n): ", end="")

        try:
            choice = input().strip().lower()
            if choice == 'y':
                print("\n正在安装依赖包...")
                success, messages = install_missing_packages()
                for msg in messages:
                    print(f"  {msg}")

                if success:
                    print("\n✓ 所有依赖包安装完成!")
                else:
                    print("\n✗ 部分包安装失败，请手动安装")
        except KeyboardInterrupt:
            print("\n已取消安装")

    print("\n" + "=" * 60)
    if report["overall_status"] == "ready":
        print("✓ 环境检查通过，可以运行程序")
    else:
        print("✗ 环境检查未通过，请解决上述问题")
    print("=" * 60)
