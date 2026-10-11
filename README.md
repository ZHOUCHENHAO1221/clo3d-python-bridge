# clo3d-python-bridge

[![tests](https://github.com/ZHOUCHENHAO1221/clo3d-python-bridge/actions/workflows/tests.yml/badge.svg)](https://github.com/ZHOUCHENHAO1221/clo3d-python-bridge/actions/workflows/tests.yml)

Drive **CLO Standalone's Python API from an ordinary Python process** — import patterns, apply
fabrics, simulate, render, export — on a machine where CLO is running.

```python
from clo_bridge import CloSession

with CloSession() as clo:
    info = clo.run("examples/01_hello_clo.py")

print(info["version"], info["patternCount"])
```

---

## Why this exists

CLO exposes about **800 Python functions** across five modules, and **no way to call them
except by hand**: paste into `Edit > Python Script`, press Play. No headless flag, no
`clo --script`, no socket, no RPC. If you have searched for how to automate CLO, you have
already found that there is no answer — this is the missing piece.

So the bridge automates that window. That part is a few hundred lines. The part worth reading is
[`reference/PITFALLS.md`](reference/PITFALLS.md), which documents the ways CLO's UI will lie to
you and what to do about each one. The headline:

> **Pressing Play tells you nothing.** Qt can invalidate the editor's automation handle while
> CLO is still executing, so your automation reports a failure for a job that succeeded. The
> only evidence of an outcome is a file the worker itself wrote.

Everything in this package follows from that.

## Install

```bash
git clone https://github.com/ZHOUCHENHAO1221/clo3d-python-bridge
cd clo3d-python-bridge
pip install -e .
```

Requires Windows, Python 3.8+, and `pywinauto`. CLO must be running and signed in, with a
document open.

## Five-minute check

```bash
python examples/01_hello_clo.py
```

Read-only — it opens nothing, changes nothing, saves nothing. Expected:

```
CLO 2026.1.224
project: my_garment
patterns: 7
```

If it says `No CLO window with a Python editor was found`, open `Edit > Python Script` in CLO
and run it again.

## Writing a worker

A worker is a normal file on disk, so it can be reviewed, diffed and version-controlled — which
text pasted into a GUI box cannot.

```python
from clo_bridge.api import require, changed
from clo_bridge.worker import run, beat

def main(payload):
    importer = require("import_api", "ImportDXFW")      # fails clearly on a build that
    pattern  = require("pattern_api", "GetPatternCount")  # spells it differently

    before = pattern.GetPatternCount()
    beat("importing")                                   # a timeout can now say where it stopped
    importer.ImportDXFW(payload["dxf"])
    changed(before, pattern.GetPatternCount(), "pattern count")   # the import actually did something

    return {"patterns": pattern.GetPatternCount()}

run(main)       # writes result.json on every path, exceptions included
```

Run it:

```python
with CloSession() as clo:
    clo.run("my_worker.py", {"dxf": r"C:\patterns\front.dxf"})
```

## What is in here

| | |
|---|---|
| `src/clo_bridge/` | the bridge: `session` (host), `worker` (inside CLO), `protocol` (the contract), `editor` (UI automation), `api` (`require` / `changed`) |
| `reference/PITFALLS.md` | **read this first** — every trap, symptom first |
| `reference/API_MAP.md` | ~800 functions grouped by task, not alphabetically |
| `scripts/probe_api.py` | regenerate the map against your own CLO build |
| `examples/` | hello, DXF→simulate→OBJ, fixed-camera fabric sweep |
| `tests/test_offline.py` | the whole protocol, with a fake editor — no CLO needed |

## Honest limits

- **There is no headless mode.** Running this on a server means a real desktop session with CLO
  signed in. Whether your licence permits that is between you and CLO. This package never
  touches credentials and never automates sign-in — it drives an instance a human signed in to.
- **One job at a time.** CLO's editor is a single slot and the GUI blocks while a script runs.
- **Windows only** (`pywinauto`).
- **The API map has names, not signatures.** `dir()` cannot report argument order. Examples
  name-check every call, but the argument order in examples 02 and 03 is **not verified against
  a running CLO** — those files say so at the top. Check against CLO's own documentation.
- **The committed `api_surface.json` is a contributed snapshot** whose CLO build was not
  recorded. Regenerate it on your install rather than trusting it.
- The UI automation itself cannot be covered by tests in CI, because CI has no CLO. The
  protocol — loader, worker, results, heartbeats, timeouts, refusals — is fully covered by
  `tests/test_offline.py`, which runs anywhere.

## Tests

```bash
python tests/test_offline.py
```

Ten tests, no CLO, no Windows, no pytest required. They execute the real loader text and the
real worker module against a fake editor, so everything except the four `pywinauto` calls is
exercised.

## Licence

MIT. CLO Standalone is a commercial product of CLO Virtual Fashion Inc.; this project is not
affiliated with or endorsed by them, and it contains no CLO code.
