#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for nightly_revert_checker."""


import io
import unittest
from unittest.mock import patch

import cros_utils.tiny_render as tiny_render
import get_upstream_patch
import nightly_revert_checker
import revert_checker


# pylint: disable=protected-access


class Test(unittest.TestCase):
    """Tests for nightly_revert_checker."""

    def test_email_rendering_works_for_singular_revert(self):
        def prettify_sha(sha: str) -> tiny_render.Piece:
            return "pretty_" + sha

        def get_sha_description(sha: str) -> tiny_render.Piece:
            return "subject_" + sha

        email = nightly_revert_checker._generate_revert_email(
            repository_name="${repo}",
            friendly_name="${name}",
            sha="${sha}",
            prettify_sha=prettify_sha,
            get_sha_description=get_sha_description,
            new_reverts=[
                revert_checker.Revert(
                    sha="${revert_sha}", reverted_sha="${reverted_sha}"
                )
            ],
        )

        expected_email = nightly_revert_checker._Email(
            subject="[revert-checker/${repo}] new revert discovered across ${name}",
            body=[
                "It looks like there may be a new revert across ${name} (",
                "pretty_${sha}",
                ").",
                tiny_render.line_break,
                tiny_render.line_break,
                "That is:",
                tiny_render.UnorderedList(
                    [
                        [
                            "pretty_${revert_sha}",
                            " (appears to revert ",
                            "pretty_${reverted_sha}",
                            "): ",
                            "subject_${revert_sha}",
                        ]
                    ]
                ),
                tiny_render.line_break,
                "PTAL and consider reverting them locally.",
            ],
        )

        self.assertEqual(email, expected_email)

    def test_email_rendering_works_for_multiple_reverts(self):
        def prettify_sha(sha: str) -> tiny_render.Piece:
            return "pretty_" + sha

        def get_sha_description(sha: str) -> tiny_render.Piece:
            return "subject_" + sha

        email = nightly_revert_checker._generate_revert_email(
            repository_name="${repo}",
            friendly_name="${name}",
            sha="${sha}",
            prettify_sha=prettify_sha,
            get_sha_description=get_sha_description,
            new_reverts=[
                revert_checker.Revert(
                    sha="${revert_sha1}", reverted_sha="${reverted_sha1}"
                ),
                revert_checker.Revert(
                    sha="${revert_sha2}", reverted_sha="${reverted_sha2}"
                ),
                # Keep this out-of-order to check that we sort based on SHAs
                revert_checker.Revert(
                    sha="${revert_sha0}", reverted_sha="${reverted_sha0}"
                ),
            ],
        )

        expected_email = nightly_revert_checker._Email(
            subject="[revert-checker/${repo}] new reverts discovered across "
            "${name}",
            body=[
                "It looks like there may be new reverts across ${name} (",
                "pretty_${sha}",
                ").",
                tiny_render.line_break,
                tiny_render.line_break,
                "These are:",
                tiny_render.UnorderedList(
                    [
                        [
                            "pretty_${revert_sha0}",
                            " (appears to revert ",
                            "pretty_${reverted_sha0}",
                            "): ",
                            "subject_${revert_sha0}",
                        ],
                        [
                            "pretty_${revert_sha1}",
                            " (appears to revert ",
                            "pretty_${reverted_sha1}",
                            "): ",
                            "subject_${revert_sha1}",
                        ],
                        [
                            "pretty_${revert_sha2}",
                            " (appears to revert ",
                            "pretty_${reverted_sha2}",
                            "): ",
                            "subject_${revert_sha2}",
                        ],
                    ]
                ),
                tiny_render.line_break,
                "PTAL and consider reverting them locally.",
            ],
        )

        self.assertEqual(email, expected_email)

    def test_llvm_ebuild_parsing_appears_to_function(self):
        llvm_ebuild = io.StringIO(
            "\n".join(
                (
                    "foo",
                    '#LLVM_HASH="123"',
                    'LLVM_HASH="123" # comment',
                    'LLVM_NEXT_HASH="456"',
                )
            )
        )

        shas = nightly_revert_checker._parse_llvm_ebuild_for_shas(llvm_ebuild)
        self.assertEqual(
            shas,
            [
                ("llvm", "123"),
                ("llvm-next", "456"),
            ],
        )

    def test_llvm_ebuild_parsing_fails_if_both_hashes_arent_present(self):
        bad_bodies = [
            "",
            'LLVM_HASH="123" # comment',
            'LLVM_NEXT_HASH="123" # comment',
            'LLVM_NEXT_HASH="123" # comment\n#LLVM_HASH="123"',
        ]

        for bad in bad_bodies:
            with self.assertRaises(ValueError) as e:
                nightly_revert_checker._parse_llvm_ebuild_for_shas(
                    io.StringIO(bad)
                )

            self.assertIn("Failed to detect SHAs", str(e.exception))

    @patch("revert_checker.find_reverts")
    @patch("get_upstream_patch.get_from_upstream")
    def test_do_cherrypick_is_called(self, do_cherrypick, find_reverts):
        find_reverts.return_value = [
            revert_checker.Revert("12345abcdef", "fedcba54321")
        ]
        nightly_revert_checker.do_cherrypick(
            chroot_path="/path/to/chroot",
            llvm_dir="/path/to/llvm",
            interesting_shas=[("12345abcdef", "fedcba54321")],
            state={},
            reviewers=["meow@chromium.org"],
            cc=["purr@chromium.org"],
        )

        do_cherrypick.assert_called_once()
        find_reverts.assert_called_once()

    @patch("revert_checker.find_reverts")
    @patch("get_upstream_patch.get_from_upstream")
    def test_do_cherrypick_handles_cherrypick_error(
        self, do_cherrypick, find_reverts
    ):
        find_reverts.return_value = [
            revert_checker.Revert("12345abcdef", "fedcba54321")
        ]
        do_cherrypick.side_effect = get_upstream_patch.CherrypickError(
            "Patch at 12345abcdef already exists in PATCHES.json"
        )
        nightly_revert_checker.do_cherrypick(
            chroot_path="/path/to/chroot",
            llvm_dir="/path/to/llvm",
            interesting_shas=[("12345abcdef", "fedcba54321")],
            state={},
            reviewers=["meow@chromium.org"],
            cc=["purr@chromium.org"],
        )

        do_cherrypick.assert_called_once()
        find_reverts.assert_called_once()


if __name__ == "__main__":
    unittest.main()
