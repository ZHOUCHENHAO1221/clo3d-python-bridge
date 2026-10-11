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

MODULES = ["utility_api", "pattern_api", "fabric_api", "import_api", "export_api",
           "rest_api", "ApiTypes"]
# rest_api was missed on the first pass, and the map then reported its eight functions as
# "documented but absent from your build" - a wrong answer produced by not looking.


def probe(_payload):
    """Runs inside CLO.

    The API is a pybind11 binding, so every callable carries its full signature - overloads
    included - in __doc__. That is the only place signatures exist: inspect.signature() raises
    on these builtins and CLO publishes no machine-readable reference. Capturing the docstring
    turns the map from a list of names into something you can call from.
    """
    from clo_bridge.worker import beat
    out = {"modules": {}}
    for name in MODULES:
        beat("importing " + name)
        try:
            module = __import__(name)
            entries = {}
            for n in dir(module):
                # "~Name" entries are C++ destructors that leak through the binding.
                if n.startswith("_") or n.startswith("~"):
                    continue
                doc = ""
                try:
                    attr = getattr(module, n)
                    if callable(attr):
                        doc = (getattr(attr, "__doc__", None) or "").strip()
                except Exception:
                    pass
                entries[n] = doc
            out["modules"][name] = entries
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
    # The pattern count is a connectivity check, not reference data - it says the probe reached
    # a real document. It is reported to the caller and deliberately not written to the file,
    # which describes an API and has no business carrying anyone's scene state.
    try:
        import pattern_api
        out["_patternCount"] = pattern_api.GetPatternCount()
    except Exception as exc:
        out["_sceneError"] = str(exc)
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
    scene = surface.pop("_patternCount", None)
    surface.pop("_sceneError", None)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(surface, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("CLO %s  (reached a document with %s patterns)" % (surface.get("version"), scene))
    for name, entries in surface["modules"].items():
        if not isinstance(entries, dict) or "error" in entries:
            print("  %-14s ERROR" % name)
            continue
        signed = sum(1 for d in entries.values() if d)
        print("  %-14s %4d  (%d with a signature)" % (name, len(entries), signed))
    print("written: %s" % target)
