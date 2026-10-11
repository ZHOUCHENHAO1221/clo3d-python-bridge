"""Exceptions raised by the bridge.

They are separate types because the caller's response to each one differs: a CloNotFound means
"open CLO", a CloEditorBusy means "a human has unsaved work in the editor, do not touch it", and
a CloTimeout means "the worker may still be running inside CLO" - which is not the same as
failure and must not be retried blindly.
"""


class CloError(Exception):
    """Base class for every error this package raises."""


class CloNotFound(CloError):
    """No CLO window with a reachable Python editor was found."""


class CloEditorBusy(CloError):
    """The Python editor holds a script this package did not put there.

    Overwriting it would destroy a user's unsaved work, so the bridge refuses.
    """


class CloTimeout(CloError):
    """No result file appeared in time.

    The worker may still be running inside CLO. `stage` carries the last heartbeat the worker
    wrote, which is usually enough to say how far it got.
    """

    def __init__(self, message, stage=None, elapsed=None):
        super().__init__(message)
        self.stage = stage
        self.elapsed = elapsed


class CloWorkerError(CloError):
    """The worker ran and reported a failure. `traceback` is the worker's own traceback."""

    def __init__(self, message, traceback=None):
        super().__init__(message)
        self.traceback = traceback
