# -*- coding: utf-8 -*-
"""End-to-end tests that need no CLO, no Windows and no pywinauto.

The trick is that the loader the session writes is ordinary Python. A fake editor can therefore
*execute* it, which exercises the real loader text, the real worker module and the real result
protocol - everything except the four pywinauto calls in editor.py.

    python tests/test_offline.py        # or: pytest tests
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from clo_bridge import (CloEditorBusy, CloNotFound, CloSession,  # noqa: E402
                        CloTimeout, CloWorkerError)
from clo_bridge import protocol  # noqa: E402


class FakeEditor(object):
    """A text box that runs what you type into it, like CLO's editor would."""

    def __init__(self, text="", execute=True, play_note=None):
        self.text = text
        self.execute = execute
        self.plays = 0
        self.play_note = play_note

    def read(self):
        return self.text

    def write(self, text):
        self.text = text

    def play(self):
        """Returns a note instead of raising, like the real one."""
        self.plays += 1
        if self.execute:
            exec(compile(self.text, "<editor>", "exec"), {"__name__": "__editor__"})
        return self.play_note


def _worker(body):
    """Write a worker script to a temp file and return its path."""
    path = os.path.join(tempfile.mkdtemp(), "worker.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


OK_WORKER = """
from clo_bridge.worker import run, beat

def main(payload):
    beat("working")
    return {"doubled": payload["n"] * 2}

run(main)
"""

BOOM_WORKER = """
from clo_bridge.worker import run

def main(payload):
    raise ValueError("fabric not found")

run(main)
"""

SILENT_WORKER = """
pass
"""


def test_round_trip():
    editor = FakeEditor()
    with CloSession(editor=editor) as clo:
        out = clo.run(_worker(OK_WORKER), {"n": 21})
    assert out == {"doubled": 42}, out
    assert editor.plays == 1


def test_two_jobs_in_one_session_do_not_share_a_job_dir():
    """Regression. CLO keeps clo_bridge.worker loaded between runs, so a cached CLO_JOB_DIR
    would make job two write into job one's directory - which the host has already deleted."""
    editor = FakeEditor()
    with CloSession(editor=editor) as clo:
        first = clo.run(_worker(OK_WORKER), {"n": 1})
        second = clo.run(_worker(OK_WORKER), {"n": 100})
    assert (first, second) == ({"doubled": 2}, {"doubled": 200}), (first, second)


def test_a_failing_play_does_not_end_a_job_that_succeeded():
    """Regression, from a real run. UIA's Invoke is synchronous, so on a long job it is still
    waiting when CLO stops answering and then it fails - for a job running perfectly well. An
    earlier version let that exception out of run() and the poll never started."""
    editor = FakeEditor(play_note="invoke: COMError / click_input: COMError")
    with CloSession(editor=editor) as clo:
        assert clo.run(_worker(OK_WORKER), {"n": 3}) == {"doubled": 6}


def test_worker_exception_reaches_the_host():
    with CloSession(editor=FakeEditor()) as clo:
        try:
            clo.run(_worker(BOOM_WORKER))
        except CloWorkerError as exc:
            assert "fabric not found" in str(exc), exc
            assert "ValueError" in exc.traceback
            return
    raise AssertionError("a failing worker must raise CloWorkerError")


def test_silent_worker_times_out_and_says_where_it_stopped():
    """A worker that writes nothing must time out rather than hang for ever."""
    with CloSession(editor=FakeEditor(), timeout=0.0) as clo:
        try:
            clo.run(_worker(SILENT_WORKER))
        except CloTimeout as exc:
            assert exc.stage is None
            return
    raise AssertionError("a silent worker must raise CloTimeout")


def test_heartbeat_survives_into_the_timeout():
    """The point of beat(): a timeout should say how far the job got."""
    job = protocol.new_job_dir()
    protocol.write_json(os.path.join(job, protocol.HEARTBEAT), {"stage": "simulating"})
    result, stage = protocol.wait_for_result(job, timeout=0.0)
    assert result is None and stage == "simulating", (result, stage)


def test_refuses_to_overwrite_someone_elses_script():
    editor = FakeEditor(text="import pattern_api  # my own work, unsaved")
    with CloSession(editor=editor) as clo:
        try:
            clo.run(_worker(OK_WORKER))
        except CloEditorBusy:
            assert editor.text.startswith("import pattern_api"), "must not have been touched"
            return
    raise AssertionError("an occupied editor must raise CloEditorBusy")


def test_overwrites_its_own_leftover_loader():
    """Our own loader from a previous run is safe to replace; that must not block a rerun."""
    stale = protocol.build_loader(__file__, tempfile.gettempdir(), "src")
    editor = FakeEditor(text=stale)
    with CloSession(editor=editor) as clo:
        assert clo.run(_worker(OK_WORKER), {"n": 1}) == {"doubled": 2}


def test_loader_embeds_windows_paths_without_escape_damage():
    """A raw Windows path in a source line turns \\t into a tab. repr() is why we do not."""
    loader = protocol.build_loader(r"C:\\temp\\run.py", r"C:\\temp\\job", r"C:\\src")
    assert "\t" not in loader
    assert protocol.is_our_loader(loader)
    compile(loader, "<loader>", "exec")          # must be valid Python


def test_no_clo_gives_an_actionable_message():
    session = CloSession(editor=None)
    session._editor = None
    import clo_bridge.session as mod
    original, mod.find_editor = mod.find_editor, lambda *a, **k: None
    try:
        session.connect()
    except CloNotFound as exc:
        assert "Edit > Python Script" in str(exc)
    else:
        raise AssertionError("missing CLO must raise CloNotFound")
    finally:
        mod.find_editor = original


def test_pruning_takes_old_jobs_and_leaves_everything_else():
    """Deleting the wrong thing here destroys the only record of a failure somebody is still
    looking into, so the rule is narrow: old, and named like a job directory."""
    import time as _t
    root = tempfile.mkdtemp()
    old = protocol.new_job_dir(root)
    young = protocol.new_job_dir(root)
    lock = os.path.join(root, ".clo_bridge.lock")
    stranger = os.path.join(root, "my_notes")
    open(lock, "w").close()
    os.makedirs(stranger)
    ancient = _t.time() - 30 * 86400
    os.utime(old, (ancient, ancient))
    os.utime(stranger, (ancient, ancient))

    assert protocol.prune_jobs(root, keep_days=7.0) == 1
    assert not os.path.exists(old), "an old job directory should go"
    assert os.path.isdir(young), "a recent one must stay"
    assert os.path.exists(lock), "the lock is not a job"
    assert os.path.isdir(stranger), "only directories this module named are ours to delete"


def test_pruning_can_be_turned_off():
    root = tempfile.mkdtemp()
    old = protocol.new_job_dir(root)
    import time as _t
    ancient = _t.time() - 365 * 86400
    os.utime(old, (ancient, ancient))
    CloSession(editor=FakeEditor(), jobs_root=root, prune_days=None).connect()
    assert os.path.isdir(old)


def test_atomic_write_leaves_no_partial_file():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "r.json")
    protocol.write_json(p, {"a": 1})
    assert json.load(open(p, encoding="utf-8")) == {"a": 1}
    assert [f for f in os.listdir(d) if f.endswith(".tmp")] == []


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print("  ok  %s" % fn.__name__)
    print("\n%d passed" % len(tests))
