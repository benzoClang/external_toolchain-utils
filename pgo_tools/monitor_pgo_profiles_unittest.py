#!/usr/bin/env python3
# Copyright 2020 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for monitor_pgo_profiles."""

import datetime
import subprocess
import unittest
import unittest.mock

import monitor_pgo_profiles


class Test(unittest.TestCase):
    """Tests for monitor_pgo_profiles."""

    def test_compose_complaint_with_zero_out_of_date(self):
        self.assertIsNone(monitor_pgo_profiles.compose_complaint([]))

    def test_compose_complaint_with_one_out_of_date(self):
        profdata_info = monitor_pgo_profiles.ProfdataInfo(
            date=datetime.datetime(2020, 1, 2, 3, 4, 5),
            location="gs://somewhere",
        )
        result = monitor_pgo_profiles.compose_complaint(
            [
                ("some_arch", profdata_info),
            ]
        )
        self.assertEqual(
            result,
            "\n".join(
                (
                    "1 profile is out of date:",
                    f"- some_arch (most recent profile was from {profdata_info.date} "
                    f"at {profdata_info.location!r})",
                    "",
                    "",
                    "PTAL to see if the llvm-pgo-generate bots are functioning "
                    "normally. Their status can be found at "
                    f"{monitor_pgo_profiles.PGO_BUILDBOT_LINK}.",
                )
            ),
        )

    def test_compose_complaint_with_two_out_of_date(self):
        profdata_info_1 = monitor_pgo_profiles.ProfdataInfo(
            date=datetime.datetime(2020, 1, 2, 3, 4, 5),
            location="gs://somewhere",
        )
        profdata_info_2 = monitor_pgo_profiles.ProfdataInfo(
            date=datetime.datetime(2020, 3, 2, 1, 4, 5),
            location="gs://somewhere-else",
        )
        result = monitor_pgo_profiles.compose_complaint(
            [
                ("some_arch", profdata_info_1),
                ("some_other_arch", profdata_info_2),
            ]
        )
        self.assertEqual(
            result,
            "\n".join(
                (
                    "2 profiles are out of date:",
                    f"- some_arch (most recent profile was from {profdata_info_1.date} "
                    f"at {profdata_info_1.location!r})",
                    f"- some_other_arch (most recent profile was from "
                    f"{profdata_info_2.date} at {profdata_info_2.location!r})",
                    "",
                    "",
                    "PTAL to see if the llvm-pgo-generate bots are functioning "
                    "normally. Their status can be found at "
                    f"{monitor_pgo_profiles.PGO_BUILDBOT_LINK}.",
                )
            ),
        )

    @unittest.mock.patch.object(subprocess, "run")
    def test_fetching_profdata_functions(self, subprocess_run_mock):
        ls_return_value = unittest.mock.MagicMock()
        ls_return_value.stdout = "\n".join(
            (
                "  1234 2020-06-26T05:26:40Z gs://bar",
                "    44 2020-06-23T05:26:40Z gs://foo",
                "  1234 2020-06-25T05:26:40Z gs://zzz",
            )
        )
        subprocess_run_mock.return_value = ls_return_value

        most_recent = monitor_pgo_profiles.fetch_most_recent_profdata("arm")
        self.assertEqual(
            most_recent,
            monitor_pgo_profiles.ProfdataInfo(
                date=datetime.datetime(2020, 6, 26, 5, 26, 40),
                location="gs://bar",
            ),
        )


if __name__ == "__main__":
    unittest.main()
