# -*- coding: utf-8 -*-
"""One job at a time, enforced across processes.

CLO's Python editor is a single slot: one script, one Play button. Two bridge processes sharing
one CLO do not collide loudly - they collide quietly, which is worse.

The sequence that makes it quiet: process A writes its loader and presses Play. Process B
starts, reads the editor, sees A's loader, recognises the marker as **this package's own**, and
concludes it is a leftover that is safe to overwrite. B overwrites a job that is mid-flight. A
then polls for a result file nobody will ever write and times out after its full timeout, while
B's job runs to completion and looks fine.

So the "is this our loader" check, which exists to protect a human's unsaved work, fails open
against another copy of ourselves. This closes it. The lock is held for the whole job - write,
play and wait - because that is how long CLO is occupied.
"""
import errno
import json
import os
import socket
import time

from .errors import CloError

LOCK_NAME = ".clo_bridge.lock"


class CloBusy(CloError):
    """Another process is driving this CLO. `holder` says which, if the lock was readable."""

    def __init__(self, message, holder=None):
        super().__init__(message)
        self.holder = holder


def _alive(pid):
    """Best-effort liveness check. True when unsure - never steal a lock on a guess."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        except Exception:
            return True
    try:
        os.kill(pid, 0)
        return True
    except OSError as exc:
        return exc.errno != errno.ESRCH
    except Exception:
        return True


class JobLock(object):
    """Hold the right to drive CLO. Use as a context manager.

    A lock left behind by a process that is no longer running is taken over. A lock held by a
    live process is never taken over, however old it is: a long simulation looks exactly like a
    hung one from here, and stealing from a running job is the failure this class exists to
    prevent.
    """

    def __init__(self, root, stale_after=7200.0):
        self.path = os.path.join(root, LOCK_NAME)
        self.stale_after = stale_after
        self._held = False

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def acquire(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        payload = json.dumps({"pid": os.getpid(), "host": socket.gethostname(),
                              "since": time.time()})
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise
            holder = self._read()
            pid = (holder or {}).get("pid")
            same_host = (holder or {}).get("host") == socket.gethostname()
            age = time.time() - (holder or {}).get("since", 0)
            if holder is None or (same_host and not _alive(pid)) or age > self.stale_after:
                # The owner is gone, or the lock is older than any job should be. Take it.
                os.unlink(self.path)
                return self.acquire()
            raise CloBusy(
                "another process is driving CLO (pid %s on %s, for %.0fs). CLO's editor is a "
                "single slot, so this job would overwrite that one mid-flight. Wait, or remove "
                "%s if you are certain that process is gone."
                % (pid, (holder or {}).get("host"), age, self.path), holder=holder)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        self._held = True
        return self

    def release(self):
        if not self._held:
            return
        self._held = False
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
        return False
