# -*- coding: utf-8 -*-
"""Drive CLO Standalone's Python API from an ordinary Python process.

CLO exposes a large Python API (800+ functions across five modules) but no headless mode and no
command-line entry point for it. The only supported way to run a script is to paste it into
Edit > Python Script and press Play. This package automates that window, and - more
importantly - gives the two halves a contract that survives the ways CLO's UI lies to you.

    from clo_bridge import CloSession
    with CloSession() as clo:
        print(clo.run("examples/01_hello_clo.py"))

See reference/PITFALLS.md before writing your own worker.
"""
from .errors import (CloEditorBusy, CloError, CloNotFound, CloTimeout,
                     CloWorkerError)
from .session import CloSession

__all__ = ["CloSession", "CloError", "CloNotFound", "CloEditorBusy",
           "CloTimeout", "CloWorkerError"]
__version__ = "0.1.0"
