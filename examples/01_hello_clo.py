# -*- coding: utf-8 -*-
"""The smallest complete job: ask CLO what it is and what is open.

    python examples/01_hello_clo.py

Read-only. It opens nothing, changes nothing and saves nothing, which makes it the right first
thing to run when you are checking that the bridge reaches your install at all.

Every function used here was confirmed present by scripts/probe_api.py, and none of them takes
an argument, so this example is safe to trust as written. The later examples are not - read
their headers.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def main(_payload):
    """Runs inside CLO."""
    from clo_bridge.api import require
    from clo_bridge.worker import beat

    beat("reading version")
    utility = require("utility_api", "GetMajorVersion", "GetMinorVersion", "GetPatchVersion",
                      "GetProjectNameW")
    pattern = require("pattern_api", "GetPatternCount")

    return {
        "version": "%s.%s.%s" % (utility.GetMajorVersion(),
                                 utility.GetMinorVersion(),
                                 utility.GetPatchVersion()),
        "project": utility.GetProjectNameW(),
        "patternCount": pattern.GetPatternCount(),
    }


if "CLO_JOB_DIR" in globals():
    from clo_bridge.worker import run
    run(main)
elif __name__ == "__main__":
    from clo_bridge import CloSession
    with CloSession() as clo:
        info = clo.run(__file__)
    print("CLO %s" % info["version"])
    print("project: %s" % (info["project"] or "(untitled)"))
    print("patterns: %d" % info["patternCount"])
