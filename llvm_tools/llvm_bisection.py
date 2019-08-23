#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# Copyright 2019 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Performs bisection on LLVM based off a .JSON file."""

from __future__ import division
from __future__ import print_function

import argparse
import errno
import json
import os

from assert_not_in_chroot import VerifyOutsideChroot
from get_llvm_hash import CreateTempLLVMRepo
from get_llvm_hash import LLVMHash
from modify_a_tryjob import AddTryjob
from patch_manager import _ConvertToASCII
from update_tryjob_status import FindTryjobIndex
from update_tryjob_status import TryjobStatus


def is_file_and_json(json_file):
  """Validates that the file exists and is a JSON file."""
  return os.path.isfile(json_file) and json_file.endswith('.json')


def GetCommandLineArgs():
  """Parses the command line for the command line arguments."""

  # Default path to the chroot if a path is not specified.
  cros_root = os.path.expanduser('~')
  cros_root = os.path.join(cros_root, 'chromiumos')

  # Create parser and add optional command-line arguments.
  parser = argparse.ArgumentParser(
      description='Bisects LLVM via tracking a JSON file.')

  # Add argument for other change lists that want to run alongside the tryjob
  # which has a change list of updating a package's git hash.
  parser.add_argument(
      '--parallel',
      type=int,
      default=3,
      help='How many tryjobs to create between the last good version and '
      'the first bad version (default: %(default)s)')

  # Add argument for the good LLVM revision for bisection.
  parser.add_argument(
      '--start_rev',
      required=True,
      type=int,
      help='The good revision for the bisection.')

  # Add argument for the bad LLVM revision for bisection.
  parser.add_argument(
      '--end_rev',
      required=True,
      type=int,
      help='The bad revision for the bisection.')

  # Add argument for the absolute path to the file that contains information on
  # the previous tested svn version.
  parser.add_argument(
      '--last_tested',
      required=True,
      help='the absolute path to the file that contains the tryjobs')

  # Add argument for the absolute path to the LLVM source tree.
  parser.add_argument(
      '--src_path',
      help='the path to the LLVM source tree to use (used for retrieving the '
      'git hash of each version between the last good version and first bad '
      'version)')

  # Add argument for other change lists that want to run alongside the tryjob
  # which has a change list of updating a package's git hash.
  parser.add_argument(
      '--extra_change_lists',
      type=int,
      nargs='+',
      help='change lists that would like to be run alongside the change list '
      'of updating the packages')

  # Add argument for custom options for the tryjob.
  parser.add_argument(
      '--options',
      required=False,
      nargs='+',
      help='options to use for the tryjob testing')

  # Add argument for the builder to use for the tryjob.
  parser.add_argument(
      '--builder', required=True, help='builder to use for the tryjob testing')

  # Add argument for the description of the tryjob.
  parser.add_argument(
      '--description',
      required=False,
      nargs='+',
      help='the description of the tryjob')

  # Add argument for a specific chroot path.
  parser.add_argument(
      '--chroot_path',
      default=cros_root,
      help='the path to the chroot (default: %(default)s)')

  # Add argument for the log level.
  parser.add_argument(
      '--log_level',
      default='none',
      choices=['none', 'quiet', 'average', 'verbose'],
      help='the level for the logs (default: %(default)s)')

  args_output = parser.parse_args()

  assert args_output.start_rev < args_output.end_rev, (
      'Start revision %d is >= end revision %d' % (args_output.start_rev,
                                                   args_output.end_rev))

  if args_output.last_tested and not args_output.last_tested.endswith('.json'):
    raise ValueError(
        'Filed provided %s does not end in \'.json\'' % args_output.last_tested)

  return args_output


def _ValidateStartAndEndAgainstJSONStartAndEnd(start, end, json_start,
                                               json_end):
  """Valides that the command line arguments are the same as the JSON."""

  if start != json_start or end != json_end:
    raise ValueError('The start %d or the end %d version provided is '
                     'different than \'start\' %d or \'end\' %d in the .JSON '
                     'file' % (start, end, json_start, json_end))


def GetStartAndEndRevision(start, end, tryjobs):
  """Gets the start and end intervals in 'json_file'.

  Args:
    start: The start version of the bisection provided via the command line.
    end: The end version of the bisection provided via the command line.
    tryjobs: A list of tryjobs where each element is in the following format:
    [
        {[TRYJOB_INFORMATION]},
        {[TRYJOB_INFORMATION]},
        ...,
        {[TRYJOB_INFORMATION]}
    ]

  Returns:
    The new start version and end version for bisection.

  Raises:
    ValueError: The value for 'status' is missing or there is a mismatch
    between 'start' and 'end' compared to the 'start' and 'end' in the JSON
    file.
    AssertionError: The new start version is >= than the new end version.
  """

  if not tryjobs:
    return start, end, []

  # Verify that each tryjob has a value for the 'status' key.
  for cur_tryjob_dict in tryjobs:
    if not cur_tryjob_dict.get('status', None):
      raise ValueError('\'status\' is missing or has no value, please '
                       'go to %s and update it' % cur_tryjob_dict['link'])

  all_bad_revisions = [end]
  all_bad_revisions.extend(cur_tryjob['rev']
                           for cur_tryjob in tryjobs
                           if cur_tryjob['status'] == TryjobStatus.BAD.value)

  # The minimum value for the 'bad' field in the tryjobs is the new end
  # version.
  bad_rev = min(all_bad_revisions)

  all_good_revisions = [start]
  all_good_revisions.extend(cur_tryjob['rev']
                            for cur_tryjob in tryjobs
                            if cur_tryjob['status'] == TryjobStatus.GOOD.value)

  # The maximum value for the 'good' field in the tryjobs is the new start
  # version.
  good_rev = max(all_good_revisions)

  # The good version should always be strictly less than the bad version;
  # otherwise, bisection is broken.
  assert good_rev < bad_rev, ('Bisection is broken because %d (good) is >= '
                              '%d (bad)' % (good_rev, bad_rev))

  # Find all revisions that are 'pending' within 'good_rev' and 'bad_rev'.
  #
  # NOTE: The intent is to not launch tryjobs between 'good_rev' and 'bad_rev'
  # that have already been launched (this list is used when constructing the
  # list of revisions to launch tryjobs for).
  pending_revisions = [
      tryjob['rev']
      for tryjob in tryjobs
      if tryjob['status'] == TryjobStatus.PENDING.value and
      good_rev < tryjob['rev'] < bad_rev
  ]

  return good_rev, bad_rev, pending_revisions


def GetRevisionsBetweenBisection(start, end, parallel, src_path,
                                 pending_revisions):
  """Gets the revisions between 'start' and 'end'.

  Sometimes, the LLVM source tree's revisions do not increment by 1 (there is
  a jump), so need to construct a list of all revisions that are NOT missing
  between 'start' and 'end'. Then, the step amount (i.e. length of the list
  divided by ('parallel' + 1)) will be used for indexing into the list.

  Args:
    start: The start revision.
    end: The end revision.
    parallel: The number of tryjobs to create between 'start' and 'end'.
    src_path: The absolute path to the LLVM source tree to use.
    pending_revisions: A list of 'pending' revisions that are between 'start'
    and 'end'.

  Returns:
    A list of revisions between 'start' and 'end'.
  """

  new_llvm = LLVMHash()

  valid_revisions = []

  # Start at ('start' + 1) because 'start' is the good revision.
  #
  # FIXME: Searching for each revision from ('start' + 1) up to 'end' in the
  # LLVM source tree is a quadratic algorithm. It's a good idea to optimize
  # this.
  for cur_revision in range(start + 1, end):
    try:
      if cur_revision not in pending_revisions:
        # Verify that the current revision exists by finding its corresponding
        # git hash in the LLVM source tree.
        new_llvm.GetGitHashForVersion(src_path, cur_revision)
        valid_revisions.append(cur_revision)
    except ValueError:
      # Could not find the git hash for the current revision.
      continue

  # ('parallel' + 1) so that the last revision in the list is not close to
  # 'end' (have a bit more coverage).
  index_step = len(valid_revisions) // (parallel + 1)

  if not index_step:
    index_step = 1

  # Starting at 'index_step' because the first element would be close to
  # 'start' (similar to ('parallel' + 1) for the last element).
  result = [valid_revisions[index] \
            for index in range(index_step, len(valid_revisions), index_step)]

  return result


def GetRevisionsListAndHashList(start, end, parallel, src_path,
                                pending_revisions):
  """Determines the revisions between start and end."""

  new_llvm = LLVMHash()

  with new_llvm.CreateTempDirectory() as temp_dir:
    with CreateTempLLVMRepo(temp_dir) as new_repo:
      if not src_path:
        src_path = new_repo

      # Get a list of revisions between start and end.
      revisions = GetRevisionsBetweenBisection(start, end, parallel, src_path,
                                               pending_revisions)

      git_hashes = [
          new_llvm.GetGitHashForVersion(src_path, rev) for rev in revisions
      ]

  assert revisions, ('No revisions between start %d and end %d to create '
                     'tryjobs.' % (start, end))

  return revisions, git_hashes


def main():
  """Bisects LLVM based off of a .JSON file.

  Raises:
    AssertionError: The script was run inside the chroot.
  """

  VerifyOutsideChroot()

  args_output = GetCommandLineArgs()

  update_packages = [
      'sys-devel/llvm', 'sys-libs/compiler-rt', 'sys-libs/libcxx',
      'sys-libs/libcxxabi', 'sys-libs/llvm-libunwind'
  ]

  patch_metadata_file = 'PATCHES.json'

  start = args_output.start_rev
  end = args_output.end_rev

  try:
    with open(args_output.last_tested) as f:
      bisect_contents = _ConvertToASCII(json.load(f))
  except IOError as err:
    if err.errno != errno.ENOENT:
      raise
    bisect_contents = {'start': start, 'end': end, 'jobs': []}

  _ValidateStartAndEndAgainstJSONStartAndEnd(
      start, end, bisect_contents['start'], bisect_contents['end'])

  # Pending revisions are between 'start_revision' and 'end_revision'.
  start_revision, end_revision, pending_revisions = GetStartAndEndRevision(
      start, end, bisect_contents['jobs'])

  revisions, git_hashes = GetRevisionsListAndHashList(
      start_revision, end_revision, args_output.parallel, args_output.src_path,
      pending_revisions)

  # Check if any revisions that are going to be added as a tryjob exist already
  # in the 'jobs' list.
  for rev in revisions:
    if FindTryjobIndex(rev, bisect_contents['jobs']) is not None:
      raise ValueError('Revision %d exists already in \'jobs\'' % rev)

  try:
    for svn_revision, git_hash in zip(revisions, git_hashes):
      tryjob_dict = AddTryjob(update_packages, git_hash, svn_revision,
                              args_output.chroot_path, patch_metadata_file,
                              args_output.extra_change_lists,
                              args_output.options, args_output.builder,
                              args_output.log_level, svn_revision)

      bisect_contents['jobs'].append(tryjob_dict)
  finally:
    # Do not want to lose progress if there is an exception.
    if args_output.last_tested:
      new_file = '%s.new' % args_output.last_tested
      with open(new_file, 'w') as json_file:
        json.dump(bisect_contents, json_file, indent=4, separators=(',', ': '))

        os.rename(new_file, args_output.last_tested)


if __name__ == '__main__':
  main()
