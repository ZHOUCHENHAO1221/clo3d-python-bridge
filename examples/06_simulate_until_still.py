# -*- coding: utf-8 -*-
"""Simulate a garment until it stops moving, and say whether it did.

    python examples/06_simulate_until_still.py garment.zprj -o out/ [--block 60]
           [--threshold 0.5] [--cap 1200]

A fixed step count can stop while the garment is still falling (reference/PITFALLS.md, "Sixty
steps is not simulated"). This simulates in blocks, exports an OBJ after each block, and stops
when the mean vertex movement between two exports falls below the threshold, or at the cap.
It returns the steps run, a `settled` flag that is False when the cap was reached first, and
the movement after each block. A run that hit the cap is still returned, marked unsettled; do
not read it as a run at rest.

Two more things are in it because they decide whether the check means anything:

- **Per group, not only the mean.** The export keeps one OBJ group per object
  (`bSingleObject = False`), and each block also reports the group that moved most. A small
  piece that is still moving hardly changes the garment's mean.
- **A light export.** Every topstitch style drawn in 3D is switched to texture for the export
  and switched back in `finally`, because 3D topstitches can make an export hundreds of
  megabytes. The file size is checked against `clo_bridge.mesh.MAX_BYTES` before it is parsed.

The solver quality is read and recorded, not set: this measures the project as it is saved.

What it changes: it imports the project you name, which replaces the open document, then
simulates. It never saves. It refuses to start if CLO has a different project open, so save
yours and open an empty project first.

The block loop and the topstitch switch are adapted from code run on CLO 2026.1.382
(19 November 2026, a 41-piece top); this file has not been re-run as packaged. The per-group
report is new here and has not been run on CLO at all.
"""
import argparse
import os
import sys
from math import dist

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def read_groups(path):
    """(vertices, {group name: vertex ids its faces use}) from an OBJ, in file order."""
    vertices, groups, name = [], {}, None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("v "):
                vertices.append(tuple(float(x) for x in line.split()[1:4]))
            elif line.startswith(("g ", "o ")):
                name = line[2:].strip()
            elif line.startswith("f "):
                ids = groups.setdefault(name, set())
                for token in line.split()[1:]:
                    i = int(token.split("/")[0])
                    ids.add(i - 1 if i > 0 else len(vertices) + i)
    return vertices, groups


def movement(previous, current):
    """Mean vertex movement between two exports of the same scene, overall and per group."""
    (before, _), (after, groups) = previous, current
    if len(before) != len(after):
        raise RuntimeError("the two exports have different vertex counts (%d, %d); they are "
                           "not the same mesh" % (len(before), len(after)))
    moved = [dist(a, b) for a, b in zip(before, after)]
    per_group = {g: sum(moved[i] for i in ids) / len(ids) for g, ids in groups.items() if ids}
    return sum(moved) / len(moved), per_group


def main(payload):
    """Runs inside CLO."""
    from clo_bridge.api import require
    from clo_bridge.mesh import MAX_BYTES, MeshTooLarge
    from clo_bridge.worker import beat

    importer = require("import_api", "ImportZprjW")
    pattern = require("pattern_api", "GetPatternCount", "GetTopstitchStyleList",
                      "GetTopstitchStyleModelType", "SetTopstitchStyleModelType")
    utility = require("utility_api", "Simulate", "GetSimulationQuality", "GetProjectFilePath")
    exporter = require("export_api", "ExportOBJW")
    types = require("ApiTypes", "ImportZPRJOption", "ImportExportOption")

    zprj, obj = payload["zprj"], payload["obj"]
    block, threshold, cap = payload["block"], payload["threshold"], payload["cap"]

    def same(a, b):
        return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))

    current = utility.GetProjectFilePath()
    if pattern.GetPatternCount() > 0 and not (current and same(current, zprj)):
        raise RuntimeError(
            "CLO has another project open (%s). This example replaces the open document and "
            "never saves, so save yours and open an empty project first."
            % (current or "untitled"))

    beat("opening the garment")
    if not importer.ImportZprjW(zprj, types.ImportZPRJOption()):
        raise RuntimeError("ImportZprjW returned False for %s" % zprj)
    if pattern.GetPatternCount() < 1:
        raise RuntimeError("the project opened with no pattern pieces")
    quality = list(utility.GetSimulationQuality())

    opt = types.ImportExportOption()
    opt.bExportAvatar = False          # default True: the avatar would be measured as cloth
    opt.bSingleObject = False          # one group per object, for the per-group report
    styles = [int(s["TopstitchStyleIndex"]) for s in pattern.GetTopstitchStyleList()]

    def export():
        before = {i: pattern.GetTopstitchStyleModelType(i) for i in styles}
        if any(kind not in (0, 1) for kind in before.values()):
            raise RuntimeError("unexpected topstitch model types %s; nothing changed" % before)
        try:
            for i, kind in before.items():
                if kind == 0:                          # 0 drawn in 3D, 1 drawn as texture
                    pattern.SetTopstitchStyleModelType(i, 1)
            exporter.ExportOBJW(obj, opt)
        finally:
            for i, kind in before.items():
                pattern.SetTopstitchStyleModelType(i, kind)
            wrong = [i for i, kind in before.items()
                     if pattern.GetTopstitchStyleModelType(i) != kind]
            if wrong:
                raise RuntimeError("topstitch styles %s were not restored" % wrong)
        if not os.path.isfile(obj):
            raise RuntimeError("no mesh was written at %s" % obj)
        size = os.path.getsize(obj)
        if size > MAX_BYTES:
            raise MeshTooLarge("%s is %.1f MB; not parsing it inside CLO"
                               % (obj, size / 1048576.0))
        return read_groups(obj)

    steps, previous, blocks, settled = 0, None, [], False
    while True:
        beat("simulating, %d steps so far" % steps)
        if not utility.Simulate(block):
            raise RuntimeError("Simulate returned False")
        steps += block
        beat("exporting after %d steps" % steps)
        exported = export()
        if previous is not None:
            mean, per_group = movement(previous, exported)
            worst = max(per_group, key=per_group.get)
            blocks.append({"steps": steps, "meanMoveMm": round(mean, 4),
                           "worstGroup": worst, "worstGroupMoveMm": round(per_group[worst], 4)})
            if mean < threshold:
                settled = True
                break
        previous = exported
        if steps >= cap:
            break
    return {"steps": steps, "settled": settled, "blocks": blocks, "obj": obj,
            "simulationQuality": quality, "groups": len(exported[1])}


if "CLO_JOB_DIR" in globals():
    from clo_bridge.worker import run
    run(main)
elif __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("zprj")
    ap.add_argument("-o", "--out", default="still_out")
    ap.add_argument("--block", type=int, default=60, help="steps per block")
    ap.add_argument("--threshold", type=float, default=0.5,
                    help="stop when mean movement between blocks is below this, in mm")
    ap.add_argument("--cap", type=int, default=1200, help="stop here even if still moving")
    a = ap.parse_args()

    from clo_bridge import CloSession
    os.makedirs(a.out, exist_ok=True)
    name = os.path.splitext(os.path.basename(a.zprj))[0] + ".obj"
    obj = os.path.abspath(os.path.join(a.out, name))
    with CloSession(timeout=3600) as clo:
        r = clo.run(__file__, {"zprj": os.path.abspath(a.zprj), "obj": obj, "block": a.block,
                               "threshold": a.threshold, "cap": a.cap})

    print("%-6s %10s  %s" % ("steps", "mean mm", "group that moved most"))
    for b in r["blocks"]:
        print("%-6d %10.3f  %s (%.3f mm)" % (b["steps"], b["meanMoveMm"], b["worstGroup"],
                                             b["worstGroupMoveMm"]))
    print("\n%d steps, %s, solver quality %s, %d groups, mesh at %s"
          % (r["steps"], "settled" if r["settled"] else "NOT settled - reached the cap",
             r["simulationQuality"], r["groups"], r["obj"]))
    last = r["blocks"][-1] if r["blocks"] else None
    if r["settled"] and last["worstGroupMoveMm"] >= a.threshold:
        print("The garment's mean is below the threshold but %s still moved %.3f mm in the last "
              "block. Look at that piece before trusting a measurement on it."
              % (last["worstGroup"], last["worstGroupMoveMm"]))
