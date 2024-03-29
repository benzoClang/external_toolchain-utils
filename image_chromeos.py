#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2019 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Script to image a ChromeOS device.

This script images a remote ChromeOS device with a specific image."
"""


__author__ = "asharif@google.com (Ahmad Sharif)"

import argparse
import filecmp
import getpass
import glob
import os
import re
import shutil
import sys
import tempfile
import time

from cros_utils import command_executer
from cros_utils import locks
from cros_utils import logger
from cros_utils import misc
from cros_utils.file_utils import FileUtils


checksum_file = "/usr/local/osimage_checksum_file"
lock_file = "/tmp/image_chromeos_lock/image_chromeos_lock"


def Usage(parser, message):
    print("ERROR: %s" % message)
    parser.print_help()
    sys.exit(0)


def CheckForCrosFlash(chromeos_root, remote, log_level):
    cmd_executer = command_executer.GetCommandExecuter(log_level=log_level)

    # Check to see if remote machine has cherrypy, ctypes
    command = "python -c 'import cherrypy, ctypes'"
    ret = cmd_executer.CrosRunCommand(
        command, chromeos_root=chromeos_root, machine=remote
    )
    logger.GetLogger().LogFatalIf(
        ret == 255, "Failed ssh to %s (for checking cherrypy)" % remote
    )
    logger.GetLogger().LogFatalIf(
        ret != 0,
        "Failed to find cherrypy or ctypes on remote '{}', "
        "cros flash cannot work.".format(remote),
    )


def DisableCrosBeeps(chromeos_root, remote, log_level):
    """Disable annoying chromebooks beeps after reboots."""
    cmd_executer = command_executer.GetCommandExecuter(log_level=log_level)

    command = "/usr/share/vboot/bin/set_gbb_flags.sh 0x1"
    logger.GetLogger().LogOutput("Trying to disable beeping.")

    ret, o, _ = cmd_executer.CrosRunCommandWOutput(
        command, chromeos_root=chromeos_root, machine=remote
    )
    if ret != 0:
        logger.GetLogger().LogOutput(o)
        logger.GetLogger().LogOutput("Failed to disable beeps.")


def FindChromeOSImage(image_file, chromeos_root):
    """Find path for ChromeOS image inside chroot.

    This function could be called with image paths that are either inside
    or outside the chroot.  In either case the path needs to be translated
    to an real/absolute path inside the chroot.
    Example input paths:
    /usr/local/google/home/uname/chromeos/chroot/tmp/my-test-images/image
    ~/trunk/src/build/images/board/latest/image
    /tmp/peppy-release/R67-1235.0.0/image

    Corresponding example output paths:
    /tmp/my-test-images/image
    /home/uname/trunk/src/build/images/board/latest/image
    /tmp/peppy-release/R67-1235.0,0/image
    """

    # Get the name of the user, for "/home/<user>" part of the path.
    whoami = getpass.getuser()
    # Get the full path for the chroot dir, including 'chroot'
    real_chroot_dir = os.path.join(os.path.realpath(chromeos_root), "chroot")
    # Get the full path for the chromeos root, excluding 'chroot'
    real_chromeos_root = os.path.realpath(chromeos_root)

    # If path name starts with real_chroot_dir, remove that piece, but assume
    # the rest of the path is correct.
    if image_file.find(real_chroot_dir) != -1:
        chroot_image = image_file[len(real_chroot_dir) :]
    # If path name starts with chromeos_root, excluding 'chroot', replace the
    # chromeos_root with the prefix: '/home/<username>/trunk'.
    elif image_file.find(real_chromeos_root) != -1:
        chroot_image = image_file[len(real_chromeos_root) :]
        chroot_image = "/home/%s/trunk%s" % (whoami, chroot_image)
    # Else assume the path is already internal, so leave it alone.
    else:
        chroot_image = image_file

    return chroot_image


def DoImage(argv):
    """Image ChromeOS."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--chromeos_root",
        dest="chromeos_root",
        help="Target directory for ChromeOS installation.",
    )
    parser.add_argument("-r", "--remote", dest="remote", help="Target device.")
    parser.add_argument(
        "-i", "--image", dest="image", help="Image binary file."
    )
    parser.add_argument(
        "-b", "--board", dest="board", help="Target board override."
    )
    parser.add_argument(
        "-f",
        "--force",
        dest="force",
        action="store_true",
        default=False,
        help="Force an image even if it is non-test.",
    )
    parser.add_argument(
        "-n",
        "--no_lock",
        dest="no_lock",
        default=False,
        action="store_true",
        help="Do not attempt to lock remote before imaging.  "
        "This option should only be used in cases where the "
        "exclusive lock has already been acquired (e.g. in "
        "a script that calls this one).",
    )
    parser.add_argument(
        "-l",
        "--logging_level",
        dest="log_level",
        default="verbose",
        help="Amount of logging to be used. Valid levels are "
        "'quiet', 'average', and 'verbose'.",
    )
    parser.add_argument("-a", "--image_args", dest="image_args")

    options = parser.parse_args(argv[1:])

    if not options.log_level in command_executer.LOG_LEVEL:
        Usage(parser, "--logging_level must be 'quiet', 'average' or 'verbose'")
    else:
        log_level = options.log_level

    # Common initializations
    cmd_executer = command_executer.GetCommandExecuter(log_level=log_level)
    l = logger.GetLogger()

    if options.chromeos_root is None:
        Usage(parser, "--chromeos_root must be set")

    if options.remote is None:
        Usage(parser, "--remote must be set")

    options.chromeos_root = os.path.expanduser(options.chromeos_root)

    if options.board is None:
        board = cmd_executer.CrosLearnBoard(
            options.chromeos_root, options.remote
        )
    else:
        board = options.board

    if options.image is None:
        images_dir = misc.GetImageDir(options.chromeos_root, board)
        image = os.path.join(images_dir, "latest", "chromiumos_test_image.bin")
        if not os.path.exists(image):
            image = os.path.join(images_dir, "latest", "chromiumos_image.bin")
        is_xbuddy_image = False
    else:
        image = options.image
        is_xbuddy_image = image.startswith("xbuddy://")
        if not is_xbuddy_image:
            image = os.path.expanduser(image)

    if not is_xbuddy_image:
        image = os.path.realpath(image)

    if not os.path.exists(image) and not is_xbuddy_image:
        Usage(parser, "Image file: " + image + " does not exist!")

    try:
        should_unlock = False
        if not options.no_lock:
            try:
                _ = locks.AcquireLock(
                    list(options.remote.split()), options.chromeos_root
                )
                should_unlock = True
            except Exception as e:
                raise RuntimeError("Error acquiring machine: %s" % str(e))

        reimage = False
        local_image = False
        if not is_xbuddy_image:
            local_image = True
            image_checksum = FileUtils().Md5File(image, log_level=log_level)

            command = "cat " + checksum_file
            ret, device_checksum, _ = cmd_executer.CrosRunCommandWOutput(
                command,
                chromeos_root=options.chromeos_root,
                machine=options.remote,
            )

            device_checksum = device_checksum.strip()
            image_checksum = str(image_checksum)

            l.LogOutput("Image checksum: " + image_checksum)
            l.LogOutput("Device checksum: " + device_checksum)

            if image_checksum != device_checksum:
                [found, located_image] = LocateOrCopyImage(
                    options.chromeos_root, image, board=board
                )

                reimage = True
                l.LogOutput("Checksums do not match. Re-imaging...")

                chroot_image = FindChromeOSImage(
                    located_image, options.chromeos_root
                )

                is_test_image = IsImageModdedForTest(
                    options.chromeos_root, chroot_image, log_level
                )

                if not is_test_image and not options.force:
                    logger.GetLogger().LogFatal(
                        "Have to pass --force to image a " "non-test image!"
                    )
        else:
            reimage = True
            found = True
            l.LogOutput("Using non-local image; Re-imaging...")

        if reimage:
            # If the device has /tmp mounted as noexec, image_to_live.sh can fail.
            command = "mount -o remount,rw,exec /tmp"
            cmd_executer.CrosRunCommand(
                command,
                chromeos_root=options.chromeos_root,
                machine=options.remote,
            )

            # Check to see if cros flash will work for the remote machine.
            CheckForCrosFlash(options.chromeos_root, options.remote, log_level)

            # Disable the annoying chromebook beeps after reboot.
            DisableCrosBeeps(options.chromeos_root, options.remote, log_level)

            cros_flash_args = [
                "cros",
                "flash",
                "--board=%s" % board,
                "--clobber-stateful",
                options.remote,
            ]
            if local_image:
                cros_flash_args.append(chroot_image)
            else:
                cros_flash_args.append(image)

            command = " ".join(cros_flash_args)

            # Workaround for crosbug.com/35684.
            os.chmod(misc.GetChromeOSKeyFile(options.chromeos_root), 0o600)

            if log_level == "average":
                cmd_executer.SetLogLevel("verbose")
            retries = 0
            while True:
                if log_level == "quiet":
                    l.LogOutput("CMD : %s" % command)
                ret = cmd_executer.ChrootRunCommand(
                    options.chromeos_root, command, command_timeout=1800
                )
                if ret == 0 or retries >= 2:
                    break
                retries += 1
                if log_level == "quiet":
                    l.LogOutput("Imaging failed. Retry # %d." % retries)

            if log_level == "average":
                cmd_executer.SetLogLevel(log_level)

            logger.GetLogger().LogFatalIf(ret, "Image command failed")

            # Unfortunately cros_image_to_target.py sometimes returns early when the
            # machine isn't fully up yet.
            ret = EnsureMachineUp(
                options.chromeos_root, options.remote, log_level
            )

            # If this is a non-local image, then the ret returned from
            # EnsureMachineUp is the one that will be returned by this function;
            # in that case, make sure the value in 'ret' is appropriate.
            if not local_image and ret:
                ret = 0
            else:
                ret = 1

            if local_image:
                if log_level == "average":
                    l.LogOutput("Verifying image.")
                command = "echo %s > %s && chmod -w %s" % (
                    image_checksum,
                    checksum_file,
                    checksum_file,
                )
                ret = cmd_executer.CrosRunCommand(
                    command,
                    chromeos_root=options.chromeos_root,
                    machine=options.remote,
                )
                logger.GetLogger().LogFatalIf(ret, "Writing checksum failed.")

                successfully_imaged = VerifyChromeChecksum(
                    options.chromeos_root,
                    chroot_image,
                    options.remote,
                    log_level,
                )
                logger.GetLogger().LogFatalIf(
                    not successfully_imaged, "Image verification failed!"
                )
                TryRemountPartitionAsRW(
                    options.chromeos_root, options.remote, log_level
                )

            if not found:
                temp_dir = os.path.dirname(located_image)
                l.LogOutput("Deleting temp image dir: %s" % temp_dir)
                shutil.rmtree(temp_dir)
            l.LogOutput("Image updated.")
        else:
            l.LogOutput("Checksums match, skip image update and reboot.")
            command = "reboot && exit"
            _ = cmd_executer.CrosRunCommand(
                command,
                chromeos_root=options.chromeos_root,
                machine=options.remote,
            )
            # Wait 30s after reboot.
            time.sleep(30)

    finally:
        if should_unlock:
            locks.ReleaseLock(
                list(options.remote.split()), options.chromeos_root
            )

    return ret


def LocateOrCopyImage(chromeos_root, image, board=None):
    l = logger.GetLogger()
    if board is None:
        board_glob = "*"
    else:
        board_glob = board

    chromeos_root_realpath = os.path.realpath(chromeos_root)
    image = os.path.realpath(image)

    if image.startswith("%s/" % chromeos_root_realpath):
        return [True, image]

    # First search within the existing build dirs for any matching files.
    images_glob = "%s/src/build/images/%s/*/*.bin" % (
        chromeos_root_realpath,
        board_glob,
    )
    images_list = glob.glob(images_glob)
    for potential_image in images_list:
        if filecmp.cmp(potential_image, image):
            l.LogOutput(
                "Found matching image %s in chromeos_root." % potential_image
            )
            return [True, potential_image]
    # We did not find an image. Copy it in the src dir and return the copied
    # file.
    if board is None:
        board = ""
    base_dir = "%s/src/build/images/%s" % (chromeos_root_realpath, board)
    if not os.path.isdir(base_dir):
        os.makedirs(base_dir)
    temp_dir = tempfile.mkdtemp(prefix="%s/tmp" % base_dir)
    new_image = "%s/%s" % (temp_dir, os.path.basename(image))
    l.LogOutput(
        "No matching image found. Copying %s to %s" % (image, new_image)
    )
    shutil.copyfile(image, new_image)
    return [False, new_image]


def GetImageMountCommand(image, rootfs_mp, stateful_mp):
    image_dir = os.path.dirname(image)
    image_file = os.path.basename(image)
    mount_command = (
        "cd /mnt/host/source/src/scripts &&"
        "./mount_gpt_image.sh --from=%s --image=%s"
        " --safe --read_only"
        " --rootfs_mountpt=%s"
        " --stateful_mountpt=%s"
        % (image_dir, image_file, rootfs_mp, stateful_mp)
    )
    return mount_command


def MountImage(
    chromeos_root,
    image,
    rootfs_mp,
    stateful_mp,
    log_level,
    unmount=False,
    extra_commands="",
):
    cmd_executer = command_executer.GetCommandExecuter(log_level=log_level)
    command = GetImageMountCommand(image, rootfs_mp, stateful_mp)
    if unmount:
        command = "%s --unmount" % command
    if extra_commands:
        command = "%s ; %s" % (command, extra_commands)
    ret, out, _ = cmd_executer.ChrootRunCommandWOutput(chromeos_root, command)
    logger.GetLogger().LogFatalIf(ret, "Mount/unmount command failed!")
    return out


def IsImageModdedForTest(chromeos_root, image, log_level):
    if log_level != "verbose":
        log_level = "quiet"
    command = "mktemp -d"
    cmd_executer = command_executer.GetCommandExecuter(log_level=log_level)
    _, rootfs_mp, _ = cmd_executer.ChrootRunCommandWOutput(
        chromeos_root, command
    )
    _, stateful_mp, _ = cmd_executer.ChrootRunCommandWOutput(
        chromeos_root, command
    )
    rootfs_mp = rootfs_mp.strip()
    stateful_mp = stateful_mp.strip()
    lsb_release_file = os.path.join(rootfs_mp, "etc/lsb-release")
    extra = "grep CHROMEOS_RELEASE_TRACK %s | grep -i test" % lsb_release_file
    output = MountImage(
        chromeos_root,
        image,
        rootfs_mp,
        stateful_mp,
        log_level,
        extra_commands=extra,
    )
    is_test_image = re.search("test", output, re.IGNORECASE)
    MountImage(
        chromeos_root, image, rootfs_mp, stateful_mp, log_level, unmount=True
    )
    return is_test_image


def VerifyChromeChecksum(chromeos_root, image, remote, log_level):
    command = "mktemp -d"
    cmd_executer = command_executer.GetCommandExecuter(log_level=log_level)
    _, rootfs_mp, _ = cmd_executer.ChrootRunCommandWOutput(
        chromeos_root, command
    )
    _, stateful_mp, _ = cmd_executer.ChrootRunCommandWOutput(
        chromeos_root, command
    )
    rootfs_mp = rootfs_mp.strip()
    stateful_mp = stateful_mp.strip()
    chrome_file = "%s/opt/google/chrome/chrome" % rootfs_mp
    extra = "md5sum %s" % chrome_file
    out = MountImage(
        chromeos_root,
        image,
        rootfs_mp,
        stateful_mp,
        log_level,
        extra_commands=extra,
    )
    image_chrome_checksum = out.strip().split()[0]
    MountImage(
        chromeos_root, image, rootfs_mp, stateful_mp, log_level, unmount=True
    )

    command = "md5sum /opt/google/chrome/chrome"
    [_, o, _] = cmd_executer.CrosRunCommandWOutput(
        command, chromeos_root=chromeos_root, machine=remote
    )
    device_chrome_checksum = o.split()[0]
    return image_chrome_checksum.strip() == device_chrome_checksum.strip()


# Remount partition as writable.
# TODO: auto-detect if an image is built using --noenable_rootfs_verification.
def TryRemountPartitionAsRW(chromeos_root, remote, log_level):
    l = logger.GetLogger()
    cmd_executer = command_executer.GetCommandExecuter(log_level=log_level)
    command = "sudo mount -o remount,rw /"
    ret = cmd_executer.CrosRunCommand(
        command,
        chromeos_root=chromeos_root,
        machine=remote,
        terminated_timeout=10,
    )
    if ret:
        ## Safely ignore.
        l.LogWarning(
            "Failed to remount partition as rw, "
            "probably the image was not built with "
            '"--noenable_rootfs_verification", '
            "you can safely ignore this."
        )
    else:
        l.LogOutput("Re-mounted partition as writable.")


def EnsureMachineUp(chromeos_root, remote, log_level):
    l = logger.GetLogger()
    cmd_executer = command_executer.GetCommandExecuter(log_level=log_level)
    timeout = 600
    magic = "abcdefghijklmnopqrstuvwxyz"
    command = "echo %s" % magic
    start_time = time.time()
    while True:
        current_time = time.time()
        if current_time - start_time > timeout:
            l.LogError(
                "Timeout of %ss reached. Machine still not up. Aborting."
                % timeout
            )
            return False
        ret = cmd_executer.CrosRunCommand(
            command, chromeos_root=chromeos_root, machine=remote
        )
        if not ret:
            return True


if __name__ == "__main__":
    retval = DoImage(sys.argv)
    sys.exit(retval)
