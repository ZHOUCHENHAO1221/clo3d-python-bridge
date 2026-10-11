# -*- coding: utf-8 -*-
"""The host/worker contract. No GUI, no CLO - so this module is testable on any machine.

Why a file-based protocol at all, when the host starts the worker itself?

Because the host cannot see what the worker returns. CLO's Python editor runs the script in
CLO's own interpreter and reports nothing back to the process that pressed Play. Worse, Qt can
invalidate the editor's automation handle while CLO is still executing, so the *host* sees an
error while the *worker* is running happily. Any design that treats the click's outcome as the
job's outcome will report failures that did not happen and successes that did not finish.

So the only thing that counts as a result is a file the worker itself wrote:

    <job>/request.json     host -> worker, the payload
    <job>/heartbeat.json   worker -> host, "still alive, currently doing X"
    <job>/result.json      worker -> host, the single source of truth

The host polls for result.json and ignores everything else it might think it knows.
"""
import json
import os
import tempfile
import time
import uuid

MARKER = "# clo_bridge loader - safe to overwrite"
REQUEST = "request.json"
HEARTBEAT = "heartbeat.json"
RESULT = "result.json"


def write_json(path, payload):
    """Write atomically. A half-written result.json read by the poller is a race we can avoid."""
    tmp = "%s.%s.tmp" % (path, uuid.uuid4().hex[:8])
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def new_job_dir(root=None):
    """A fresh directory for one job. Defaults under the system temp dir."""
    root = root or os.path.join(tempfile.gettempdir(), "clo_bridge_jobs")
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6])
    os.makedirs(path)
    return path


def build_loader(script_path, job_dir, src_root):
    """The text typed into CLO's Python editor.

    It is deliberately boring: put the package on sys.path, tell the worker where its job
    directory is, then exec the user's script as __main__. Everything interesting happens in
    the script, which lives on disk and can be edited and diffed like normal code - as opposed
    to being pasted into a GUI text box where nothing is reviewable.

    Paths are embedded with repr() and forward slashes, because a Windows path pasted raw into
    a Python source line turns "\\t" into a tab and silently breaks.
    """
    script = os.path.abspath(script_path).replace("\\", "/")
    job = os.path.abspath(job_dir).replace("\\", "/")
    src = os.path.abspath(src_root).replace("\\", "/")
    return "\n".join([
        MARKER,
        "import sys",
        "if %r not in sys.path: sys.path.insert(0, %r)" % (src, src),
        "exec(compile(open(%r, encoding='utf-8').read(), %r, 'exec'), {" % (script, script),
        "    '__name__': '__main__', '__file__': %r, 'CLO_JOB_DIR': %r})" % (script, job),
    ])


def is_our_loader(text):
    """True when the editor holds a loader this package wrote, so overwriting is safe."""
    return text.strip().startswith(MARKER)


def wait_for_result(job_dir, timeout=900.0, poll=0.5, sleep=time.sleep, clock=time.monotonic):
    """Block until the worker writes result.json.

    Returns (result, stage). `stage` is the last heartbeat seen, which is what makes a timeout
    actionable instead of just "it did not finish".

    `sleep` and `clock` are injectable so the tests do not have to spend real seconds.
    """
    result_path = os.path.join(job_dir, RESULT)
    beat_path = os.path.join(job_dir, HEARTBEAT)
    deadline = clock() + timeout
    stage = None
    while True:
        result = read_json(result_path)
        if result is not None:
            return result, stage
        beat = read_json(beat_path)
        if isinstance(beat, dict):
            stage = beat.get("stage", stage)
        if clock() >= deadline:
            return None, stage
        sleep(poll)
