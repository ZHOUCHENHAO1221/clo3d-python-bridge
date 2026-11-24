# -*- coding: utf-8 -*-
"""Group the pieces of the open project into garments by shared seams, with each piece's outline.

    python examples/07_garment_scope.py [-o scope.json]

A project often holds more than one garment - a top and a bottom on one avatar, a lining sewn to
a shell. Before re-fabricking or measuring "the garment", decide which pieces it is. This joins
two pieces whenever they share a seam, so every group is a set of pieces sewn to each other.
That is a candidate, not a recognised garment: a detached lining or belt is its own group, and two
garments sewn together are one. Look at the groups before using them.

Outlines are read with the fallback order in reference/PITFALLS.md, because no one call has
worked on every build: GetPatternOutlinePoints, then ExportPatternJSON (written to the job
directory), then the lines of GetPatternLineInfo. Each piece records which source answered, or
"none". The grouping does not need outlines, so a missing one is reported, not fatal.

Where the build has `GetPatternGroupsBySeamlineConnectivity` (not in CLO's published list), its
groups are compared with the ones computed here and the result is reported.

Read-only. It changes nothing in the document and saves nothing; the only file it writes is the
pattern JSON in its own job directory. Adapted from code run on CLO 2025.2.368 and 2026.1.382;
not re-run as packaged.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def line_info_outline(pattern, i):
    """Outline points from GetPatternLineInfo: each line's start and end, in line order."""
    try:
        info = json.loads(pattern.GetPatternLineInfo(i))
    except Exception:
        return []
    points = []
    for line in sorted(info.get("lines") or [], key=lambda l: l.get("lineIndex", 0)):
        for key in ("start", "end"):
            q = line.get(key)
            if isinstance(q, dict) and "x" in q and "y" in q:
                p = [float(q["x"]), float(q["y"])]
                if not points or points[-1] != p:
                    points.append(p)
    return points


def seam_groups(seams):
    """Union pieces that share a seam id. `seams` is {piece: [seam ids]}. Returns sorted groups."""
    parent = {i: i for i in seams}

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first = {}
    for i, ids in seams.items():
        for s in ids:
            if s in first:
                parent[root(i)] = root(first[s])
            else:
                first[s] = i
    groups = {}
    for i in seams:
        groups.setdefault(root(i), []).append(i)
    return sorted(sorted(g) for g in groups.values())


def main(_payload):
    """Runs inside CLO."""
    from clo_bridge.api import require
    from clo_bridge.worker import beat, job_dir

    pattern = require("pattern_api", "GetPatternCount", "GetPatternPieceName",
                      "GetSeamlinePairGroupListInPattern")
    count = pattern.GetPatternCount()
    if count < 1:
        raise RuntimeError("the open project has no pattern pieces")

    beat("reading %d pieces" % count)
    pieces = []
    reader = getattr(pattern, "GetPatternOutlinePoints", None)
    for i in range(count):
        outline = [list(p) for p in reader(i)] if callable(reader) else []
        pieces.append({"index": i, "name": pattern.GetPatternPieceName(i),
                       "seams": sorted(set(pattern.GetSeamlinePairGroupListInPattern(i))),
                       "outline": outline,
                       "outlineSource": "GetPatternOutlinePoints" if outline else None})

    missing = [p for p in pieces if not p["outline"]]
    if missing and callable(getattr(pattern, "ExportPatternJSON", None)):
        beat("ExportPatternJSON")
        path = os.path.join(job_dir(), "patterns.json")
        exported = None
        if pattern.ExportPatternJSON(path) and os.path.isfile(path):
            with open(path, encoding="utf-8-sig") as fh:
                exported = json.load(fh).get("PatternList")
        # Use the file only if it describes the same pieces in the same order.
        if exported and len(exported) == count and all(
                p["name"] == e.get("Name") for p, e in zip(pieces, exported)):
            for p in missing:
                try:
                    p["outline"] = [[q["Position"]["x"], q["Position"]["y"]]
                                    for line in exported[p["index"]]["ShapeInfo"]["LineList"]
                                    for q in line["PointList"]]
                except (KeyError, TypeError):
                    p["outline"] = []
                p["outlineSource"] = "ExportPatternJSON" if p["outline"] else None

    for p in pieces:
        if not p["outline"] and callable(getattr(pattern, "GetPatternLineInfo", None)):
            p["outline"] = line_info_outline(pattern, p["index"])
            p["outlineSource"] = "GetPatternLineInfo" if p["outline"] else None
        p["outlineSource"] = p["outlineSource"] or "none"

    groups = seam_groups({p["index"]: p["seams"] for p in pieces})
    out = {"pieceCount": count, "groups": groups, "pieces": pieces}

    clo_groups = getattr(pattern, "GetPatternGroupsBySeamlineConnectivity", None)
    if callable(clo_groups):
        try:
            theirs = sorted(sorted(g["patternIndices"])
                            for g in json.loads(clo_groups(False, False))["groups"])
            out["cloGroupsAgree"] = theirs == groups
            out["cloGroups"] = theirs
        except Exception as exc:
            out["cloGroupsAgree"] = "could not read: %s: %s" % (type(exc).__name__, exc)
    return out


if "CLO_JOB_DIR" in globals():
    from clo_bridge.worker import run
    run(main)
elif __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--out", default="garment_scope.json")
    a = ap.parse_args()

    from clo_bridge import CloSession
    with CloSession() as clo:
        scope = clo.run(__file__)
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(scope, fh, ensure_ascii=False, indent=1)

    names = {p["index"]: p["name"] for p in scope["pieces"]}
    print("%d pieces in %d group(s) sewn together" % (scope["pieceCount"], len(scope["groups"])))
    for n, group in enumerate(scope["groups"], 1):
        shown = ", ".join(names[i] for i in group[:6]) + (" ..." if len(group) > 6 else "")
        print("  group %d: %d piece(s)  %s" % (n, len(group), shown))
    sources = {}
    for p in scope["pieces"]:
        sources[p["outlineSource"]] = sources.get(p["outlineSource"], 0) + 1
    print("outlines: %s" % ", ".join("%s %d" % kv for kv in sorted(sources.items())))
    if "cloGroupsAgree" in scope:
        print("CLO's own seam grouping agrees: %s" % scope["cloGroupsAgree"])
    print("written: %s" % a.out)
