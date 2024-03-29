#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2014 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests for the Crosperf Benchmark class."""


import inspect
import unittest

from benchmark import Benchmark


class BenchmarkTestCase(unittest.TestCase):
    """Individual tests for the Benchmark class."""

    def test_benchmark(self):
        # Test creating a benchmark with all the fields filled out.
        b1 = Benchmark(
            "b1_test",  # name
            "octane",  # test_name
            "",  # test_args
            3,  # iterations
            False,  # rm_chroot_tmp
            "record -e cycles",  # perf_args
            "telemetry_Crosperf",  # suite
            True,
        )  # show_all_results
        self.assertTrue(b1.suite, "telemetry_Crosperf")

        # Test creating a benchmark field with default fields left out.
        b2 = Benchmark(
            "b2_test",  # name
            "octane",  # test_name
            "",  # test_args
            3,  # iterations
            False,  # rm_chroot_tmp
            "record -e cycles",
        )  # perf_args
        self.assertEqual(b2.suite, "")
        self.assertFalse(b2.show_all_results)

        # Test explicitly creating 'suite=Telemetry' and 'show_all_results=False"
        # and see what happens.
        b3 = Benchmark(
            "b3_test",  # name
            "octane",  # test_name
            "",  # test_args
            3,  # iterations
            False,  # rm_chroot_tmp
            "record -e cycles",  # perf_args
            "telemetry",  # suite
            False,
        )  # show_all_results
        self.assertTrue(b3.show_all_results)

        # Check to see if the args to Benchmark have changed since the last time
        # this test was updated.
        args_list = [
            "self",
            "name",
            "test_name",
            "test_args",
            "iterations",
            "rm_chroot_tmp",
            "perf_args",
            "suite",
            "show_all_results",
            "retries",
            "run_local",
            "cwp_dso",
            "weight",
        ]
        arg_spec = inspect.getfullargspec(Benchmark.__init__)
        self.assertEqual(len(arg_spec.args), len(args_list))
        for arg in args_list:
            self.assertIn(arg, arg_spec.args)


if __name__ == "__main__":
    unittest.main()
