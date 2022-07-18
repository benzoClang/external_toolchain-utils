#!/usr/bin/env python3
# Copyright 2019 The ChromiumOS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests when handling patches."""

import json
from pathlib import Path
import tempfile
from typing import Callable
import unittest
from unittest import mock

import patch_manager
import patch_utils


class PatchManagerTest(unittest.TestCase):
  """Test class when handling patches of packages."""

  # Simulate behavior of 'os.path.isdir()' when the path is not a directory.
  @mock.patch.object(Path, 'is_dir', return_value=False)
  def testInvalidDirectoryPassedAsCommandLineArgument(self, mock_isdir):
    src_dir = '/some/path/that/is/not/a/directory'
    patch_metadata_file = '/some/path/that/is/not/a/file'

    # Verify the exception is raised when the command line argument for
    # '--filesdir_path' or '--src_path' is not a directory.
    with self.assertRaises(ValueError):
      patch_manager.main([
          '--src_path', src_dir, '--patch_metadata_file', patch_metadata_file
      ])
    mock_isdir.assert_called_once()

  # Simulate behavior of 'os.path.isfile()' when the patch metadata file is does
  # not exist.
  @mock.patch.object(Path, 'is_file', return_value=False)
  def testInvalidPathToPatchMetadataFilePassedAsCommandLineArgument(
      self, mock_isfile):
    src_dir = '/some/path/that/is/not/a/directory'
    patch_metadata_file = '/some/path/that/is/not/a/file'

    # Verify the exception is raised when the command line argument for
    # '--filesdir_path' or '--src_path' is not a directory.
    with mock.patch.object(Path, 'is_dir', return_value=True):
      with self.assertRaises(ValueError):
        patch_manager.main([
            '--src_path', src_dir, '--patch_metadata_file', patch_metadata_file
        ])
    mock_isfile.assert_called_once()

  @mock.patch('builtins.print')
  def testRemoveOldPatches(self, _):
    """Can remove old patches from PATCHES.json."""
    one_patch_dict = {
        'metadata': {
            'title': '[some label] hello world',
        },
        'platforms': [
            'chromiumos',
        ],
        'rel_patch_path': 'x/y/z',
        'version_range': {
            'from': 4,
            'until': 5,
        }
    }
    patches = [
        one_patch_dict,
        {
            **one_patch_dict, 'version_range': {
                'until': None
            }
        },
        {
            **one_patch_dict, 'version_range': {
                'from': 100
            }
        },
        {
            **one_patch_dict, 'version_range': {
                'until': 8
            }
        },
    ]
    cases = [
        (0, lambda x: self.assertEqual(len(x), 4)),
        (6, lambda x: self.assertEqual(len(x), 3)),
        (8, lambda x: self.assertEqual(len(x), 2)),
        (1000, lambda x: self.assertEqual(len(x), 2)),
    ]

    def _t(dirname: str, svn_version: int, assertion_f: Callable):
      json_filepath = Path(dirname) / 'PATCHES.json'
      with json_filepath.open('w', encoding='utf-8') as f:
        json.dump(patches, f)
      patch_manager.RemoveOldPatches(svn_version, Path(), json_filepath)
      with json_filepath.open('r', encoding='utf-8') as f:
        result = json.load(f)
      assertion_f(result)

    with tempfile.TemporaryDirectory(
        prefix='patch_manager_unittest') as dirname:
      for r, a in cases:
        _t(dirname, r, a)

  @mock.patch('builtins.print')
  @mock.patch.object(patch_utils, 'git_clean_context')
  def testCheckPatchApplies(self, _, mock_git_clean_context):
    """Tests whether we can apply a single patch for a given svn_version."""
    mock_git_clean_context.return_value = mock.MagicMock()
    with tempfile.TemporaryDirectory(
        prefix='patch_manager_unittest') as dirname:
      dirpath = Path(dirname)
      patch_entries = [
          patch_utils.PatchEntry(dirpath,
                                 metadata=None,
                                 platforms=[],
                                 rel_patch_path='another.patch',
                                 version_range={
                                     'from': 9,
                                     'until': 20,
                                 }),
          patch_utils.PatchEntry(dirpath,
                                 metadata=None,
                                 platforms=['chromiumos'],
                                 rel_patch_path='example.patch',
                                 version_range={
                                     'from': 1,
                                     'until': 10,
                                 }),
          patch_utils.PatchEntry(dirpath,
                                 metadata=None,
                                 platforms=['chromiumos'],
                                 rel_patch_path='patch_after.patch',
                                 version_range={
                                     'from': 1,
                                     'until': 5,
                                 })
      ]
      patches_path = dirpath / 'PATCHES.json'
      with patch_utils.atomic_write(patches_path, encoding='utf-8') as f:
        json.dump([pe.to_dict() for pe in patch_entries], f)

      def _harness1(version: int, return_value: patch_utils.PatchResult,
                    expected: patch_manager.GitBisectionCode):
        with mock.patch.object(
            patch_utils.PatchEntry,
            'apply',
            return_value=return_value,
        ) as m:
          result = patch_manager.CheckPatchApplies(
              version,
              dirpath,
              patches_path,
              'example.patch',
          )
          self.assertEqual(result, expected)
          m.assert_called()

      _harness1(1, patch_utils.PatchResult(True, {}),
                patch_manager.GitBisectionCode.GOOD)
      _harness1(2, patch_utils.PatchResult(True, {}),
                patch_manager.GitBisectionCode.GOOD)
      _harness1(2, patch_utils.PatchResult(False, {}),
                patch_manager.GitBisectionCode.BAD)
      _harness1(11, patch_utils.PatchResult(False, {}),
                patch_manager.GitBisectionCode.BAD)

      def _harness2(version: int, application_func: Callable,
                    expected: patch_manager.GitBisectionCode):
        with mock.patch.object(
            patch_utils,
            'apply_single_patch_entry',
            application_func,
        ):
          result = patch_manager.CheckPatchApplies(
              version,
              dirpath,
              patches_path,
              'example.patch',
          )
          self.assertEqual(result, expected)

      # Check patch can apply and fail with good return codes.
      def _apply_patch_entry_mock1(v, _, patch_entry, **__):
        return patch_entry.can_patch_version(v), None

      _harness2(
          1,
          _apply_patch_entry_mock1,
          patch_manager.GitBisectionCode.GOOD,
      )
      _harness2(
          11,
          _apply_patch_entry_mock1,
          patch_manager.GitBisectionCode.BAD,
      )

      # Early exit check, shouldn't apply later failing patch.
      def _apply_patch_entry_mock2(v, _, patch_entry, **__):
        if (patch_entry.can_patch_version(v)
            and patch_entry.rel_patch_path == 'patch_after.patch'):
          return False, {'filename': mock.Mock()}
        return True, None

      _harness2(
          1,
          _apply_patch_entry_mock2,
          patch_manager.GitBisectionCode.GOOD,
      )

      # Skip check, should exit early on the first patch.
      def _apply_patch_entry_mock3(v, _, patch_entry, **__):
        if (patch_entry.can_patch_version(v)
            and patch_entry.rel_patch_path == 'another.patch'):
          return False, {'filename': mock.Mock()}
        return True, None

      _harness2(
          9,
          _apply_patch_entry_mock3,
          patch_manager.GitBisectionCode.SKIP,
      )

  @mock.patch('patch_utils.git_clean_context', mock.MagicMock)
  def testUpdateVersionRanges(self):
    """Test the UpdateVersionRanges function."""
    with tempfile.TemporaryDirectory(
        prefix='patch_manager_unittest') as dirname:
      dirpath = Path(dirname)
      patches = [
          patch_utils.PatchEntry(workdir=dirpath,
                                 rel_patch_path='x.patch',
                                 metadata=None,
                                 platforms=None,
                                 version_range={
                                     'from': 0,
                                     'until': 2,
                                 }),
          patch_utils.PatchEntry(workdir=dirpath,
                                 rel_patch_path='y.patch',
                                 metadata=None,
                                 platforms=None,
                                 version_range={
                                     'from': 0,
                                     'until': 2,
                                 }),
      ]
      patches[0].apply = mock.MagicMock(return_value=patch_utils.PatchResult(
          succeeded=False, failed_hunks={'a/b/c': []}))
      patches[1].apply = mock.MagicMock(return_value=patch_utils.PatchResult(
          succeeded=True))
      results = patch_manager.UpdateVersionRangesWithEntries(
          1, dirpath, patches)
      # We should only have updated the version_range of the first patch,
      # as that one failed to apply.
      self.assertEqual(len(results), 1)
      self.assertEqual(results[0].version_range, {'from': 0, 'until': 1})
      self.assertEqual(patches[0].version_range, {'from': 0, 'until': 1})
      self.assertEqual(patches[1].version_range, {'from': 0, 'until': 2})


if __name__ == '__main__':
  unittest.main()
