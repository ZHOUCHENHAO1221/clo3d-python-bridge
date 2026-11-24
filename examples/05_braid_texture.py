# -*- coding: utf-8 -*-
"""Draw a seamless 45° braid texture in numpy, then put it on a fabric in every colorway.

    python examples/05_braid_texture.py "Mesh" [-o braid_texture/]

The second argument is matched against fabric names; every fabric whose name contains it gets
the maps. Needs numpy and Pillow on the host side; nothing extra inside CLO.

The texture is a 2/2 biaxial braid: two sets of strands at +45° and -45°, each passing over two
and under two. It is drawn as a height field, and the colour and normal maps both come from it:

- **Coordinates.** `u = x + y` and `v = x - y` run along the two strand directions, so a strand
  is just a band of constant `floor(u / w)`. Which set is on top at a crossing is
  `((i + j) // 2) % 2`, which makes it 2/2. Use `% 2` alone for a plain weave.
- **Strand shape.** A round cross-section, `sqrt(1 - t^2)`, narrowed so a gap shows between
  strands. The top strand dips towards where it goes under, and a fine cosine along the strand
  reads as fibre.
- **Seamless.** The pattern repeats every 4 strand widths along u and v, so `N / STRANDS` must be
  a multiple of 4 for the tile edges to meet.
- **Normals from a wrapped gradient.** `np.gradient` on the raw height map gets the edge pixels
  wrong, which shows as a line at every tile seam. Pad with `mode="wrap"`, take the gradient,
  crop. Green points up (OpenGL), which is what CLO reads.
- **Grey base colour.** CLO multiplies the base map by the fabric's colour, so one grey map
  serves every colorway; the colour stays a fabric setting.

The maps go on with `SetBaseTextureMapImageGivenFilePathW` and `SetNormalMapImageGivenFilePathW`,
once per colorway (reference/PITFALLS.md). Thickness is read before and after and printed:
`SetMaterialProperties` is known to zero it, and these two calls are checked the same way here.
Texture calls used on CLO 2026.1.382.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

N = 1024           # tile size in px
STRANDS = 16       # strands per direction per tile


def main(payload):
    """Runs inside CLO."""
    from clo_bridge.api import require
    from clo_bridge.worker import beat

    u = require("utility_api", "GetColorwayCount")
    f = require("fabric_api", "GetFabricCount", "GetFabricNameW", "GetFabricInformationW",
                "SetBaseTextureMapImageGivenFilePathW", "SetNormalMapImageGivenFilePathW")
    hits = [i for i in range(f.GetFabricCount()) if payload["match"] in f.GetFabricNameW(i)]
    if not hits:
        raise RuntimeError("no fabric name contains %r" % payload["match"])

    out = []
    for i in hits:
        before = dict(f.GetFabricInformationW(i)).get("Thickness")
        for cw in range(u.GetColorwayCount()):
            beat("fabric %d colorway %d" % (i, cw))
            f.SetBaseTextureMapImageGivenFilePathW(payload["base"], cw, i)
            f.SetNormalMapImageGivenFilePathW(payload["normal"], cw, i)
        after = dict(f.GetFabricInformationW(i)).get("Thickness")
        out.append({"index": i, "name": f.GetFabricNameW(i), "thickness": [before, after]})
    return {"colorways": u.GetColorwayCount(), "fabrics": out}


def draw(out_dir):
    """Runs on the host. Writes the base and normal maps, returns their paths."""
    import numpy as np
    from PIL import Image

    assert (N // STRANDS) % 4 == 0, "N / STRANDS must be a multiple of 4 to tile"
    w = N / STRANDS
    ys, xs = np.mgrid[0:N, 0:N].astype(float)
    u, v = xs + ys, xs - ys
    i, j = np.floor(u / w), np.floor(v / w)
    fu, fv = u / w - i, v / w - j
    a_top = ((i + j) // 2) % 2 == 0
    prof = lambda t: np.sqrt(np.clip(1 - ((2 * t - 1) / 0.88) ** 2, 0, 1))
    pa, pb = prof(fu), prof(fv)
    top = np.where(a_top,
                   pa * (0.75 + 0.25 * np.cos(2 * np.pi * (fv - 0.5))) * (0.92 + 0.08 * np.cos(18 * np.pi * fu)),
                   pb * (0.75 + 0.25 * np.cos(2 * np.pi * (fu - 0.5))) * (0.92 + 0.08 * np.cos(18 * np.pi * fv)))
    h = np.maximum(top, np.where(a_top, pb, pa) * 0.45)

    gy, gx = np.gradient(np.pad(h, 2, mode="wrap"))
    gx, gy = gx[2:-2, 2:-2] * -6.0, gy[2:-2, 2:-2] * -6.0
    n = np.stack([gx, -gy, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)

    os.makedirs(out_dir, exist_ok=True)
    base, normal = os.path.join(out_dir, "braid_base.png"), os.path.join(out_dir, "braid_normal.png")
    Image.fromarray((110 + 120 * h).clip(0, 255).astype(np.uint8)).save(base)
    Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8)).save(normal)
    return base, normal


if "CLO_JOB_DIR" in globals():
    from clo_bridge.worker import run
    run(main)
elif __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit('usage: 05_braid_texture.py "<part of fabric name>" [-o out_dir]')
    out_dir = sys.argv[sys.argv.index("-o") + 1] if "-o" in sys.argv else "braid_texture"
    base, normal = draw(os.path.abspath(out_dir))
    from clo_bridge import CloSession
    with CloSession() as clo:
        r = clo.run(__file__, {"match": sys.argv[1], "base": base, "normal": normal})
    print("%d colorways" % r["colorways"])
    for fab in r["fabrics"]:
        print("  [%d] %-28s thickness %s -> %s" % (fab["index"], fab["name"], *fab["thickness"]))
