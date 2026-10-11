# -*- coding: utf-8 -*-
"""The host side: hand a script to CLO, wait for the file the worker writes, return its result.

Usage:

    from clo_bridge import CloSession

    with CloSession() as clo:
        out = clo.run("examples/01_hello_clo.py")
        print(out["patternCount"])

The one rule worth internalising: pressing Play tells you nothing. The session never treats the
click, the control state, or any exception from pywinauto as the job's outcome. Only
`result.json`, written by the worker inside CLO, decides. See reference/PITFALLS.md.
"""
import os
import shutil

from . import protocol
from .editor import find_editor
from .errors import CloEditorBusy, CloNotFound, CloTimeout, CloWorkerError

SRC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CloSession(object):
    """A connection to a running CLO instance's Python editor.

    Parameters
    ----------
    editor : Editor, optional
        Injected for testing. Left out, the session finds the real one.
    jobs_root : str, optional
        Where job directories are created. Defaults to the system temp directory.
    timeout : float
        Seconds to wait for result.json. CLO simulation is slow; 900 is not paranoid.
    keep_jobs : bool
        Keep the job directory after a successful run. Useful while developing a worker.
    """

    def __init__(self, editor=None, jobs_root=None, timeout=900.0, keep_jobs=False):
        self._editor = editor
        self._jobs_root = jobs_root
        self.timeout = timeout
        self.keep_jobs = keep_jobs

    # ------------------------------------------------------------------ context manager
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        return False

    def connect(self):
        if self._editor is None:
            self._editor = find_editor()
        if self._editor is None:
            raise CloNotFound(
                "No CLO window with a Python editor was found. Start CLO, sign in, then "
                "open Edit > Python Script.")
        return self._editor

    # ------------------------------------------------------------------ the one method
    def run(self, script, payload=None, timeout=None):
        """Execute `script` inside CLO and return whatever its worker returned.

        Raises CloEditorBusy if a human's script is open, CloTimeout if nothing came back,
        CloWorkerError if the worker reported a failure.
        """
        editor = self.connect()
        script = os.path.abspath(script)
        if not os.path.isfile(script):
            raise FileNotFoundError(script)

        existing = editor.read().strip()
        if existing and not protocol.is_our_loader(existing):
            raise CloEditorBusy(
                "CLO's Python editor contains a script this bridge did not write. Save it and "
                "clear the editor before running a job - the bridge will not overwrite it.")

        job_dir = protocol.new_job_dir(self._jobs_root)
        protocol.write_json(os.path.join(job_dir, protocol.REQUEST), payload or {})
        editor.write(protocol.build_loader(script, job_dir, SRC_ROOT))
        editor.play()

        result, stage = protocol.wait_for_result(
            job_dir, timeout=self.timeout if timeout is None else timeout)

        if result is None:
            raise CloTimeout(
                "CLO did not write a result within %.0fs. The worker may still be running - "
                "check CLO's Python editor before retrying." % (timeout or self.timeout),
                stage=stage)
        if not result.get("ok"):
            raise CloWorkerError(result.get("error", "worker failed without a message"),
                                 traceback=result.get("traceback"))
        if not self.keep_jobs:
            shutil.rmtree(job_dir, ignore_errors=True)
        return result.get("value")
