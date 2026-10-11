# -*- coding: utf-8 -*-
"""Load a measured fabric file into CLO and check that its numbers arrived.

    python examples/03_load_measured_fabric.py path/to/fabric.zfab

Verified against CLO 2026.1.310.

Why this example loads a file rather than setting numbers: across the fifty-nine writers in
`fabric_api`, none sets bending, stretch or shear. They set colour, roughness, metalness,
opacity, texture maps, the name, the item number, the roll width and metadata.
`ChangeFabricWithJson` looks like the way in and is not - the JSON it round-trips has 31 keys
and every one is appearance.

There is one route that has NOT been tested here and that you should know about before quoting
the paragraph above: `GetFabricInformationW` returns a dict containing `Weight` and
`Thickness`, and `SetFabricInformationW(index, dict)` is its exact write counterpart. Whether
writing through it reaches the solver, updates only the displayed metadata, or is ignored
outright is unknown - and it returns None, so the call tells you nothing either way. See
reference/PITFALLS.md.

What this script does is the route that is known to work. Loading a `.zfab` from a script
delivers the values:

    CLO's default fabric   0.5 mm    300 g/m2
    a measured .zfab       0.22 mm   135.3 g/m2

Read `GetFabricInformationW` back after loading and compare, the way this does. "AddFabricW
returned an index" and "the fabric in the document has the values I measured" are different
claims, and only the second one is worth putting in a report.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def main(payload):
    """Runs inside CLO."""
    from clo_bridge.api import require
    from clo_bridge.worker import beat

    fabric = require("fabric_api", "AddFabricW", "GetFabricNameW", "GetFabricInformationW")
    path = payload["zfab"]

    before = dict(fabric.GetFabricInformationW(0))
    beat("loading %s" % os.path.basename(path))
    index = fabric.AddFabricW(path)
    if not isinstance(index, int) or index < 0:
        raise RuntimeError("AddFabricW returned %r for %s" % (index, path))

    loaded = dict(fabric.GetFabricInformationW(index))
    moved = [k for k in ("Weight", "Thickness") if before.get(k) != loaded.get(k)]
    if not moved:
        raise RuntimeError(
            "The fabric loaded at index %d but reads the same weight and thickness as the one "
            "already in the document (%s). Either the file carries CLO's defaults or it did "
            "not take." % (index, before))

    return {"index": index, "name": fabric.GetFabricNameW(index),
            "before": before, "loaded": loaded, "changed": moved}


if "CLO_JOB_DIR" in globals():
    from clo_bridge.worker import run
    run(main)
elif __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: 03_load_measured_fabric.py path/to/fabric.zfab")
    from clo_bridge import CloSession
    with CloSession() as clo:
        r = clo.run(__file__, {"zfab": os.path.abspath(sys.argv[1])})
    print("loaded %r at index %d" % (r["name"], r["index"]))
    for key in ("Weight", "Thickness"):
        print("  %-10s %-12s -> %s" % (key, r["before"].get(key), r["loaded"].get(key)))
