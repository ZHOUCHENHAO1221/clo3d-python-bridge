---
name: clo3d-python-bridge
description: Use when automating CLO Standalone (CLO3D) from Python - running its Python API without a GUI session you drive by hand, importing DXF patterns, applying fabrics, simulating, batch rendering, or exporting. Covers the fact that CLO has no headless mode and no CLI entry point, and the specific traps in driving its built-in Python editor.
---

# CLO3D Python bridge

## What this solves

CLO Standalone exposes a large Python API — roughly 800 functions across `utility_api`,
`pattern_api`, `fabric_api`, `import_api` and `export_api` — and **no way to call it except by
pasting a script into `Edit > Python Script` and pressing Play**. There is no headless flag, no
`clo --script`, no socket. Every "how do I automate CLO" answer ends there.

This package automates that window, and gives the two halves a contract that survives the ways
CLO's UI misreports what happened.

## Before writing any worker

Read `reference/PITFALLS.md`. It is short and every entry cost hours. The three that matter most:

1. **Pressing Play tells you nothing.** Qt can invalidate the editor's automation handle while
   CLO is still executing, so the host sees an error for a job that succeeded. The only evidence
   of an outcome is a file the worker itself wrote.
2. **CLO keeps your modules loaded between runs.** Anything a worker caches at module level
   leaks into the next job. Never cache the job directory or any per-job state.
3. **"The simulation ran" ≠ "the parameter took effect."** Verify the output changed. Nine times
   out of ten a parameter that "has no effect" was applied to a different piece.

## Using it

```python
from clo_bridge import CloSession

with CloSession() as clo:
    info = clo.run("examples/01_hello_clo.py")
    print(info["version"], info["patternCount"])
```

A worker is an ordinary script on disk — reviewable, diffable, testable — not text in a GUI box:

```python
from clo_bridge.api import require
from clo_bridge.worker import run, beat

def main(payload):
    pattern = require("pattern_api", "GetPatternCount")   # fails loudly on the wrong build
    beat("counting")                                      # makes a timeout actionable
    return {"n": pattern.GetPatternCount()}

run(main)       # always writes result.json, including on exception
```

## Finding the function you need

`reference/API_MAP.md` indexes the API surface **by task** (import, fabric, simulation, camera,
export, grading, …) rather than alphabetically. Names ending in `W` are the wide-string variants
— use those for any path or label that may contain non-ASCII characters.

The committed map is a snapshot. Regenerate it against your own build:

```bash
python scripts/probe_api.py        # read-only; writes scripts/api_surface.json
python scripts/build_api_map.py    # -> reference/API_MAP.md
```

## Things it cannot do

- **No headless.** Running on a server means a full desktop session with CLO signed in. The
  licence position on that is between the user and CLO. This package never handles credentials
  and never automates sign-in.
- **No concurrency.** CLO's editor is a single slot and the GUI blocks. Serialise jobs.
- **Windows only**, because the UI automation is `pywinauto`.
- **No signatures.** `dir()` gives names, not argument order. The examples name-check every call
  but cannot verify argument order; confirm against CLO's own documentation.

## Verifying a change

`python tests/test_offline.py` runs the whole protocol — loader, worker, result, heartbeat,
timeout, refusal to overwrite — with a fake editor, so it needs no CLO and no Windows. Run it
after touching anything in `src/clo_bridge/`.
