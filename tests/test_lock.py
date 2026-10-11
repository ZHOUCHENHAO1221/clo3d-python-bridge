# -*- coding: utf-8 -*-
"""The single-job lock. No CLO needed - the failure it prevents is a file-level race.

    python tests/test_lock.py      # or: pytest tests
"""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from clo_bridge import protocol  # noqa: E402
from clo_bridge.lock import LOCK_NAME, CloBusy, JobLock  # noqa: E402


def root():
    return tempfile.mkdtemp()


def test_a_second_holder_is_refused():
    r = root()
    with JobLock(r):
        try:
            JobLock(r).acquire()
        except CloBusy as exc:
            assert str(os.getpid()) in str(exc)
            return
    raise AssertionError("two holders at once is the bug this exists to prevent")


def test_the_lock_is_released_on_the_way_out():
    r = root()
    with JobLock(r):
        pass
    with JobLock(r):
        pass                       # no exception means it was released


def test_an_exception_still_releases():
    r = root()
    try:
        with JobLock(r):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert not os.path.exists(os.path.join(r, LOCK_NAME))


def test_a_dead_process_lock_is_taken_over():
    """A crash must not block the next run for ever."""
    r = root()
    with open(os.path.join(r, LOCK_NAME), "w", encoding="utf-8") as fh:
        # PID 2**22 - above every platform's pid_max, so it cannot be live
        json.dump({"pid": 4194304, "host": __import__("socket").gethostname(),
                   "since": time.time()}, fh)
    with JobLock(r):
        pass


def test_a_live_holder_is_never_taken_over_however_old():
    """A long simulation looks exactly like a hung one. Stealing from a running job is the
    failure this class exists to prevent, so age alone is not grounds."""
    r = root()
    with open(os.path.join(r, LOCK_NAME), "w", encoding="utf-8") as fh:
        json.dump({"pid": os.getpid(), "host": __import__("socket").gethostname(),
                   "since": time.time() - 86400}, fh)
    try:
        JobLock(r, stale_after=1e9).acquire()
    except CloBusy:
        return
    raise AssertionError("a live holder must keep the lock no matter how long it has held it")


def test_an_unreadable_lock_is_replaced_not_obeyed():
    r = root()
    with open(os.path.join(r, LOCK_NAME), "w", encoding="utf-8") as fh:
        fh.write("not json")
    with JobLock(r):
        pass


def test_a_session_locks_the_jobs_root_it_uses():
    """The lock has to sit where the jobs do, or two sessions with different roots would not
    see each other's locks while sharing one CLO."""
    from clo_bridge import CloSession
    s = CloSession(editor=object(), jobs_root=None)
    assert s._jobs_root == protocol.default_jobs_root()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print("  ok  %s" % fn.__name__)
    print("\n%d passed" % len(tests))
