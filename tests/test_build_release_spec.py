# -*- coding: utf-8 -*-
"""build_release.py 自动发版脚本回归测试。

两个曾让「一键发布」出错的 bug（此前各版本均手动构建，脚本从未真正跑通）：
1. bump_version 把两段式版本 5.85 递增成 5.85.1（三段式），与项目全程
   5.XX 两段式约定（tag v5.85 / spec GZ_Monitor_v5.85_*.spec）不符。
   正确应为 5.85 -> 5.86。
2. make_spec 的 EXE 名占位写死 GZ_Monitor_v5.53_Win7；模板随每次发布递增，
   升到 v5.85 后 replace 完全不命中，新 spec 会残留旧版 EXE 名，
   导致构建出错误名字的 exe。修复为正则替换「任意版本」的 EXE 名。
"""
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import build_release as br


# 模拟一份 v5.85 模板 spec（只保留关心的行）
MIN_TEMPLATE = """# v5.85 GZ_Monitor onefile spec - 模板说明
# -*- mode: python -*-

a = Analysis(
    binaries=[],
    datas=[(os.path.join(proj_root, 'CHANGELOG.md'), '.')],
)
exe = EXE(
    name='GZ_Monitor_v5.85_Win7',
)
"""


class TestBumpVersion(unittest.TestCase):
    def test_two_segment_stays_two_segment(self):
        # 项目实际形态：5.XX，补丁位即末段
        self.assertEqual(br.bump_version("5.85"), "5.86")
        self.assertEqual(br.bump_version("5.53"), "5.54")
        self.assertEqual(br.bump_version("5.9"), "5.10")

    def test_three_segment(self):
        # 三段式亦兼容，递增末段
        self.assertEqual(br.bump_version("5.85.1"), "5.85.2")

    def test_v_prefix_and_whitespace(self):
        self.assertEqual(br.bump_version("v5.85"), "5.86")
        self.assertEqual(br.bump_version("  5.85  "), "5.86")

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            br.bump_version("not-a-version")


class TestMakeSpec(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmpl_path = os.path.join(tmp.name, "GZ_Monitor_v5.85_onefile.spec")
        br.write_text(self.tmpl_path, MIN_TEMPLATE)
        old_dist = br.DIST_DIR
        br.DIST_DIR = tmp.name
        self.addCleanup(setattr, br, "DIST_DIR", old_dist)

    def test_exe_name_replaced_without_leftover(self):
        out = br.make_spec("5.86", self.tmpl_path)
        text = br.read_text(out)
        self.assertIn("name='GZ_Monitor_v5.86_Win7'", text)
        # 任何旧版本 EXE 名都不得残留
        names = set(re.findall(r"GZ_Monitor_v[\d.]+_Win7", text))
        self.assertEqual(names, {"GZ_Monitor_v5.86_Win7"})

    def test_comment_version_replaced_and_desc_kept(self):
        out = br.make_spec("5.86", self.tmpl_path)
        text = br.read_text(out)
        self.assertTrue(text.startswith("# v5.86 GZ_Monitor onefile spec"))
        self.assertIn("模板说明", text)

    def test_output_spec_filename(self):
        out = br.make_spec("5.86", self.tmpl_path)
        self.assertTrue(out.endswith("GZ_Monitor_v5.86_onefile.spec"))

    def test_changelog_datas_not_duplicated(self):
        # 模板已含 CHANGELOG.md，不应被二次注入
        out = br.make_spec("5.86", self.tmpl_path)
        text = br.read_text(out)
        self.assertEqual(text.count("CHANGELOG.md"), 1)


if __name__ == "__main__":
    unittest.main()
