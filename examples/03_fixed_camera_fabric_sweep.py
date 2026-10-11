# -*- coding: utf-8 -*-
"""Render the same garment under several fabrics from one fixed camera.

    python examples/03_fixed_camera_fabric_sweep.py fabrics.json out/

where fabrics.json is {"label": "<CLO fabric JSON or .zfab path>", ...}.

⚠️  NOT VERIFIED AGAINST A RUNNING CLO.
    Names are probed; argument order is not. See examples/02 for the full caveat.

Why this example and not a prettier one: a fabric comparison is only readable if the camera
does not move between shots. If it does, every difference you see is part lens and part cloth
and you cannot separate them afterwards. So the camera is captured once, up front, and restored
before every single snapshot - including the first, so that the baseline is taken through the
same path as the rest.

Note also what is *not* here: CLO exposes no individual setters for weight, thickness, bending
or stretch. Physical properties go in as a whole fabric definition via `ChangeFabricWithJsonW`.
Hunting for a `SetBendingStiffness` will waste an afternoon; there isn't one.
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def main(payload):
    """Runs inside CLO."""
    from clo_bridge.api import changed, require
    from clo_bridge.worker import beat

    fabrics = payload["fabrics"]
    out_dir = payload["out_dir"]
    os.makedirs(out_dir, exist_ok=True)

    utility = require("utility_api", "GetViewPoint", "SetViewPoint", "Simulate")
    fabric_api = require("fabric_api", "ChangeFabricWithJsonW")
    exporter = require("export_api", "ExportCustomViewSnapshotW")

    camera = utility.GetViewPoint()        # captured once; every shot is taken from here
    shots = {}
    digests = {}

    for label, definition in sorted(fabrics.items()):
        beat("applying %s" % label)
        fabric_api.ChangeFabricWithJsonW(definition)

        beat("simulating %s" % label)
        utility.Simulate()

        utility.SetViewPoint(camera)
        path = os.path.join(out_dir, "%s.png" % label)
        exporter.ExportCustomViewSnapshotW(path)
        if not os.path.isfile(path):
            raise RuntimeError("no snapshot was written for %s at %s" % (label, path))

        digests[label] = hashlib.sha256(open(path, "rb").read()).hexdigest()
        shots[label] = path

    # Two similar fabrics may legitimately render almost alike, so a per-pair check would cry
    # wolf. A whole sweep landing on one byte-identical image cannot be the cloth: it means the
    # fabric never reached the garment and every simulation re-ran the same inputs.
    # See reference/PITFALLS.md, "You changed a parameter and the simulation did not change".
    if len(fabrics) > 1:
        unique = set(digests.values())
        changed(1, len(unique), "number of distinct renders across %d fabrics" % len(fabrics))

    return {"camera": list(camera) if hasattr(camera, "__iter__") else camera,
            "shots": shots, "sha256": digests}


if "CLO_JOB_DIR" in globals():
    from clo_bridge.worker import run
    run(main)
elif __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("usage: 03_fixed_camera_fabric_sweep.py fabrics.json out/")
    with open(sys.argv[1], encoding="utf-8") as fh:
        fabrics = json.load(fh)
    from clo_bridge import CloSession
    with CloSession(timeout=1800) as clo:          # a sweep is several simulations
        result = clo.run(__file__, {"fabrics": fabrics,
                                    "out_dir": os.path.abspath(sys.argv[2])})
    for label, path in sorted(result["shots"].items()):
        print("%-20s %s" % (label, path))
