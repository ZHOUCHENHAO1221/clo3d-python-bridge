# -*- coding: utf-8 -*-
"""Simulate one garment in every fabric you hand it, and measure each result.

    python examples/04_sweep.py garment.zprj fabrics/*.zfab -o out/ [--repeats 2] [--steps 60]

This is the script behind the contact sheet in the README: twenty-seven runs, 5.3 minutes, no
one at the keyboard. Verified against CLO 2026.1.310.

Each run starts from a fresh import, so nothing carries over from the last one. Then:

    load the .zfab                 AddFabricW -> an index
    assign it to every piece       pattern_api.SetPatternPieceFabricIndex
    READ THE ASSIGNMENT BACK       GetPatternPieceFabricIndex, and stop if it did not stick
    fix the solver                 quality and time step, so runs are comparable
    simulate, export, measure      clo_bridge.mesh, off the exported geometry

Three things in that list are the whole point of the example.

**Reading the assignment back.** `SetPatternPieceFabricIndex` returns None. A sweep where the
fabric silently failed to apply produces N identical garments and a table of numbers that all
look plausible. Nobody re-checks a table that looks plausible.

**Fixing the solver.** Quality and time step are session state, not project state. Leave them
to whatever the last person set and your runs are not comparable to each other, let alone to
anyone else's.

**Measuring off the mesh.** Not asking the simulator. And not the bounding box - see
`clo_bridge.mesh`, which finds the lowest closed boundary loop instead, because the lowest
vertex of a garment is usually a fold.

Progress is written after every run. Stop it, and the next start skips what is already done.
"""
import argparse
import glob
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def main(payload):
    """Runs inside CLO. One fabric, one repeat - the host drives the loop."""
    from clo_bridge.api import require
    from clo_bridge.worker import beat

    importer = require("import_api", "ImportZprjW")
    pattern = require("pattern_api", "GetPatternCount", "SetPatternPieceFabricIndex",
                      "GetPatternPieceFabricIndex")
    fabric = require("fabric_api", "AddFabricW", "GetFabricNameW")
    utility = require("utility_api", "Simulate", "SetSimulationQuality",
                      "SetSimulationTimeStep")
    exporter = require("export_api", "ExportOBJW")
    types = require("ApiTypes", "ImportZPRJOption", "ImportExportOption")

    zprj, zfab, out = payload["zprj"], payload["zfab"], payload["obj"]

    beat("opening the garment")
    if not importer.ImportZprjW(zprj, types.ImportZPRJOption()):
        raise RuntimeError("ImportZprjW returned False for %s" % zprj)
    pieces = pattern.GetPatternCount()
    if pieces < 1:
        raise RuntimeError("the project opened with no pattern pieces")

    beat("loading %s" % os.path.basename(zfab))
    index = fabric.AddFabricW(zfab)
    if not isinstance(index, int) or index < 0:
        raise RuntimeError("AddFabricW returned %r for %s" % (index, zfab))
    for i in range(pieces):
        pattern.SetPatternPieceFabricIndex(i, index)
    wrong = [i for i in range(pieces) if pattern.GetPatternPieceFabricIndex(i) != index]
    if wrong:
        raise RuntimeError(
            "the fabric did not stick on piece(s) %s. The setter returns None, so this check "
            "is the only thing between you and a sweep of identical garments." % wrong)

    utility.SetSimulationQuality(payload["quality"], 0)
    utility.SetSimulationTimeStep(1.0 / payload["fps"])
    beat("simulating")
    started = time.perf_counter()
    if not utility.Simulate(payload["steps"]):
        raise RuntimeError("Simulate returned False")
    seconds = round(time.perf_counter() - started, 1)

    beat("exporting")
    # The options object is what keeps this headless; ExportOBJW without it opens a dialog.
    # It also has to be configured, because the defaults are not what a measurement wants:
    #   bExportAvatar defaults to TRUE, so the mannequin comes with the garment. On this
    #   project that made the garment 38.7% of the exported surface, and the lowest closed
    #   boundary loop could as easily have been the avatar's ankle as the hem.
    #   weldType decides whether the panels arrive as one surface or as loose pieces.
    opt = types.ImportExportOption()
    opt.bExportAvatar = False
    opt.bSingleObject = True
    try:
        opt.weldType = types.WELD_TYPE.FULLY_WELDED
    except Exception:
        pass                       # older builds may spell it differently; the refusal in
                                   # clo_bridge.mesh catches the consequence either way
    exporter.ExportOBJW(out, opt)
    if not os.path.isfile(out):
        raise RuntimeError("no mesh was written at %s" % out)
    return {"fabric": fabric.GetFabricNameW(index), "fabricIndex": index,
            "pieces": pieces, "seconds": seconds, "obj": out}


if "CLO_JOB_DIR" in globals():
    from clo_bridge.worker import run
    run(main)
elif __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("zprj")
    ap.add_argument("zfab", nargs="+", help="fabric files; shell globs are fine")
    ap.add_argument("-o", "--out", default="sweep_out")
    ap.add_argument("--repeats", type=int, default=1,
                    help="runs per fabric. 2 or more sizes the run-to-run noise, which you "
                         "need before any difference between fabrics means anything")
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--quality", type=int, default=2)
    ap.add_argument("--fps", type=int, default=30, help="time step is 1/fps")
    a = ap.parse_args()

    from clo_bridge import CloBusy, CloSession, CloTimeout, CloWorkerError
    from clo_bridge.mesh import MeshInvalid, MeshTooLarge, largest_surface, loop_span, measure

    # Failures a sweep should record and carry on past: this garment in this fabric did not
    # work. Anything else - a typo in the worker, a missing file, a broken install - is not a
    # property of one run, and continuing would repeat it for every fabric and hand back a
    # ledger of identical "failures" that looks like data.
    PER_RUN = (CloWorkerError, CloTimeout, MeshInvalid, MeshTooLarge, OSError)

    fabrics = sorted({p for g in a.zfab for p in (glob.glob(g) or [g])})
    os.makedirs(a.out, exist_ok=True)
    ledger = os.path.join(a.out, "progress.json")
    done = {}
    if os.path.exists(ledger):
        with open(ledger, encoding="utf-8") as fh:
            done = {r["slot"]: r for r in json.load(fh)["runs"]}
        print("resuming: %d run(s) already recorded" % len(done))

    plan = [(f, r) for f in fabrics for r in range(1, a.repeats + 1)]
    print("%d run(s): %d fabric(s) x %d repeat(s)" % (len(plan), len(fabrics), a.repeats))

    def save():
        tmp = ledger + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"zprj": os.path.abspath(a.zprj), "steps": a.steps,
                       "quality": a.quality, "fps": a.fps,
                       "runs": [done[k] for k in sorted(done)]}, fh, indent=1)
        os.replace(tmp, ledger)

    consecutive = 0
    with CloSession(timeout=1800) as clo:
        for zfab, rep in plan:
            slot = "%s_r%d" % (os.path.splitext(os.path.basename(zfab))[0], rep)
            if slot in done and done[slot].get("status") == "ok":
                continue
            raw = os.path.join(a.out, slot + "_raw.obj")
            rec = {"slot": slot, "zfab": os.path.abspath(zfab), "repeat": rep}
            try:
                rec.update(clo.run(__file__, {
                    "zprj": os.path.abspath(a.zprj), "zfab": os.path.abspath(zfab),
                    "obj": raw, "steps": a.steps, "quality": a.quality, "fps": a.fps}))
                surface = os.path.join(a.out, slot + ".obj")
                rec["surface"] = largest_surface(raw, surface)
                m = measure(surface)
                loop = m["lowestClosedLoop"]
                rec.update({
                    "status": "ok",
                    "nonManifoldEdges": m["nonManifoldEdges"],
                    "boundaryLoops": len(m["boundaryLoops"]),
                    "lowestLoopY": None if loop is None else round(loop["min"], 2),
                    "lowestLoopWidth": None if loop is None else round(loop_span(m), 2),
                    "bboxMinY": round(m["bbox"]["min"][1], 2),
                })
                if loop is None:
                    rec["status"] = "no closed boundary loop - look at the mesh"
            except CloBusy:
                raise
            except PER_RUN as exc:
                rec.update({"status": "failed", "error": "%s: %s" % (type(exc).__name__, exc)})
            except Exception as exc:
                rec.update({"status": "failed",
                            "error": "%s: %s" % (type(exc).__name__, exc),
                            "stopped": "not a per-run failure"})
                done[slot] = rec
                save()
                print("  %-22s %s" % (slot, rec["error"]))
                raise SystemExit(
                    "\nStopped: that is not a failure of one run. %d of %d done, recorded in "
                    "%s - fix it and start again, the finished runs are skipped."
                    % (len([r for r in done.values() if r.get("status") == "ok"]),
                       len(plan), ledger))
            done[slot] = rec
            save()
            print("  %-22s %s" % (slot, rec.get("status")))
            # Three in a row is not about the cloth. Stopping beats handing back a ledger of
            # identical failures that reads like a result.
            consecutive = 0 if rec.get("status") == "ok" else consecutive + 1
            if consecutive >= 3:
                raise SystemExit(
                    "\nStopped after three failures in a row. Whatever is wrong is not about "
                    "one fabric. Ledger: %s" % ledger)

    ok = [r for r in done.values() if r.get("status") == "ok"]
    print("\n%d/%d ok, ledger at %s\n" % (len(ok), len(done), ledger))
    if ok:
        print("%-22s %8s %10s %10s %8s" % ("run", "sec", "loop Y", "loop width", "bbox Y"))
        for r in sorted(ok, key=lambda r: r["slot"]):
            print("%-22s %8.1f %10s %10s %8s" % (r["slot"], r["seconds"], r["lowestLoopY"],
                                                 r["lowestLoopWidth"], r["bboxMinY"]))
        spread = {r["lowestLoopWidth"] for r in ok}
        if len(ok) > 1 and len(spread) == 1:
            print("\nEvery run produced the same hem width. Before reading anything into that, "
                  "check the fabric actually changed between runs.")
