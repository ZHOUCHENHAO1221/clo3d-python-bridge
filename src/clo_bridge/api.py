# -*- coding: utf-8 -*-
"""Small helpers for worker scripts. Import these inside CLO, not on the host.

The point of `require` is honesty about what a script actually depends on. CLO's API surface
differs between builds, and a worker that calls a function which does not exist on this install
should say which function and which module - not die with an AttributeError three frames deep
in somebody's recipe.
"""
from .errors import CloError


class CloApiMissing(CloError):
    """A function this worker needs is not present on this build of CLO."""


def require(module, *names):
    """Import `module` and assert it exposes `names`. Returns the module.

        fabric_api = require("fabric_api", "AddFabric", "AssignFabricToPattern")

    Call it at the top of a worker so a missing function is reported before anything has been
    changed in the user's document, rather than halfway through.
    """
    try:
        mod = __import__(module)
    except ImportError as exc:
        raise CloApiMissing(
            "%s is not importable. This script must run inside CLO, launched by "
            "clo_bridge.CloSession." % module) from exc
    missing = [n for n in names if not hasattr(mod, n)]
    if missing:
        raise CloApiMissing(
            "%s on this build of CLO has no %s. Regenerate the API map with "
            "scripts/probe_api.py and check reference/API_MAP.md for the current spelling."
            % (module, ", ".join(missing)))
    return mod


def changed(before, after, label="output"):
    """Assert that an operation actually changed something, and say so if it did not.

    See reference/PITFALLS.md, "You changed a parameter and the simulation did not change".
    "The job ran" and "the parameter took effect" are different claims; only the second one is
    worth reporting. Pass anything comparable - a measurement, a vertex count, a file hash.
    """
    if before == after:
        raise CloError(
            "%s is identical before and after. The operation ran, but it changed nothing - "
            "the usual cause is that it was applied to a different piece than the one being "
            "measured. Do not record this as a result." % label)
    return after
