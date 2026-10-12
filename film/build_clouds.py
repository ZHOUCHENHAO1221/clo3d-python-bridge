# -*- coding: utf-8 -*-
"""Pack the sweep's exported meshes into one file the film can read.

    python film/build_clouds.py <folder with V1_P06_r1.obj ... V3_P32_r1.obj> <pattern.dxf>

Writes film/assets/clouds.js. Nothing in it is drawn or invented: every point is a vertex CLO
solved, and every hem width is measured here, off the mesh, by clo_bridge.mesh - the same code
the sweep example uses. If a width disagrees with the contact sheet, this script stops.

Within one pattern all seven fabrics share a topology (checked below), which is what lets the
film move vertex i of one fabric to vertex i of the next.

The DXF is the flat pattern the widest garment was simulated from: its cut lines and internal
lines, in millimetres, as CLO wrote them. Needs ezdxf (pip install ezdxf) - the film itself
does not.
"""
import base64
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
from clo_bridge.mesh import loop_span, measure, read_obj  # noqa: E402

PATTERNS = [("V1", "straight"), ("V2", "A-line"), ("V3", "exaggerated A-line")]
FABRICS = [("P06", "cotton poplin"), ("P15", "cotton knit"), ("P24", "poly chiffon"),
           ("P27", "worsted wool"), ("P28", "boiled wool"), ("P31", "coated twill, brown"),
           ("P32", "coated twill, cream")]
# hem widths printed on docs/fabric_sweep_3x7.jpg, mm - the cross-check
SHEET = {"V1": [365, 365, 364, 364, 366, 364, 365], "V2": [401, 375, 372, 391, 382, 408, 423],
         "V3": [492, 441, 432, 476, 502, 491, 489]}
STEP = 0.05          # mm per int16 unit: +-1638 mm of range, far finer than the mesh


def b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode("ascii")


def normals(v, f):
    n = np.zeros_like(v)
    c = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    for k in range(3):
        np.add.at(n, f[:, k], c)
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-9)


def flat_pattern(path):
    """Cut lines (AAMA layer 1) and internal lines (layer 8) of every piece, laid side by side."""
    import ezdxf
    doc = ezdxf.readfile(path)
    pieces = []
    for ins in doc.modelspace().query("INSERT"):
        block, cut, inner = doc.blocks[ins.dxf.name], [], []
        for e in block:
            if e.dxftype() == "POLYLINE" and e.dxf.layer in ("1", "8"):
                pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                (cut if e.dxf.layer == "1" else inner).append(pts)
        if cut and len(cut[0]) > 8:             # the 4-point polyline is the sheet's bounding box
            pieces.append((cut, inner))
    pieces.sort(key=lambda p: min(x for x, _ in p[0][0]))
    out, cursor = [], 0.0
    for cut, inner in pieces:
        xs = [x for pl in cut for x, _ in pl]
        ys = [y for pl in cut for _, y in pl]
        dx, dy = cursor - min(xs), -(min(ys) + max(ys)) / 2
        flat = lambda pl: [round(v, 1) for x, y in pl for v in (x + dx, y + dy)]
        out.append({"cut": [flat(pl) for pl in cut], "inner": [flat(pl) for pl in inner],
                    "width": round(max(xs) - min(xs), 1), "height": round(max(ys) - min(ys), 1)})
        cursor += max(xs) - min(xs) + 90.0      # 90 mm between pieces, for the film only
    shift = (cursor - 90.0) / 2
    for piece in out:
        for key in ("cut", "inner"):
            piece[key] = [[round(v - shift, 1) if i % 2 == 0 else v for i, v in enumerate(pl)] for pl in piece[key]]
        print("pattern piece  %.0f x %.0f mm  %d internal line(s)" % (piece["width"], piece["height"], len(piece["inner"])))
    return out


def main(src, dxf=None):
    out = {"step": STEP, "patterns": [], "flat": flat_pattern(dxf) if dxf else []}
    centre = None
    for pid, pname in PATTERNS:
        faces0, fabrics = None, []
        for j, (fid, fname) in enumerate(FABRICS):
            path = os.path.join(src, "%s_%s_r1.obj" % (pid, fid))
            verts, faces = read_obj(path)
            v = np.array(verts, np.float64)
            tri = np.array([f[:3] for f in faces], np.int64)
            if faces0 is None:
                faces0 = tri
            elif tri.shape != faces0.shape or (tri != faces0).any():
                sys.exit("%s: topology differs from the first fabric of %s" % (path, pid))
            m = measure(path)
            loop = m["lowestClosedLoop"]
            width = loop_span(m)
            if abs(width - SHEET[pid][j]) > 0.6:
                sys.exit("%s: hem %.2f mm here, %d mm on the contact sheet" % (path, width, SHEET[pid][j]))
            if centre is None:          # one origin for all 21, so they share a neckline height
                centre = np.array([0.0, (v[:, 1].min() + v[:, 1].max()) / 2, 0.0])
            q = np.round((v - centre) / STEP)
            if np.abs(q).max() > 32767:
                sys.exit("%s does not fit int16 at %.2f mm" % (path, STEP))
            fabrics.append({
                "id": fid, "name": fname, "hem": round(width, 1),
                "lowest": round(loop["min"], 1), "loop": loop["vertexIds"],
                "pos": b64(q.astype("<i2")),
                "nrm": b64(np.round(normals(v, tri) * 127).astype(np.int8)),
            })
            print("%s %s  %5d vertices  hem %.1f mm (sheet %d)  loop of %d" %
                  (pid, fid, len(v), width, SHEET[pid][j], len(loop["vertexIds"])))
        # every closed boundary loop, lowest first: hem, the two armholes, neck
        loops = [l["vertexIds"] for l in m["boundaryLoops"] if l["closed"]]
        print("%s  %d closed boundary loop(s): %s" % (pid, len(loops), [len(l) for l in loops]))
        out["patterns"].append({"id": pid, "name": pname, "vertices": int(len(v)), "fabrics": fabrics,
                                "loops": loops})

    dest = os.path.join(HERE, "assets", "clouds.js")
    with open(dest + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("/* Generated by film/build_clouds.py from the sweep's exported OBJ files. */\n")
        fh.write("window.CLOUDS = %s;\n" % json.dumps(out, separators=(",", ":")))
    os.replace(dest + ".tmp", dest)
    print("-> %s  %.2f MB" % (dest, os.path.getsize(dest) / 1e6))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else sys.exit(__doc__), sys.argv[2] if len(sys.argv) > 2 else None)
