# -*- coding: utf-8 -*-
"""Record what this build of CLO actually exposes. Run it through the bridge:

    python scripts/probe_api.py

CLO's published API documentation lags the binary, so the only reliable catalogue is the one
you read out of the interpreter you are going to run against. This writes api_surface.json next
to the script, stamped with the CLO version, and build_api_map.py turns that into a readable
index.

The probe is read-only: it imports modules, calls dir(), and asks for the version and the
pattern count. It does not touch the open document and does not save anything.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

MODULES = ["utility_api", "pattern_api", "fabric_api", "import_api", "export_api", "ApiTypes"]


def probe(_payload):
    """Runs inside CLO."""
    from clo_bridge.worker import beat
    out = {"modules": {}}
    for name in MODULES:
        beat("importing " + name)
        try:
            module = __import__(name)
            out["modules"][name] = sorted(n for n in dir(module) if not n.startswith("_"))
        except Exception as exc:
            out["modules"][name] = {"error": "%s: %s" % (type(exc).__name__, exc)}
    try:
        import utility_api
        out["version"] = "%s.%s.%s" % (utility_api.GetMajorVersion(),
                                       utility_api.GetMinorVersion(),
                                       utility_api.GetPatchVersion())
    except Exception as exc:
        out["version"] = None
        out["versionError"] = str(exc)
    try:
        import pattern_api
        out["patternCount"] = pattern_api.GetPatternCount()
    except Exception as exc:
        out["sceneError"] = str(exc)
    return out


if __name__ == "__main__" and "CLO_JOB_DIR" in globals():
    # inside CLO, launched by the bridge
    from clo_bridge.worker import run
    run(probe)
elif __name__ == "__main__":
    # on the host: drive CLO, then save the answer
    from clo_bridge import CloSession
    with CloSession() as clo:
        surface = clo.run(__file__)
    target = os.path.join(HERE, "api_surface.json")
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(surface, fh, indent=2, ensure_ascii=False)
    counts = {k: (len(v) if isinstance(v, list) else "ERROR")
              for k, v in surface["modules"].items()}
    print("CLO %s" % surface.get("version"))
    for name, n in counts.items():
        print("  %-14s %s" % (name, n))
    print("written: %s" % target)
