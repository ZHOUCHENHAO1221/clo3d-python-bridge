# -*- coding: utf-8 -*-
"""Finding and driving CLO's built-in Python editor through Windows accessibility.

This is the part with no alternative. CLO Standalone ships a Python API but exposes no headless
mode and no command-line entry point for it: the only supported way to execute a script is
Edit > Python Script, paste, press Play. So "automating CLO" means automating that window.

Two details make the difference between a script that works once and one that works next month:

* Match control ids by SUFFIX, not by full path. CLO's auto_id is the whole widget hierarchy,
  e.g. "MVSingleApplication.MVDialog.CodeEditor.QSplitter.textEditorFrame.QCodeEditor". The
  prefix is layout and changes between builds; the tail ("QCodeEditor", "playButton") is the
  widget and has been stable. Pinning the full string makes the bridge break on upgrade for no
  reason.

* Several CLO top-level windows carry an "Edit" menu and only one of them owns "Python Script".
  Failing on the first one means try the next, not give up.

pywinauto is imported lazily so the rest of the package imports on any machine, including the
one running the tests.
"""
import time

# The editor and Play button, identified by the tail of their auto_id.
EDIT_SUFFIX = "QCodeEditor"
PLAY_SUFFIX = "playButton"
# CLO's main window title varies by edition and sign-in mode ("CLO Standalone OnlineAuth",
# "CLO Standalone", ...). Match the family, not one spelling.
WINDOW_PREFIX = "CLO"


class Editor(object):
    """Minimal surface the session needs. Swap it out in tests."""

    def read(self):
        raise NotImplementedError

    def write(self, text):
        raise NotImplementedError

    def play(self):
        raise NotImplementedError


class UiaEditor(Editor):
    """The real one, backed by pywinauto's UIA backend."""

    def __init__(self, window, edit, play):
        self._window = window
        self._edit = edit
        self._play = play

    def read(self):
        return self._edit.window_text()

    def write(self, text):
        self._window.set_focus()
        self._edit.set_edit_text(text)

    def play(self):
        self._play.click_input()


def _endswith(control, suffix):
    try:
        return str(control.element_info.automation_id).endswith(suffix)
    except Exception:
        return False


def _editor_in(window):
    """Return (edit, play) inside an open Python Script dialog, or None."""
    edit = play = None
    for child in window.descendants():
        if edit is None and _endswith(child, EDIT_SUFFIX):
            edit = child
        elif play is None and _endswith(child, PLAY_SUFFIX):
            play = child
        if edit is not None and play is not None:
            return edit, play
    return None


def _clo_windows():
    from pywinauto import Desktop
    win32 = Desktop(backend="win32")
    uia = Desktop(backend="uia")
    for window in win32.windows():
        try:
            if not window.window_text().startswith(WINDOW_PREFIX) or not window.is_visible():
                continue
            yield uia.window(handle=window.handle)
        except Exception:
            continue


def find_editor(open_if_closed=True, settle=0.5):
    """Locate the Python editor, opening it through CLO's own menu if needed.

    Returns a UiaEditor, or None when no CLO window has one. Opening the editor is a menu click
    in CLO's UI - it changes nothing in the user's document and saves nothing.
    """
    for window in _clo_windows():
        found = _editor_in(window)
        if found:
            return UiaEditor(window, *found)

    if not open_if_closed:
        return None

    # Importing a .zprj closes the editor dialog, which is the usual reason it is missing
    # mid-session. Reopen it the way a person would.
    for window in _clo_windows():
        try:
            menu = window.child_window(title="Edit", control_type="MenuItem")
            if not menu.exists(timeout=0.2):
                continue
            window.set_focus()
            menu.click_input()
            item = window.child_window(title="Python Script", control_type="MenuItem")
            if not item.exists(timeout=0.5):
                continue
            item.click_input()
            time.sleep(settle)
        except Exception:
            continue
        found = _editor_in(window)
        if found:
            return UiaEditor(window, *found)
    return None
