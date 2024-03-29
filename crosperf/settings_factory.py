# -*- coding: utf-8 -*-
# Copyright 2013 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Setting files for global, benchmark and labels."""


from field import BooleanField
from field import EnumField
from field import FloatField
from field import IntegerField
from field import ListField
from field import TextField
from settings import Settings


class BenchmarkSettings(Settings):
    """Settings used to configure individual benchmarks."""

    def __init__(self, name):
        super(BenchmarkSettings, self).__init__(name, "benchmark")
        self.AddField(
            TextField(
                "test_name",
                description="The name of the test to run. "
                "Defaults to the name of the benchmark.",
            )
        )
        self.AddField(
            TextField(
                "test_args",
                description="Arguments to be passed to the " "test.",
            )
        )
        self.AddField(
            IntegerField(
                "iterations",
                required=False,
                default=0,
                description="Number of iterations to run the test. "
                "If not set, will run each benchmark test the optimum number of "
                "times to get a stable result.",
            )
        )
        self.AddField(
            TextField(
                "suite",
                default="test_that",
                description="The type of the benchmark.",
            )
        )
        self.AddField(
            IntegerField(
                "retries",
                default=0,
                description="Number of times to retry a " "benchmark run.",
            )
        )
        self.AddField(
            BooleanField(
                "run_local",
                description="Run benchmark harness on the DUT. "
                "Currently only compatible with the suite: "
                "telemetry_Crosperf.",
                required=False,
                default=True,
            )
        )
        self.AddField(
            FloatField(
                "weight",
                default=0.0,
                description="Weight of the benchmark for CWP approximation",
            )
        )


class LabelSettings(Settings):
    """Settings for each label."""

    def __init__(self, name):
        super(LabelSettings, self).__init__(name, "label")
        self.AddField(
            TextField(
                "chromeos_image",
                required=False,
                description="The path to the image to run tests "
                "on, for local/custom-built images. See the "
                "'build' option for official or trybot images.",
            )
        )
        self.AddField(
            TextField(
                "autotest_path",
                required=False,
                description="Autotest directory path relative to chroot which "
                "has autotest files for the image to run tests requiring autotest "
                "files.",
            )
        )
        self.AddField(
            TextField(
                "debug_path",
                required=False,
                description="Debug info directory relative to chroot which has "
                "symbols and vmlinux that can be used by perf tool.",
            )
        )
        self.AddField(
            TextField(
                "chromeos_root",
                description="The path to a chromeos checkout which "
                "contains a src/scripts directory. Defaults to "
                "the chromeos checkout which contains the "
                "chromeos_image.",
            )
        )
        self.AddField(
            ListField(
                "remote",
                description="A comma-separated list of IPs of chromeos"
                "devices to run experiments on.",
            )
        )
        self.AddField(
            TextField(
                "image_args",
                required=False,
                default="",
                description="Extra arguments to pass to " "image_chromeos.py.",
            )
        )
        self.AddField(
            TextField(
                "cache_dir",
                default="",
                description="The cache dir for this image.",
            )
        )
        self.AddField(
            TextField(
                "compiler",
                default="gcc",
                description="The compiler used to build the "
                "ChromeOS image (gcc or llvm).",
            )
        )
        self.AddField(
            TextField(
                "chrome_src",
                description="The path to the source of chrome. "
                "This is used to run telemetry benchmarks. "
                "The default one is the src inside chroot.",
                required=False,
                default="",
            )
        )
        self.AddField(
            TextField(
                "build",
                description="The xbuddy specification for an "
                "official or trybot image to use for tests. "
                "'/remote' is assumed, and the board is given "
                "elsewhere, so omit the '/remote/<board>/' xbuddy "
                "prefix.",
                required=False,
                default="",
            )
        )


class GlobalSettings(Settings):
    """Settings that apply per-experiment."""

    def __init__(self, name):
        super(GlobalSettings, self).__init__(name, "global")
        self.AddField(
            TextField(
                "name",
                description="The name of the experiment. Just an "
                "identifier.",
            )
        )
        self.AddField(
            TextField(
                "board",
                description="The target board for running "
                "experiments on, e.g. x86-alex.",
            )
        )
        self.AddField(
            BooleanField(
                "crosfleet",
                description="Whether to run experiments via crosfleet.",
                default=False,
            )
        )
        self.AddField(
            ListField(
                "remote",
                description="A comma-separated list of IPs of "
                "chromeos devices to run experiments on.",
            )
        )
        self.AddField(
            BooleanField(
                "rerun_if_failed",
                description="Whether to re-run failed test runs " "or not.",
                default=False,
            )
        )
        self.AddField(
            BooleanField(
                "rm_chroot_tmp",
                default=False,
                description="Whether to remove the test_that "
                "result in the chroot.",
            )
        )
        self.AddField(
            ListField(
                "email",
                description="Space-separated list of email "
                "addresses to send email to.",
            )
        )
        self.AddField(
            BooleanField(
                "rerun",
                description="Whether to ignore the cache and "
                "for tests to be re-run.",
                default=False,
            )
        )
        self.AddField(
            BooleanField(
                "same_specs",
                default=True,
                description="Ensure cached runs are run on the "
                "same kind of devices which are specified as a "
                "remote.",
            )
        )
        self.AddField(
            BooleanField(
                "same_machine",
                default=False,
                description="Ensure cached runs are run on the " "same remote.",
            )
        )
        self.AddField(
            BooleanField(
                "use_file_locks",
                default=False,
                description="DEPRECATED: Whether to use the file locks "
                "or AFE server lock mechanism.",
            )
        )
        self.AddField(
            IntegerField(
                "iterations",
                required=False,
                default=0,
                description="Number of iterations to run all tests. "
                "If not set, will run each benchmark test the optimum number of "
                "times to get a stable result.",
            )
        )
        self.AddField(
            TextField(
                "chromeos_root",
                description="The path to a chromeos checkout which "
                "contains a src/scripts directory. Defaults to "
                "the chromeos checkout which contains the "
                "chromeos_image.",
            )
        )
        self.AddField(
            TextField(
                "logging_level",
                default="average",
                description="The level of logging desired. "
                "Options are 'quiet', 'average', and 'verbose'.",
            )
        )
        self.AddField(
            IntegerField(
                "acquire_timeout",
                default=0,
                description="Number of seconds to wait for "
                "machine before exit if all the machines in "
                "the experiment file are busy. Default is 0.",
            )
        )
        self.AddField(
            TextField(
                "perf_args",
                default="",
                description="The optional profile command. It "
                "enables perf commands to record perforamance "
                "related counters. It must start with perf "
                "command record or stat followed by arguments.",
            )
        )
        self.AddField(
            BooleanField(
                "download_debug",
                default=True,
                description="Download compressed debug symbols alongwith "
                "image. This can provide more info matching symbols for"
                "profiles, but takes larger space. By default, download"
                "it only when perf_args is specified.",
            )
        )
        self.AddField(
            TextField(
                "cache_dir",
                default="",
                description="The abs path of cache dir. "
                "Default is /home/$(whoami)/cros_scratch.",
            )
        )
        self.AddField(
            BooleanField(
                "cache_only",
                default=False,
                description="Whether to use only cached "
                "results (do not rerun failed tests).",
            )
        )
        self.AddField(
            BooleanField(
                "no_email",
                default=False,
                description="Whether to disable the email to "
                "user after crosperf finishes.",
            )
        )
        self.AddField(
            BooleanField(
                "json_report",
                default=False,
                description="Whether to generate a json version "
                "of the report, for archiving.",
            )
        )
        self.AddField(
            BooleanField(
                "show_all_results",
                default=False,
                description="When running Telemetry tests, "
                "whether to all the results, instead of just "
                "the default (summary) results.",
            )
        )
        self.AddField(
            TextField(
                "share_cache",
                default="",
                description="Path to alternate cache whose data "
                "you want to use. It accepts multiple directories "
                'separated by a ",".',
            )
        )
        self.AddField(
            TextField("results_dir", default="", description="The results dir.")
        )
        self.AddField(
            BooleanField(
                "compress_results",
                default=True,
                description="Whether to compress all test results other than "
                "reports into a tarball to save disk space.",
            )
        )
        self.AddField(
            TextField(
                "locks_dir",
                default="",
                description="An alternate directory to use for "
                "storing/checking machine file locks for local machines. "
                "By default the file locks directory is "
                "/google/data/rw/users/mo/mobiletc-prebuild/locks.\n"
                "WARNING: If you use your own locks directory, "
                "there is no guarantee that someone else might not "
                "hold a lock on the same machine in a different "
                "locks directory.",
            )
        )
        self.AddField(
            TextField(
                "chrome_src",
                description="The path to the source of chrome. "
                "This is used to run telemetry benchmarks. "
                "The default one is the src inside chroot.",
                required=False,
                default="",
            )
        )
        self.AddField(
            IntegerField(
                "retries",
                default=0,
                description="Number of times to retry a " "benchmark run.",
            )
        )
        self.AddField(
            TextField(
                "cwp_dso",
                description="The DSO type that we want to use for "
                "CWP approximation. This is used to run telemetry "
                "benchmarks. Valid DSO types can be found from dso_list "
                "in experiment_factory.py. The default value is set to "
                "be empty.",
                required=False,
                default="",
            )
        )
        self.AddField(
            BooleanField(
                "enable_aslr",
                description="Enable ASLR on the machine to run the "
                "benchmarks. ASLR is disabled by default",
                required=False,
                default=False,
            )
        )
        self.AddField(
            BooleanField(
                "ignore_min_max",
                description="When doing math for the raw results, "
                "ignore min and max values to reduce noise.",
                required=False,
                default=False,
            )
        )
        self.AddField(
            TextField(
                "intel_pstate",
                description="Intel Pstate mode.\n"
                'Supported modes: "active", "passive", "no_hwp".\n'
                'Default is "no_hwp" which disables hardware pstates to avoid '
                "noise in benchmarks.",
                required=False,
                default="no_hwp",
            )
        )
        self.AddField(
            BooleanField(
                "turbostat",
                description="Run turbostat process in the background"
                " of a benchmark. Enabled by default.",
                required=False,
                default=True,
            )
        )
        self.AddField(
            FloatField(
                "top_interval",
                description="Run top command in the background of a benchmark with"
                " interval of sampling specified in seconds.\n"
                "Recommended values 1-5. Lower number provides more accurate"
                " data.\n"
                "With 0 - do not run top.\n"
                "NOTE: Running top with interval 1-5 sec has insignificant"
                " performance impact (performance degradation does not exceed"
                " 0.3%%, measured on x86_64, ARM32, and ARM64). "
                "The default value is 1.",
                required=False,
                default=1,
            )
        )
        self.AddField(
            IntegerField(
                "cooldown_temp",
                required=False,
                default=40,
                description="Wait until CPU temperature goes down below"
                " specified temperature in Celsius"
                " prior starting a benchmark. "
                "By default the value is set to 40 degrees.",
            )
        )
        self.AddField(
            IntegerField(
                "cooldown_time",
                required=False,
                default=10,
                description="Wait specified time in minutes allowing"
                " CPU to cool down. Zero value disables cooldown. "
                "The default value is 10 minutes.",
            )
        )
        self.AddField(
            EnumField(
                "governor",
                options=[
                    "performance",
                    "powersave",
                    "userspace",
                    "ondemand",
                    "conservative",
                    "schedutils",
                    "sched",
                    "interactive",
                ],
                default="performance",
                required=False,
                description="Setup CPU governor for all cores.\n"
                "For more details refer to:\n"
                "https://www.kernel.org/doc/Documentation/cpu-freq/governors.txt. "
                'Default is "performance" governor.',
            )
        )
        self.AddField(
            EnumField(
                "cpu_usage",
                options=[
                    "all",
                    "big_only",
                    "little_only",
                    "exclusive_cores",
                ],
                default="all",
                required=False,
                description="Restrict usage of CPUs to decrease CPU interference.\n"
                '"all" - no restrictions;\n'
                '"big-only", "little-only" - enable only big/little cores,'
                " applicable only on ARM;\n"
                '"exclusive-cores" - (for future use)'
                " isolate cores for exclusive use of benchmark processes. "
                "By default use all CPUs.",
            )
        )
        self.AddField(
            IntegerField(
                "cpu_freq_pct",
                required=False,
                default=95,
                description="Setup CPU frequency to a supported value less than"
                " or equal to a percent of max_freq. "
                "CPU frequency is reduced to 95%% by default to reduce thermal "
                "throttling.",
            )
        )
        self.AddField(
            BooleanField(
                "no_lock",
                default=False,
                description="Do not attempt to lock the DUT."
                " Useful when lock is held externally, say with crosfleet.",
            )
        )


class SettingsFactory(object):
    """Factory class for building different types of Settings objects.

    This factory is currently hardcoded to produce settings for ChromeOS
    experiment files. The idea is that in the future, other types
    of settings could be produced.
    """

    def GetSettings(self, name, settings_type):
        if settings_type == "label" or not settings_type:
            return LabelSettings(name)
        if settings_type == "global":
            return GlobalSettings(name)
        if settings_type == "benchmark":
            return BenchmarkSettings(name)

        raise TypeError("Invalid settings type: '%s'." % settings_type)
