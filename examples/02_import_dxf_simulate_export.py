# -*- coding: utf-8 -*-
"""Import a DXF pattern, simulate it, export the result as OBJ.

    python examples/02_import_dxf_simulate_export.py path/to/pattern.dxf out/

Signatures used here, read off CLO 2026.1.310 and listed in reference/API_MAP.md:

    ImportDXFW(arg0: str, arg1: Marvelous::ImportDxfOption) -> bool
    Simulate(arg0: int) -> bool
    ExportOBJW(arg0: str, arg1: Marvelous::ImportExportOption) -> List[str]

Note what the signatures save you. `ImportDXFW` wants an options object as well as a path and
`Simulate` wants an integer, so the obvious call fails on both - with an error that does not
say why.

The options object matters for a second reason, and it is the one that will cost you an
afternoon. `export_api` also offers `ExportOBJ(path)`, which is shorter and looks equivalent.
It is not: with no options to work from, CLO opens its Export OBJ dialog and waits for a
person. The worker then sits inside the call for ever. **Prefer the overload that takes an
options object.** Supplying one is how you answer the dialog in advance.

What is worth copying besides the calls:

  * every call is name-checked up front, so a mismatch is reported before the document is
    touched rather than halfway through
  * the pattern count is read after the import, because "the import returned True" and "the
    scene now holds pieces" are different claims. Note the check is not `after > before`:
    importing a DXF REPLACES the pattern set rather than adding to it
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
    types = require("ApiTypes", "ImportDxfOption", "ImportExportOption")

    before = pattern.GetPatternCount()

    beat("importing %s" % os.path.basename(dxf))
    ok = importer.ImportDXFW(dxf, types.ImportDxfOption())
    after = pattern.GetPatternCount()
    # The import REPLACES the pattern set, it does not append to it. Measured: two files of
    # three pieces each, imported one after the other, leave three pieces and not six. So the
    # check is "there are pieces now", not "there are more than there were" - and a loop that
    # imports several DXFs expecting to accumulate them keeps only the last one.
    if not ok or after < 1:
        raise RuntimeError(
            "ImportDXFW returned %r and the scene holds %d patterns (%d before). The file may "
            "be empty, in unexpected units, or on a layer CLO skips." % (ok, after, before))

    beat("simulating")
    utility.Simulate(payload.get("steps", 30))

    obj = os.path.join(out_dir, os.path.splitext(os.path.basename(dxf))[0] + ".obj")
    beat("exporting")
    # The options object is what keeps this headless. ExportOBJ(obj) would open a dialog.
    written = exporter.ExportOBJW(obj, types.ImportExportOption())
    if not os.path.isfile(obj):
        raise RuntimeError("ExportOBJW returned %r but wrote no file at %s" % (written, obj))

    return {"patterns": after, "obj": obj, "bytes": os.path.getsize(obj),
            "wrote": list(written) if written else []}


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
    print("%d patterns in the scene after the import" % result["patterns"])
    print("%s  (%d bytes)" % (result["obj"], result["bytes"]))
