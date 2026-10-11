# Pitfalls

Every entry starts with the symptom, because that is what you will have. Each one cost real
hours; none of them is in CLO's documentation.

---

## "The job failed" — but CLO did the work fine

**Symptom.** The automation layer raises, or the subprocess returns non-zero, yet the garment in
CLO is visibly updated and the export is on disk.

**Cause.** Qt can invalidate the Python editor's automation handle while CLO is still executing
the script. The host is told the *window interaction* failed. It was never told anything about
the *job*, because CLO's editor reports nothing back to whoever pressed Play.

**Rule.** The only evidence of an outcome is a file the worker itself wrote. This package polls
`result.json` and ignores the click, the control state and any exception from the UI layer. If
you build your own version of this, build it this way or you will ship a tool that reports
failures that did not happen.

```python
# wrong - the click's outcome is not the job's outcome
proc = subprocess.run([...])
if proc.returncode: raise RuntimeError("CLO failed")

# right - ask the worker
result, stage = protocol.wait_for_result(job_dir, timeout=900)
```

---

## The Python editor vanishes mid-session

**Symptom.** The first job runs. After a job that imports a `.zprj`, the editor cannot be found.

**Cause.** `ImportZprj` closes the Python Script dialog.

**Rule.** Reopen it through CLO's own menu (`Edit > Python Script`) rather than failing. One
wrinkle: several CLO top-level windows carry an `Edit` menu and only one of them owns the
`Python Script` item, so a window that does not have it means *try the next window*, not give up.

---

## Your measurement mesh has a mannequin in it

**Symptom.** You export the garment, measure the lowest closed boundary loop, and get a
plausible number that is not the hem. Or a surface check refuses the mesh because the largest
connected piece is only a third of it.

**Cause.** `ImportExportOption()` comes with **`bExportAvatar = True`**. The avatar is exported
along with the garment, and on a top it is the larger surface by far — measured here at 38.7%
of the total for the garment and the rest for the body.

Why that produces a wrong number rather than an obvious error: the avatar's **ankle and neck
openings are closed boundary loops too**, and they sit lower than a hem. "The lowest closed
boundary loop" then finds an ankle. It is a perfect loop. Nothing about it looks wrong.

**Rule.** Configure the options object; do not accept the defaults for a measurement export.

```python
opt = ApiTypes.ImportExportOption()
opt.bExportAvatar = False                        # default True - the mannequin comes too
opt.bSingleObject = True
opt.weldType = ApiTypes.WELD_TYPE.FULLY_WELDED   # panels as one surface, not loose pieces
export_api.ExportOBJW(path, opt)
```

`WELD_TYPE` offers `DEFAULT_WELDED`, `FULLY_WELDED`, `FULLY_UNWELDED` and `SELECTED_WELDED`.
Unwelded panels arrive as separate surfaces, and a measurement that does not notice measures
one panel.

Keep a surface check in front of the measurement anyway — `clo_bridge.mesh.largest_surface`
refuses when the largest connected piece is under 90% of the area, which is what caught this.

---

## Assigning a fabric to a piece is in the wrong module

**Symptom.** `fabric_api.AssignFabricToPattern` has the right name and three unnamed integers.
Called one way it returns `True` and nothing changes; called the other way it returns `False`.

**Cause.** You are in the wrong module. The call that works lives in `pattern_api`:

```python
pattern_api.SetPatternPieceFabricIndex(piece_index, fabric_index)   # -> None
pattern_api.GetPatternPieceFabricIndex(piece_index)                 # -> int
```

Two named integers, and a getter to read it back with. Whatever
`fabric_api.AssignFabricToPattern` is for, this is not it.

**Rule.** When a function whose name fits returns `True` and changes nothing, stop tuning the
arguments and search the other modules for the same idea. `reference/API_MAP.md` groups by task
across modules precisely so this costs a lookup and not an afternoon.

And read it back. The sweep in the README does
`if any(GetPatternPieceFabricIndex(i) != fi for i in range(count)): raise` before it simulates
anything, because a sweep where the fabric silently failed to apply produces twenty-one
identical garments and a table of numbers that all look plausible.

One more: `GetFabricCount()` defaults to `_bCurrentColorway=True` and will not count a fabric
you have just added. Pass `False`.

---

## Looking for the function that sets a fabric's mechanics

**Symptom.** You want to drive the simulation from measured material data and cannot find where
to put the numbers.

**What is established.** Reading every writer in `fabric_api` — all fifty-nine of them, with no
keyword filtering — **none sets bending, stretch or shear.** They set colour, roughness,
metalness, opacity, texture maps, Substance presets, the fabric's name, item number, roll width
and metadata. `ChangeFabricWithJson` looks like the way in and is not: round-trip its JSON
through `GetFabricInfoW` and it has 31 keys, every one of them appearance.

Across the whole API the only functions that set anything mechanical are
`SetZipperStyleWeight`, `SetZipperStyleTapeThickness`, `SetTrimWeight` and
`SetAddlThicknessCollision` — a zipper, a trim, and a solver collision tolerance.

**The one candidate that looks like a way in, and what happened when it was tried.**
`GetFabricInformationW` returns a `Dict[str, str]` containing `Weight` and `Thickness`, and
there is an exact write counterpart:

```
GetFabricInformationW(arg0: int)                      -> Dict[str, str]
SetFabricInformationW(arg0: int, arg1: Dict[str,str]) -> None
```

It carries no mechanical word in its name, so a keyword search for
`weight|thick|bend|stretch|shear` walks straight past it. Tested on CLO 2026.1.310:

| call | result |
|---|---|
| `SetFabricInformationW(0, {…, "SupplierName": "ACME"})` | **`SupplierName` changed** |
| `SetFabricInformationW(0, {…, "Weight": "1200 g/m2"})` | no change |
| `SetFabricInformationW(0, {…, "Weight": "1200"})` | no change |
| `SetFabricInformationW(0, {"Weight": "1200 g/m2"})` | no change |
| `SetFabricInformationW(0, 0, {…, "Weight": "1200 g/m2"})` | no change |
| `ChangeMetaDataValueForFabricW(0, "Weight", "1200 g/m2")` | no change |

The first row is the control and it is what makes the rest mean anything: **the function does
write this dictionary.** `Weight` and `Thickness` are read-only through it. Four call forms,
no error, no change — it returns `None`, so nothing in the call tells you it declined.

That silence is this repository's own trap in its purest form. A script that writes a measured
weight here and carries on would produce a whole study at CLO's default 300 g/m², with every
call having "succeeded".

**How to check this yourself, and why a grep will not do it.** `SetFabricInformation` carries
no mechanical word, so no search for `weight|thick|bend|stretch|shear` can reach it. **A keyword
search cannot establish an absence.** The claim above rests on two things instead: enumerating
every writer in the module and reading them, and testing the one candidate against a control
key that does change. If you want to assert that something is missing, that is the work.

**Rule, as far as it goes.** A `.zfab` file is a route that is known to work: `AddFabricW(path)`
loads one from a script and the values arrive with it — a measured file reading back 0.22 mm
and 135.3 g/m² where CLO's default fabric reads 0.5 mm and 300 g/m². See
`examples/03_load_measured_fabric.py`.

Read the values back and compare, whichever route you take. "The setter returned" and "the
document now holds the fabric I measured" are different claims, and for a function that returns
`None` the first one is not even available.

---

## The job never finishes, and CLO is sitting there with a dialog open

**Symptom.** No result, no error, no heartbeat past one stage. Look at CLO and it is showing a
modal — an Export options panel, or an informational notice — waiting for a person.

**Cause.** Several API calls are not headless. Two kinds:

* **Informational.** `ImportDXFW` on a file that carries seam allowances raises a notice
  explaining Custom mode. The worker is stopped inside the import until someone clicks OK.
  Tick *Don't Show Again* once and that particular one stops.
* **Options panels, and these are the dangerous ones.** The convenient short overload prompts:

  ```
  ExportOBJ(arg0: str) -> List[str]                                  # opens the options dialog
  ExportOBJW(arg0: str, arg1: Marvelous::ImportExportOption)         # does not
  ```

  The options object is not boilerplate — it is how you answer the dialog in advance. Given
  one, CLO has nothing left to ask.

**Rule.** Prefer the overload that takes an options object from `ApiTypes`, even when a shorter
one exists and looks tempting. Construct it, leave the defaults, and set only what you need.
The short form is for someone sitting at the machine.

When a job does hang, `CloTimeout` names the dialog CLO is showing, so the message says "CLO is
waiting for a person" rather than leaving you to guess. The bridge does not click it: that
button might say OK, and it might say Replace.

---

## Every write fails with a bare `COMError`

**Symptom.** The editor is found, the dialog is open, and `set_edit_text` raises
`_ctypes.COMError: (-2146233079, None, (None, None, None, 0, None))` with nothing else to go on.

**Cause.** **Two** controls in that dialog have an `automation_id` ending in `QCodeEditor`:

```
MVSingleApplication.MVDialog.CodeEditor.QSplitter.textEditorFrame.QCodeEditor   <- you type here
MVSingleApplication.MVDialog.CodeEditor.QSplitter.resultFrame.QCodeEditor       <- CLO prints here
```

A search for the tail `QCodeEditor` finds the output pane first. It is read-only, so setting its
value fails — and the error says nothing about which control it was.

**Rule.** Include one frame name in the match (`textEditorFrame.QCodeEditor`). That is still
short enough to survive a CLO update, because the part that changes is the prefix. Match the
control type as well: a container carrying the same id tail is otherwise indistinguishable from
the control itself.

The output pane is worth keeping once you have found it. `CloSession`'s editor exposes it as
`output()`, and it is where CLO's own stdout and tracebacks go.

---

## The Play button is clicked and nothing runs

**Symptom.** Intermittent, and more likely after you have moved the window or changed display
scaling.

**Cause.** A physical click goes to a screen coordinate, and the coordinate was worked out
before the window moved.

**Rule.** Call the accessible action (`invoke()`) instead, and keep `click_input()` only as a
fallback for a build that exposes no Invoke pattern.

---

## It worked last month, it does not work after a CLO update

**Symptom.** The editor control is suddenly not found, though the dialog is plainly open.

**Cause.** CLO's `automation_id` is the entire widget hierarchy, for example
`MVSingleApplication.MVDialog.CodeEditor.QSplitter.textEditorFrame.QCodeEditor`. The prefix is
layout and does change between builds. The tail is the widget and has been stable.

**Rule.** Match the suffix (`QCodeEditor`, `playButton`), never the full string. Also match the
window title by prefix (`CLO`), because the title varies by edition and sign-in mode
(`CLO Standalone`, `CLO Standalone OnlineAuth`, ...).

---

## The second job writes its result where the first job's directory used to be

**Symptom.** Job one succeeds. Job two times out, and nothing is in its directory — but a
`result.json` appeared in a directory that has since been deleted.

**Cause.** CLO's interpreter keeps your modules loaded between runs. Any value a worker module
caches at import time survives into the next job. A cached job directory is the usual casualty.

**Rule.** Workers hold no per-job state at module level. Resolve the job directory on every
call. The same applies to anything else you are tempted to memoise: a file handle, a pattern
index, a "has this been set up yet" flag.

---

## A Windows path inside the injected code silently corrupts

**Symptom.** `FileNotFoundError` for a path that is obviously right, or a path with a tab in it.

**Cause.** `C:\temp\run.py` written raw into a source line becomes `C:<TAB>emp<CR>un.py`.

**Rule.** Embed every path with `repr()` and normalise to forward slashes. The test
`test_loader_embeds_windows_paths_without_escape_damage` exists only to hold this.

---

## Your automation destroyed someone's unsaved script

**Symptom.** A colleague's half-written script is gone from the editor.

**Cause.** The bridge pasted over it.

**Rule.** Before writing, read. If the editor holds anything that is not a loader this package
wrote, refuse and say so. The marker comment on line one exists for exactly this check. For the
same reason, a bridge must never save the user's project: saving is a destructive act performed
on a document you did not author.

---

## A worker dies and the host waits the full timeout for nothing

**Symptom.** 15 minutes of nothing, then a timeout, and the traceback is sitting in CLO's editor
where only a human can see it.

**Rule.** The worker writes `result.json` on *every* path including exceptions, with the
traceback in it. `clo_bridge.worker.run` does this; if you hand-roll a worker, do the same.

And never call `sys.exit()` in a worker. Inside CLO that is an exit of CLO's own interpreter.

---

## A timeout that tells you nothing

**Symptom.** "Timed out after 900s." Was it stuck on import, on simulation, on export?

**Rule.** Call `beat("stage name")` before anything slow. The host keeps the last heartbeat and
reports it with the timeout, which turns "it failed" into "it got as far as simulating, and
simulation is slow for this garment".

---

## You changed a parameter and the simulation did not change

**Symptom.** You set a fabric property, re-simulate, and the shape is identical. You conclude
the property has no effect, or that the solver ignores it.

**Cause, nine times out of ten.** The fabric was never applied to the piece you are looking at.
The simulation genuinely re-ran — it just re-ran the same inputs.

**Rule.** Verify the *output changed*, not that the job ran. Compare the exported geometry or a
rendered pixel diff against the previous state and assert it is non-zero before you believe any
conclusion about the parameter. "The simulation ran" and "the parameter took effect" are
different claims and only the second one is interesting.

---

## Non-ASCII paths or labels fail

**Rule.** Most CLO functions have a `W` twin (`ImportDXFW`, `AddFabricW`, `GetProjectNameW`).
Use the `W` variant for any path, fabric name or annotation that may contain non-ASCII
characters. See `reference/API_MAP.md` — the pairs are listed side by side.

---

## Two jobs at once

CLO's Python editor is a single slot and the GUI blocks while a script runs. There is no
concurrency to be had. Serialise jobs in your own queue; do not try to open a second editor.

---

## There is no headless mode

Worth stating plainly, because it is the question everyone arrives with. CLO Standalone exposes
no headless flag and no command-line entry point for its Python API. Running on a server means
running a full desktop session with CLO signed in, and the licence terms for that are between
you and CLO. This package does not handle credentials, does not automate sign-in, and does not
attempt to bypass anything — it drives the editor of an instance a human has already signed in
to.
