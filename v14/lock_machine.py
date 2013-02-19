#!/usr/bin/python2.6
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Script to lock/unlock machines."""

__author__ = "asharif@google.com (Ahmad Sharif)"

import datetime
import fcntl
import getpass
import glob
import optparse
import os
import pickle
import socket
import sys
import time

from utils import logger


class FileCreationMask(object):
  def __init__(self, mask):
    self._mask = mask

  def __enter__(self):
    self._old_mask = os.umask(self._mask)

  def __exit__(self, type, value, traceback):
    os.umask(self._old_mask)


class LockDescription(object):
  def __init__(self):
    self.owner = ""
    self.exclusive = False
    self.counter = 0
    self.time = 0
    self.reason = ""

  def IsLocked(self):
    return self.counter or self.exclusive

  def __str__(self):
    return " ".join(["Owner: %s" % self.owner,
                     "Exclusive: %s" % self.exclusive,
                     "Counter: %s" % self.counter,
                     "Time: %s" % self.time,
                     "Reason: %s" % self.reason])


class FileLock(object):

  def __init__(self, lock_filename):
    self._filepath = lock_filename
    lock_dir = os.path.dirname(lock_filename)
    assert os.path.isdir(lock_dir), (
        "Locks dir: %s doesn't exist!" % lock_dir)
    self._file = None

  @classmethod
  def AsString(cls, file_locks):
    stringify_fmt = "%-30s %-15s %-4s %-4s %-15s %-40s"
    header = stringify_fmt % ("machine", "owner", "excl", "ctr",
                              "elapsed", "reason")
    lock_strings = []
    for file_lock in file_locks:

      elapsed_time = datetime.timedelta(
          seconds=int(time.time() - file_lock._description.time))
      elapsed_time = "%s ago" % elapsed_time
      lock_strings.append(stringify_fmt %
                          (os.path.basename(file_lock._filepath),
                           file_lock._description.owner,
                           file_lock._description.exclusive,
                           file_lock._description.counter,
                           elapsed_time,
                           file_lock._description.reason))
    table = "\n".join(lock_strings)
    return "\n".join([header, table])

  @classmethod
  def ListLock(cls, pattern, locks_dir):
    if not locks_dir:
      locks_dir = Machine.LOCKS_DIR
    full_pattern = os.path.join(locks_dir, pattern)
    file_locks = []
    for lock_filename in glob.glob(full_pattern):
      file_lock = FileLock(lock_filename)
      with file_lock as lock:
        if lock.IsLocked():
          file_locks.append(file_lock)
    logger.GetLogger().LogOutput("\n%s" % cls.AsString(file_locks))

  def __enter__(self):
    with FileCreationMask(0000):
      try:
        self._file = open(self._filepath, "a+")
        self._file.seek(0, os.SEEK_SET)

        if fcntl.flock(self._file.fileno(), fcntl.LOCK_EX) == -1:
          raise IOError("flock(%s, LOCK_EX) failed!" % self._filepath)

        try:
          self._description = pickle.load(self._file)
        except (EOFError, pickle.PickleError):
          self._description = LockDescription()
        return self._description
      # Check this differently?
      except IOError as ex:
        logger.GetLogger().LogError(ex)
        return None

  def __exit__(self, type, value, traceback):
    self._file.truncate(0)
    self._file.write(pickle.dumps(self._description))
    self._file.close()

  def __str__(self):
    return self.AsString([self])


class Lock(object):
  def __init__(self, lock_file):
    self._to_lock = os.path.basename(lock_file)
    self._lock_file = lock_file
    self._logger = logger.GetLogger()

  def NonBlockingLock(self, exclusive, reason=""):
    with FileLock(self._lock_file) as lock:
      if lock.exclusive:
        self._logger.LogError(
            "Exclusive lock already acquired by %s. Reason: %s" %
            (lock.owner, lock.reason))
        return False

      if exclusive:
        if lock.counter:
          self._logger.LogError("Shared lock already acquired")
          return False
        lock.exclusive = True
        lock.reason = reason
        lock.owner = getpass.getuser()
        lock.time = time.time()
      else:
        lock.counter += 1
    self._logger.LogOutput("Successfully locked: %s" % self._to_lock)
    return True

  def Unlock(self, exclusive, force=False):
    with FileLock(self._lock_file) as lock:
      if not lock.IsLocked():
        self._logger.LogError("Can't unlock unlocked machine!")
        return False

      if lock.exclusive != exclusive:
        self._logger.LogError("shared locks must be unlocked with --shared")
        return False

      if lock.exclusive:
        if lock.owner != getpass.getuser() and not force:
          self._logger.LogError("%s can't unlock lock owned by: %s" %
                                (getpass.getuser(), lock.owner))
          return False
        lock.exclusive = False
        lock.reason = ""
        lock.owner = ""
      else:
        lock.counter -= 1
    return True


class Machine(object):
  LOCKS_DIR = "/home/mobiletc-prebuild/locks"
  def __init__(self, name, locks_dir=LOCKS_DIR):
    self._name = name
    try:
      self._full_name = socket.gethostbyaddr(name)[0]
    except socket.error:
      self._full_name = self._name
    self._full_name = os.path.join(locks_dir, self._full_name)

  def Lock(self, exclusive=False, reason=""):
    lock = Lock(self._full_name)
    return lock.NonBlockingLock(exclusive, reason)

  def TryLock(self, timeout=300, exclusive=False, reason=""):
    locked = False
    sleep = timeout / 10;
    while True:
      locked = self.Lock(exclusive, reason)
      if locked or not timeout >= 0:
        break
      print "Lock not acquired for {0}, wait {1} seconds ...".format(
        self._name, sleep)
      time.sleep(sleep)
      timeout -= sleep
    return locked

  def Unlock(self, exclusive=False, ignore_ownership=False):
    lock = Lock(self._full_name)
    return lock.Unlock(exclusive, ignore_ownership)


def Main(argv):
  """The main function."""
  parser = optparse.OptionParser()
  parser.add_option("-r",
                    "--reason",
                    dest="reason",
                    default="",
                    help="The lock reason.")
  parser.add_option("-u",
                    "--unlock",
                    dest="unlock",
                    action="store_true",
                    default=False,
                    help="Use this to unlock.")
  parser.add_option("-l",
                    "--list_locks",
                    dest="list_locks",
                    action="store_true",
                    default=False,
                    help="Use this to list locks.")
  parser.add_option("-f",
                    "--ignore_ownership",
                    dest="ignore_ownership",
                    action="store_true",
                    default=False,
                    help="Use this to force unlock on a lock you don't own.")
  parser.add_option("-s",
                    "--shared",
                    dest="shared",
                    action="store_true",
                    default=False,
                    help="Use this for a shared (non-exclusive) lock.")
  parser.add_option("-d",
                    "--dir",
                    dest="locks_dir",
                    action="store",
                    default=Machine.LOCKS_DIR,
                    help="Use this to set different locks_dir")

  options, args = parser.parse_args(argv)

  options.locks_dir = os.path.abspath(options.locks_dir)
  exclusive = not options.shared

  if not options.list_locks and len(args) != 2:
    logger.GetLogger().LogError(
        "Either --list_locks or a machine arg is needed.")
    return 1

  if len(args) > 1:
    machine = Machine(args[1], options.locks_dir)
  else:
    machine = None

  if options.list_locks:
    FileLock.ListLock("*", options.locks_dir)
    retval = True
  elif options.unlock:
    retval = machine.Unlock(exclusive, options.ignore_ownership)
  else:
    retval = machine.Lock(exclusive, options.reason)

  if retval:
    return 0
  else:
    return 1

if __name__ == "__main__":
  sys.exit(Main(sys.argv))
