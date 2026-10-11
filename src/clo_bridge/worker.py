# -*- coding: utf-8 -*-
"""The worker side: this half runs *inside* CLO's interpreter.

A worker script looks like this and nothing more:

    from clo_bridge.worker import run, beat

    def main(payload):
        import pattern_api, utility_api
        beat("loading")
        ...
        return {"patternCount": pattern_api.GetPatternCount()}

    run(main)

`run` takes care of the parts that are easy to get wrong:

* It always writes result.json, including when `main` raises - a worker that dies silently
  leaves the host waiting the full timeout for no reason.
* It writes the traceback into the result, because a traceback shown in CLO's editor is a
  screenshot, not something the host can log.
* It never calls sys.exit. Inside CLO that would be an exit of CLO's own interpreter.
"""
import os
import sys
import traceback

from . import protocol

def job_dir():
    """Where this job's files live. Injected by the loader as CLO_JOB_DIR.

    Resolved fresh on every call, never cached. CLO's interpreter keeps this module loaded
    between runs, so a cached value would make the second job of a session write its heartbeat
    and result into the *first* job's directory - which the host has already deleted. The host
    then waits out its whole timeout for a result that was written somewhere else.
    """
    frame = sys._getframe()
    while frame is not None:
        if "CLO_JOB_DIR" in frame.f_globals:
            return frame.f_globals["CLO_JOB_DIR"]
        frame = frame.f_back
    found = os.environ.get("CLO_JOB_DIR")
    if not found:
        raise RuntimeError(
            "No CLO_JOB_DIR. Run this script through clo_bridge.CloSession, not by hand.")
    return found


def payload():
    """What the host sent."""
    return protocol.read_json(os.path.join(job_dir(), protocol.REQUEST), {})


def beat(stage):
    """Tell the host what you are doing now.

    Worth calling before anything slow. When a job times out, this is the difference between
    "it failed" and "it got as far as simulating and simulation is just slow".
    """
    protocol.write_json(os.path.join(job_dir(), protocol.HEARTBEAT), {"stage": str(stage)})


def run(main):
    """Call `main(payload)` and write its return value to result.json."""
    path = os.path.join(job_dir(), protocol.RESULT)
    try:
        value = main(payload())
        protocol.write_json(path, {"ok": True, "value": value})
    except BaseException as exc:                      # noqa: BLE001 - CLO must not be killed
        protocol.write_json(path, {"ok": False,
                                   "error": "%s: %s" % (type(exc).__name__, exc),
                                   "traceback": traceback.format_exc()})
