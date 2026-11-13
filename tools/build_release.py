#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GZ_Monitor 一键发布脚本（v5.54 引入）

功能：
  1. 自动递增 APP_RELEASE_VERSION（补丁号 +1）
  2. 在 CHANGELOG.md 顶部插入本次版本更新段落（旧"当前版本"标记下移）
  3. 生成版本化的 PyInstaller onefile spec 并构建 EXE
  4. git 提交 + 打标签 vX.Y.Z + 推送到远程仓库

用法：
  python tools/build_release.py "本次更新要点，可多行，或用 -f changes.md 指定"
  python tools/build_release.py -f changes.md
  python tools/build_release.py --no-git "只构建不提交"        # 仅构建 EXE
  python tools/build_release.py --dry-run "只打印将要执行的步骤"

依赖：项目根目录下 src/config.py、CHANGELOG.md、dist/*_onefile.spec
"""

import argparse
import datetime
import os
import re
import subprocess
import sys

PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(PROJ_ROOT, "src")
CONFIG_PATH = os.path.join(SRC_DIR, "config.py")
CHANGELOG_PATH = os.path.join(PROJ_ROOT, "CHANGELOG.md")
DIST_DIR = os.path.join(PROJ_ROOT, "dist")

VER_RE = re.compile(r'^APP_RELEASE_VERSION\s*=\s*"([^"]+)"', re.MULTILINE)


def read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def bump_version(ver):
    """补丁号 +1，保持原有段数：两段式 5.85 -> 5.86（项目实际约定），
    三段式 5.85.1 -> 5.85.2 亦兼容。

    旧实现把两段式版本号缺的第三段默认为 "0"，导致 5.85 -> 5.85.1，
    与全程 5.XX 两段式版本（tag v5.85、spec GZ_Monitor_v5.85_*.spec）不符。
    """
    m = re.match(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$", ver.strip())
    if not m:
        raise ValueError(f"无法解析版本号: {ver}")
    major, minor, patch = m.group(1), m.group(2), m.group(3)
    if patch is None:
        # 两段式：递增末段（即补丁位），仍是两段式
        return f"{major}.{int(minor) + 1}"
    return f"{major}.{minor}.{int(patch) + 1}"


def get_current_version():
    cfg = read_text(CONFIG_PATH)
    m = VER_RE.search(cfg)
    if not m:
        raise RuntimeError("在 config.py 中找不到 APP_RELEASE_VERSION")
    return m.group(1)


def set_version(new_ver):
    cfg = read_text(CONFIG_PATH)
    cfg = VER_RE.sub(f'APP_RELEASE_VERSION = "{new_ver}"', cfg, count=1)
    write_text(CONFIG_PATH, cfg)


def prepend_changelog(new_ver, title_suffix, body):
    """在 CHANGELOG.md 顶部插入新版本段落，并把旧的"当前版本"标记移除。"""
    today = datetime.date.today().strftime("%Y-%m-%d")
    lines = read_text(CHANGELOG_PATH).splitlines()

    # 移除旧的"✅ 当前版本"标记，改为"⏪ 上一版"
    out = []
    for ln in lines:
        if "✅ 当前版本" in ln:
            ln = ln.replace("✅ 当前版本", "⏪ 上一版")
        out.append(ln)

    # 找到第一个 "## " 版本标题行的位置（在文件头说明之后）
    insert_at = None
    for i, ln in enumerate(out):
        if ln.startswith("## v"):
            insert_at = i
            break
    if insert_at is None:
        # 没有历史版本段落，插到标题之后
        insert_at = 2

    new_block = [
        f"## v{new_ver}（{today}）✅ 当前版本",
        "",
        f"### 🚀 本次更新（{title_suffix}）",
    ]
    for bl in body.strip().splitlines():
        new_block.append(bl if bl.startswith("-") else f"- {bl}")
    new_block.append("")

    out = out[:insert_at] + new_block + out[insert_at:]
    write_text(CHANGELOG_PATH, "\n".join(out) + "\n")


def make_spec(new_ver, template_spec):
    """基于最新模板 spec 生成版本化 spec，仅替换 EXE 名与注释版本。

    EXE 名用正则替换「任意版本」而非固定占位：模板版本随每次发布递增，
    旧实现写死 GZ_Monitor_v5.53_Win7，模板升到 v5.85 后 replace 完全不命中，
    会把旧版 EXE 名原样带进新 spec（构建出错名 exe）。
    """
    tmpl = read_text(template_spec)
    tmpl = re.sub(r"GZ_Monitor_v[\d.]+_Win7",
                  f"GZ_Monitor_v{new_ver}_Win7", tmpl)
    tmpl = re.sub(r"^# v[\d.]+",
                  f"# v{new_ver}",
                  tmpl, count=1, flags=re.MULTILINE)
    # 确保 CHANGELOG.md 被打包（供「更新变化介绍」对话框读取）
    if "CHANGELOG.md" not in tmpl:
        tmpl = tmpl.replace(
            "    binaries=[],",
            "    binaries=[],\n"
            "    # 打包 CHANGELOG.md 供更新变化介绍对话框读取\n"
            "    datas=[(os.path.join(proj_root, 'CHANGELOG.md'), '.')],",
        )
        tmpl = tmpl.replace(
            "    datas=[],",
            "    datas=[(os.path.join(proj_root, 'CHANGELOG.md'), '.')],",
        )
    new_spec = os.path.join(DIST_DIR, f"GZ_Monitor_v{new_ver}_onefile.spec")
    write_text(new_spec, tmpl)
    return new_spec


def latest_template_spec():
    specs = [f for f in os.listdir(DIST_DIR) if f.endswith("_onefile.spec")]
    if not specs:
        raise RuntimeError("dist/ 下没有 *_onefile.spec 模板")
    # 取文件名中版本号最大的
    def ver_of(name):
        m = re.search(r"v(\d+)\.(\d+)(?:\.(\d+))?", name)
        if not m:
            return (0, 0, 0)
        return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
    specs.sort(key=ver_of)
    return os.path.join(DIST_DIR, specs[-1])


def build_exe(spec_path):
    print(f"[BUILD] PyInstaller {spec_path}")
    subprocess.check_call(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", spec_path],
        cwd=PROJ_ROOT,
    )


def git_commit_and_push(new_ver, summary):
    cmds = [
        ["git", "add", "-A"],
        ["git", "commit", "-m",
         f"release: v{new_ver}\n\n{summary}"],
        ["git", "tag", f"v{new_ver}"],
        ["git", "push", "origin", "HEAD"],
        ["git", "push", "origin", f"v{new_ver}"],
    ]
    for c in cmds:
        print("[GIT]", " ".join(c))
        subprocess.check_call(c, cwd=PROJ_ROOT)


def main():
    ap = argparse.ArgumentParser(description="GZ_Monitor 一键发布")
    ap.add_argument("message", nargs="*", help="更新要点（多段用空格分隔）")
    ap.add_argument("-f", "--file", help="从 .md 文件读取更新要点")
    ap.add_argument("--no-git", action="store_true", help="只构建不提交/推送")
    ap.add_argument("--dry-run", action="store_true", help="只打印步骤不执行")
    args = ap.parse_args()

    body = ""
    if args.file:
        body = read_text(args.file)
    elif args.message:
        body = " ".join(args.message)
    else:
        body = "(请通过命令行参数或 -f 指定本次更新要点)"

    cur = get_current_version()
    new_ver = bump_version(cur)
    summary = body.strip().splitlines()[0] if body.strip() else "常规更新"

    print(f"[INFO] 当前版本 v{cur} -> 新版本 v{new_ver}")

    if args.dry_run:
        print("[DRY-RUN] 将执行：")
        print(f"  1. config.py APP_RELEASE_VERSION -> {new_ver}")
        print(f"  2. CHANGELOG.md 顶部插入 v{new_ver} 段落")
        print(f"  3. 基于模板生成 spec 并 PyInstaller 构建")
        if not args.no_git:
            print(f"  4. git 提交 + tag v{new_ver} + push")
        return

    set_version(new_ver)
    prepend_changelog(new_ver, summary, body)
    spec = make_spec(new_ver, latest_template_spec())
    build_exe(spec)

    if not args.no_git:
        git_commit_and_push(new_ver, summary)
    print(f"[DONE] v{new_ver} 发布完成 -> dist/GZ_Monitor_v{new_ver}_Win7.exe")


if __name__ == "__main__":
    main()
