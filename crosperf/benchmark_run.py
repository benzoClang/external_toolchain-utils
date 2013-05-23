#!/usr/bin/python

# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import datetime
import os
import threading
import time
import traceback

from utils import command_executer
from utils import timeline

from autotest_runner import AutotestRunner
from results_cache import Result
from results_cache import ResultsCache

STATUS_FAILED = "FAILED"
STATUS_SUCCEEDED = "SUCCEEDED"
STATUS_IMAGING = "IMAGING"
STATUS_RUNNING = "RUNNING"
STATUS_WAITING = "WAITING"
STATUS_PENDING = "PENDING"


class BenchmarkRun(threading.Thread):
  def __init__(self, name, benchmark,
               label,
               iteration,
               cache_conditions,
               machine_manager,
               logger_to_use,
               share_users):
    threading.Thread.__init__(self)
    self.name = name
    self._logger = logger_to_use
    self.benchmark = benchmark
    self.iteration = iteration
    self.label = label
    self.result = None
    self.terminated = False
    self.retval = None
    self.run_completed = False
    self.machine_manager = machine_manager
    self.cache = ResultsCache()
    self.autotest_runner = AutotestRunner(self._logger)
    self.machine = None
    self.cache_conditions = cache_conditions
    self.runs_complete = 0
    self.cache_hit = False
    self.failure_reason = ""
    self.autotest_args = "%s %s" % (benchmark.autotest_args,
                                    self._GetExtraAutotestArgs())
    self._ce = command_executer.GetCommandExecuter(self._logger)
    self.timeline = timeline.Timeline()
    self.timeline.Record(STATUS_PENDING)
    self.share_users = share_users

  def run(self):
    try:
      # Just use the first machine for running the cached version,
      # without locking it.
      self.cache.Init(self.label.chromeos_image,
                      self.label.chromeos_root,
                      self.benchmark.autotest_name,
                      self.iteration,
                      self.autotest_args,
                      self.machine_manager,
                      self.label.board,
                      self.cache_conditions,
                      self._logger,
                      self.label,
                      self.share_users
                     )

      self.result = self.cache.ReadResult()
      self.cache_hit = (self.result is not None)

      if self.result:
        self._logger.LogOutput("%s: Cache hit." % self.name)
        self._logger.LogOutput(self.result.out, print_to_console=False)
        self._logger.LogError(self.result.err, print_to_console=False)

      else:
        self._logger.LogOutput("%s: No cache hit." % self.name)
        self.timeline.Record(STATUS_WAITING)
        # Try to acquire a machine now.
        self.machine = self.AcquireMachine()
        self.cache.remote = self.machine.name
        self.result = self.RunTest(self.machine)
        self.cache.StoreResult(self.result)

      if self.terminated:
        return

      if not self.result.retval:
        self.timeline.Record(STATUS_SUCCEEDED)
      else:
        if self.timeline.GetLastEvent() != STATUS_FAILED:
          self.failure_reason = "Return value of autotest was non-zero."
          self.timeline.Record(STATUS_FAILED)

    except Exception, e:
      self._logger.LogError("Benchmark run: '%s' failed: %s" % (self.name, e))
      traceback.print_exc()
      if self.timeline.GetLastEvent() != STATUS_FAILED:
        self.timeline.Record(STATUS_FAILED)
        self.failure_reason = str(e)
    finally:
      if self.machine:
        if not self.machine.IsReachable():
          self._logger.LogOutput("Machine % is not reachable, removing it."
                                 % self.machine.name)
          self.machine_manager.RemoveMachine(self.machine.name)
        self._logger.LogOutput("Releasing machine: %s" % self.machine.name)
        self.machine_manager.ReleaseMachine(self.machine)
        self._logger.LogOutput("Released machine: %s" % self.machine.name)

  def Terminate(self):
    self.terminated = True
    self.autotest_runner.Terminate()
    if self.timeline.GetLastEvent() != STATUS_FAILED:
      self.timeline.Record(STATUS_FAILED)
      self.failure_reason = "Thread terminated."

  def AcquireMachine(self):
    while True:
      if self.terminated:
        raise Exception("Thread terminated while trying to acquire machine.")
      machine = self.machine_manager.AcquireMachine(self.label.chromeos_image,
                                                    self.label)

      if machine:
        self._logger.LogOutput("%s: Machine %s acquired at %s" %
                               (self.name,
                                machine.name,
                                datetime.datetime.now()))
        break
      else:
        sleep_duration = 10
        time.sleep(sleep_duration)
    return machine

  def _GetExtraAutotestArgs(self):
    if self.benchmark.perf_args:
      perf_args_list = self.benchmark.perf_args.split(" ")
      perf_args_list = [perf_args_list[0]] + ["-a"] + perf_args_list[1:]
      perf_args = " ".join(perf_args_list)
      if not perf_args_list[0] in ["record", "stat"]:
        raise Exception("perf_args must start with either record or stat")
      extra_autotest_args = ["--profiler=custom_perf",
                             ("--profiler_args='perf_options=\"%s\"'" %
                              perf_args)]
      return " ".join(extra_autotest_args)
    else:
      return ""

  def RunTest(self, machine):
    self.timeline.Record(STATUS_IMAGING)
    self.machine_manager.ImageMachine(machine,
                                      self.label)
    self.timeline.Record(STATUS_RUNNING)
    [retval, out, err] = self.autotest_runner.Run(machine.name,
                                                  self.label.chromeos_root,
                                                  self.label.board,
                                                  self.benchmark.autotest_name,
                                                  self.autotest_args)
    self.run_completed = True

    return Result.CreateFromRun(self._logger,
                                self.label.chromeos_root,
                                self.label.board,
                                self.label.name,
                                out,
                                err,
                                retval)

  def SetCacheConditions(self, cache_conditions):
    self.cache_conditions = cache_conditions


class MockBenchmarkRun(BenchmarkRun):
  """Inherited from BenchmarkRun, just overide RunTest for testing."""

  def RunTest(self, machine):
    """Remove Result.CreateFromRun for testing."""
    self.timeline.Record(STATUS_IMAGING)
    self.machine_manager.ImageMachine(machine,
                                      self.label)
    self.timeline.Record(STATUS_RUNNING)
    [retval, out, err] = self.autotest_runner.Run(machine.name,
                                                  self.label.chromeos_root,
                                                  self.label.board,
                                                  self.benchmark.autotest_name,
                                                  self.autotest_args)
    self.run_completed = True
    rr = Result("Results placed in /tmp/test", "", 0)
    rr.out = out
    rr.err = err
    rr.retval = retval
    return rr

