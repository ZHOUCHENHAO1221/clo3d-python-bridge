# -*- coding: utf-8 -*-
"""Import a DXF pattern, simulate it, export the result as OBJ.

    python examples/02_import_dxf_simulate_export.py path/to/pattern.dxf out/

⚠️  NOT VERIFIED AGAINST A RUNNING CLO.
    The function *names* come from a live probe and `require()` will tell you immediately if
    your build spells one differently. The *argument order* does not - CLO's `dir()` cannot
    report signatures. Check each call against your CLO's API documentation before relying on
    the numbers that come out. Treat this file as a correct skeleton with unverified limbs.

What is worth copying regardless of the signatures:

  * every call is name-checked up front, so a mismatch is reported before the document is
    touched rather than halfway through
  * the pattern count is compared before and after the import, because "the import ran" and
    "the import brought in pieces" are different claims
  * the export path is returned to the host, so the caller never has to guess where the file
    went
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def main(payload):
    """Runs inside CLO."""
    from clo_bridge.api import require
    from clo_bridge.worker import beat

    dxf = payload["dxf"]
    out_dir = payload["out_dir"]
    os.makedirs(out_dir, exist_ok=True)

    importer = require("import_api", "ImportDXFW")
    pattern = require("pattern_api", "GetPatternCount")
    exporter = require("export_api", "ExportOBJW")
    utility = require("utility_api", "Simulate")

    before = pattern.GetPatternCount()

    beat("importing %s" % os.path.basename(dxf))
    importer.ImportDXFW(dxf)
    after = pattern.GetPatternCount()
    if after <= before:
        raise RuntimeError(
            "ImportDXFW returned without adding patterns (%d before, %d after). The file may "
            "be empty, in unexpected units, or on a layer CLO skips." % (before, after))

    beat("simulating")
    utility.Simulate()

    obj = os.path.join(out_dir, os.path.splitext(os.path.basename(dxf))[0] + ".obj")
    beat("exporting")
    exporter.ExportOBJW(obj)
    if not os.path.isfile(obj):
        raise RuntimeError("ExportOBJW reported nothing and wrote no file at %s" % obj)

    return {"patternsAdded": after - before, "obj": obj, "bytes": os.path.getsize(obj)}


if "CLO_JOB_DIR" in globals():
    from clo_bridge.worker import run
    run(main)
elif __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__.strip().splitlines()[2].strip())
    from clo_bridge import CloSession
    with CloSession() as clo:
        result = clo.run(__file__, {"dxf": os.path.abspath(sys.argv[1]),
                                    "out_dir": os.path.abspath(sys.argv[2])})
    print("%d patterns imported" % result["patternsAdded"])
    print("%s  (%d bytes)" % (result["obj"], result["bytes"]))
