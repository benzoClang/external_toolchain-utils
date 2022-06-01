#!/usr/bin/env python3
# Copyright 2022 The ChromiumOS Authors.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for the patch_utils.py file."""

from pathlib import Path
import unittest
import unittest.mock as mock

import patch_utils as pu


class TestPatchUtils(unittest.TestCase):
  """Test the patch_utils."""

  def test_from_to_dict(self):
    """Test to and from dict conversion."""
    d = TestPatchUtils._default_json_dict()
    d['metadata'] = {
        'title': 'hello world',
        'info': [],
        'other_extra_info': {
            'extra_flags': [],
        }
    }
    e = pu.PatchEntry.from_dict(TestPatchUtils._mock_dir(), d)
    self.assertEqual(d, e.to_dict())

  def test_can_patch_version(self):
    """Test that patch application based on version is correct."""
    base_dict = TestPatchUtils._default_json_dict()
    workdir = TestPatchUtils._mock_dir()
    e1 = pu.PatchEntry.from_dict(workdir, base_dict)
    self.assertFalse(e1.can_patch_version(3))
    self.assertTrue(e1.can_patch_version(4))
    self.assertTrue(e1.can_patch_version(5))
    self.assertFalse(e1.can_patch_version(9))
    base_dict['version_range'] = {'until': 9}
    e2 = pu.PatchEntry.from_dict(workdir, base_dict)
    self.assertTrue(e2.can_patch_version(0))
    self.assertTrue(e2.can_patch_version(5))
    self.assertFalse(e2.can_patch_version(9))
    base_dict['version_range'] = {'from': 4}
    e3 = pu.PatchEntry.from_dict(workdir, base_dict)
    self.assertFalse(e3.can_patch_version(3))
    self.assertTrue(e3.can_patch_version(5))
    self.assertTrue(e3.can_patch_version(1 << 31))
    base_dict['version_range'] = {'from': 4, 'until': None}
    e4 = pu.PatchEntry.from_dict(workdir, base_dict)
    self.assertFalse(e4.can_patch_version(3))
    self.assertTrue(e4.can_patch_version(5))
    self.assertTrue(e4.can_patch_version(1 << 31))
    base_dict['version_range'] = {'from': None, 'until': 9}
    e5 = pu.PatchEntry.from_dict(workdir, base_dict)
    self.assertTrue(e5.can_patch_version(0))
    self.assertTrue(e5.can_patch_version(5))
    self.assertFalse(e5.can_patch_version(9))

  def test_parsed_hunks(self):
    """Test that we can parse patch file hunks."""
    m = mock.mock_open(read_data=_EXAMPLE_PATCH)

    def mocked_open(self, *args, **kwargs):
      return m(self, *args, **kwargs)

    with mock.patch.object(Path, 'open', mocked_open):
      e = pu.PatchEntry.from_dict(TestPatchUtils._mock_dir(),
                                  TestPatchUtils._default_json_dict())
      hunk_dict = e.parsed_hunks()

    m.assert_called()
    filename1 = 'clang/lib/Driver/ToolChains/Clang.cpp'
    filename2 = 'llvm/lib/Passes/PassBuilder.cpp'
    self.assertEqual(set(hunk_dict.keys()), {filename1, filename2})
    hunk_list1 = hunk_dict[filename1]
    hunk_list2 = hunk_dict[filename2]
    self.assertEqual(len(hunk_list1), 1)
    self.assertEqual(len(hunk_list2), 2)

  def test_apply_success(self):
    """Test that we can call apply."""
    src_dir = TestPatchUtils._mock_dir('somewhere/llvm-project')
    patch_dir = TestPatchUtils._mock_dir()
    e = pu.PatchEntry.from_dict(patch_dir, TestPatchUtils._default_json_dict())
    with mock.patch('subprocess.run', mock.MagicMock()):
      result = e.apply(src_dir)
    self.assertTrue(result.succeeded)

  def test_parse_failed_patch_output(self):
    """Test that we can call parse `patch` output."""
    fixture = """
checking file a/b/c.cpp
Hunk #1 SUCCEEDED at 96 with fuzz 1.
Hunk #12 FAILED at 77.
Hunk #42 FAILED at 1979.
checking file x/y/z.h
Hunk #4 FAILED at 30.
checking file works.cpp
Hunk #1 SUCCEEDED at 96 with fuzz 1.
"""
    result = pu.parse_failed_patch_output(fixture)
    self.assertEqual(result['a/b/c.cpp'], [12, 42])
    self.assertEqual(result['x/y/z.h'], [4])
    self.assertNotIn('works.cpp', result)

  @staticmethod
  def _default_json_dict():
    return {
        'metadata': {
            'title': 'hello world',
        },
        'platforms': [],
        'rel_patch_path': 'x/y/z',
        'version_range': {
            'from': 4,
            'until': 9,
        }
    }

  @staticmethod
  def _mock_dir(path: str = 'a/b/c'):
    workdir = Path(path)
    workdir = mock.MagicMock(workdir)
    workdir.is_dir = lambda: True
    workdir.joinpath = lambda x: Path(path).joinpath(x)
    workdir.__truediv__ = lambda self, x: self.joinpath(x)
    return workdir


_EXAMPLE_PATCH = """
diff --git a/clang/lib/Driver/ToolChains/Clang.cpp b/clang/lib/Driver/ToolChains/Clang.cpp
index 5620a543438..099eb769ca5 100644
--- a/clang/lib/Driver/ToolChains/Clang.cpp
+++ b/clang/lib/Driver/ToolChains/Clang.cpp
@@ -3995,8 +3995,11 @@ void Clang::ConstructJob(Compilation &C, const JobAction &JA,
       Args.hasArg(options::OPT_dA))
     CmdArgs.push_back("-masm-verbose");

-  if (!TC.useIntegratedAs())
+  if (!TC.useIntegratedAs()) {
     CmdArgs.push_back("-no-integrated-as");
+    CmdArgs.push_back("-mllvm");
+    CmdArgs.push_back("-enable-call-graph-profile-sort=false");
+  }

   if (Args.hasArg(options::OPT_fdebug_pass_structure)) {
     CmdArgs.push_back("-mdebug-pass");
diff --git a/llvm/lib/Passes/PassBuilder.cpp b/llvm/lib/Passes/PassBuilder.cpp
index c5fd68299eb..4c6e15eeeb9 100644
--- a/llvm/lib/Passes/PassBuilder.cpp
+++ b/llvm/lib/Passes/PassBuilder.cpp
@@ -212,6 +212,10 @@ static cl::opt<bool>
     EnableCHR("enable-chr-npm", cl::init(true), cl::Hidden,
               cl::desc("Enable control height reduction optimization (CHR)"));

+static cl::opt<bool> EnableCallGraphProfileSort(
+    "enable-call-graph-profile-sort", cl::init(true), cl::Hidden,
+    cl::desc("Enable call graph profile pass for the new PM (default = on)"));
+
 extern cl::opt<bool> EnableHotColdSplit;
 extern cl::opt<bool> EnableOrderFileInstrumentation;

@@ -939,7 +943,8 @@ ModulePassManager PassBuilder::buildModuleOptimizationPipeline(
   // Add the core optimizing pipeline.
   MPM.addPass(createModuleToFunctionPassAdaptor(std::move(OptimizePM)));

-  MPM.addPass(CGProfilePass());
+  if (EnableCallGraphProfileSort)
+    MPM.addPass(CGProfilePass());

   // Now we need to do some global optimization transforms.
   // FIXME: It would seem like these should come first in the optimization
"""

if __name__ == '__main__':
  unittest.main()
