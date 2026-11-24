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

The rebuild can also leave an editor on screen and kill the handle you found earlier. The next
read or write then fails with `Handle N is not a valid window handle`. This was seen on CLO
2026.1.382 (19 November 2026), on the job sent straight after one that imported a project.
`CloSession` now finds the editor again and repeats, up to three times, but only before Play.
A Play that failed may still have started the job, so Play is never repeated.

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
opt.weldType = ApiTypes.WELD_TYPE.FULLY_WELDED   # panels as one surface; absent on 2025.2.368
export_api.ExportOBJW(path, opt)
```

`WELD_TYPE` offers `DEFAULT_WELDED`, `FULLY_WELDED`, `FULLY_UNWELDED` and `SELECTED_WELDED`.
Unwelded panels arrive as separate surfaces, and a measurement that does not notice measures
one panel. On CLO 2025.2.368 the enum does not exist at runtime; see *Code written on 2026.1
fails on CLO 2025.2*.

Keep a surface check in front of the measurement anyway — `clo_bridge.mesh.largest_surface`
refuses when the largest connected piece is under 90% of the area, which is what caught this.

For reference, a freshly constructed `ImportExportOption()` read back in November 2026 (CLO
2026.1, build not recorded) with `bExportAvatar = True`, `bSingleObject = False`,
`weldType = FULLY_UNWELDED` and `bIncludeHiddenObject = False`. None of those is what a
measurement export wants.

The opposite case catches people too. When you do want the avatar, a hidden one is not exported,
even with `bExportAvatar = True`. A project saved with the avatar hidden exported without it on
CLO 2026.1.310 (October 2026) until the worker called `utility_api.SetShowHideAvatar(True)` first.
In another run on the same build `bExportAvatar = True` also brought no avatar, and whether it
was hidden there was not recorded. Show it, export, and check the file for it.

---

## Assigning a fabric to a piece is in the wrong module

**Symptom.** `fabric_api.AssignFabricToPattern` has the right name and three unnamed integers.
Called one way it returns `True` and nothing changes; called the other way it returns `False`.

**Cause.** You are in the wrong module. The call that works lives in `pattern_api`:

```python
pattern_api.SetPatternPieceFabricIndex(piece_index, fabric_index)   # -> None
pattern_api.GetPatternPieceFabricIndex(piece_index)                 # -> int
```

Two named integers, and a getter to read it back with. When this was first found, neither
form of `fabric_api.AssignFabricToPattern` changed the piece; on 2026.1.382 two of its options
do (table below).

**Rule.** When a function whose name fits returns `True` and changes nothing, stop tuning the
arguments and search the other modules for the same idea. `reference/API_MAP.md` groups by task
across modules precisely so this costs a lookup and not an afternoon.

And read it back. The sweep in the README does
`if any(GetPatternPieceFabricIndex(i) != fi for i in range(count)): raise` before it simulates
anything, because a sweep where the fabric silently failed to apply produces twenty-one
identical garments and a table of numbers that all look plausible.

Read it back with `GetPatternPieceFabricIndex`, not `fabric_api.GetFabricIndexForPattern`. In
one test (9 September 2026, build not recorded) every value `GetFabricIndexForPattern` returned
changed after an `AddFabric`, while a separate `ExportPatternJSON` showed the pieces still on
their old fabric.

One more: `GetFabricCount()` defaults to `_bCurrentColorway=True` and will not count a fabric
you have just added. Pass `False`.

**Measured on CLO 2026.1.382 (19 November 2026)**, with each call read back
(`examples/probe_assign_options_1119.py`):

| Call | Returns | Time | Fabric changed |
|---|---|---|---|
| `AssignFabricToPattern(fabric, piece, 0)` | `False` | 0.1 ms | no |
| `AssignFabricToPattern(fabric, piece, 1)` | `True` | 0.43 s | yes |
| `AssignFabricToPattern(fabric, piece, 2)` | `True` | 0.46 s | yes |
| `AssignFabricToPattern(0, fabric, piece, 0)` | `False` | 0.2 ms | no |
| `AssignFabricToPattern(0, fabric, piece, 1)` | `True` | 0.37 s | **no** |
| `SetPatternPieceFabricIndex(piece, fabric)` | `None` | 0.50–0.56 s | yes |

So on this build the three-argument call with option 1 or 2 does work, and the four-argument
call is the one that returns `True` and changes nothing. None of them is faster in a way that
matters: on this garment every call that takes effect costs about half a second per piece,
freezing or hiding the piece does not change that, and repeating the call on the same piece does
not get cheaper. A 41-piece garment takes about 23 s to re-fabric.

The cost per piece also grows with the project. On a 102-piece project of about 80 MB, 61 calls
to `SetPatternPieceFabricIndex` took 144.4 s, about 2.4 s each, with the other 41 pieces hidden
and frozen (13 September 2026, build not recorded). Opening that project took 12.3 s, so the
assignment was most of the job. Budget for it; there is no bulk path. The rule above stands
either way: read the assignment back.

---

## Looking for the function that sets a fabric's mechanics

**Symptom.** You want to drive the simulation from measured material data and cannot find where
to put the numbers.

**What is established.** Reading every writer in `fabric_api` — all fifty-nine of them, with no
keyword filtering — **none sets bending, stretch or shear one property at a time.** They set
colour, roughness, metalness, opacity, texture maps, Substance presets, the fabric's name, item
number, roll width and metadata. Across the whole API the only setters with weight or thickness
in their names are `SetZipperStyleWeight`, `SetZipperStyleTapeThickness`, `SetTrimWeight` and
`SetAddlThicknessCollision` — a zipper, a trim, and a solver collision tolerance.

**The way in is the fabric file.** An earlier version of this page said `ChangeFabricWithJson`
was not a way in. That was wrong, and the mistake is instructive: the 31 appearance keys it
cited come from `GetFabricInfoW`, a summary, and were taken for the JSON that
`ChangeFabricWithJson` reads. The file it reads is a `.jfab`, which `ExportFabricW(path, index)`
writes. Its `mapPhysical` block holds density, thickness, stretch, bending, shear and buckling.

Tested on CLO 2026.1.310, on the default fabric of an empty project. The file was exported,
edited as text, loaded through `ChangeFabricWithJsonW` and again through `AddFabricW`, and read
back through `GetFabricInformationW` and a fresh export:

| field edited in the `.jfab` | read back after loading |
|---|---|
| `fDensity`, `fThickness` | as written — `GetFabricInformationW` went from `300 g/m2`, `0.5 mm` to `135.3 g/m2`, `0.22 mm` |
| `fSuK`, `fSvK` (stretch) | as written |
| `fBuK_v2`, `fBvK_v2` (bending), `fLeftShearK_v2`, `fRightShearK_v2` (shear) | as written, and `fBuK`, `fBvK`, `fLeftShearK` moved with them |
| `fBuK`, `fBvK` edited directly | **the call returned `True` and nothing changed** |
| the unedited file, reloaded first | nothing changed — the control |

**The trap inside the route that works.** Bending has two sets of fields. `fBuK` is `fBuK_v2`
divided by π, and CLO recomputes it on load. Edit `fBuK` alone and the call returns `True`, the
file is accepted, and the fabric is unchanged. Edit the `_v2` fields.

**Reading the exported file.** A `.jfab` that `ExportFabric` writes can contain `nan.0` in a
field nothing uses (seen in a texture `graph` block), and `json.loads` rejects it. Replace it
before parsing: `json.loads(re.sub(r'(?<![\w.])-?nan\.0', 'null', text))`.

**Which fabrics it exports.** CLO's library presets are `.zfab` files under CLO's `Assets/Fabric`
folder, and `AddFabric(path)` loads one like any other fabric, with no menu involved. But
`ExportFabricW(path, index)` to a `.jfab` path wrote no file in any of 14 runs, covering six
presets loaded that way (CLO 2026.1.310, October 2026). The call did not raise, so check that the
file exists before reading it. The three-argument overload, `ExportFabricW(path, colorway,
fabric)` with a `.zfab` path, writes a `.zfab` that carries the fabric's texture maps (October
2026, build not recorded).

**What this does not show.** The values were read back from the fabric record. No simulation
was run on them. They are solver units — `fDensity` in g/mm², bending and shear as engine
coefficients — so a measured figure still has to be converted before it goes in.

**The candidate that looks like a way in and is not.**
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

**Rule, as far as it goes.** A `.zfab` file is a route that is known to work, as is an edited `.jfab`: `AddFabricW(path)`
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
  one, CLO has nothing left to ask. `ExportDXF` is the same: `ExportDXF(path)` opened the export
  dialog, and `ExportDXF(path, ApiTypes.ExportDxfOption())` did not (September 2026, build not
  recorded).

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

Play can also reach CLO twice. A tool built the same way saw two runs of one job overlap, and
their writes to the same report file collided with `WinError 5`. Here it can happen when Invoke
fails after it has started the job and the fallback click starts it again. `worker.run` now
claims the job directory before it calls `main`, and a second run of the same job does nothing.

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

## Code written on 2026.1 fails on CLO 2025.2

**Symptom.** On CLO 2025.2 a worker stops with `module 'ApiTypes' has no attribute 'WELD_TYPE'`.
Or the bridge says no editor was found while the Python Script window is plainly open.

**Cause.** Measured on CLO 2025.2.368 in September 2026, on one machine:

- `ApiTypes.WELD_TYPE` is not registered at runtime, although the installed stub file declares
  `ImportExportOption.weldType` with that type. Reading `option.weldType` raises
  `TypeError: Unable to convert function return value to a Python type`, and assigning `2`, the
  documented value of `FULLY_WELDED`, is rejected. So that build cannot be asked for a welded
  export from Python. On 2026.1.224 (28 September 2026) the same option was assigned and read
  back.
- Both `QCodeEditor` controls in the Python Script window have an empty `automation_id`. Only
  their parent frames, `textEditorFrame` and `resultFrame`, tell them apart. The Play button still
  carries `CodeEditor.menubarFrame.playButton`.
- The same editor is reached twice: once through its own top-level window and once through the
  main window, with the same UIA `RuntimeId`. Both windows are titled `CLO Standalone OnlineAuth`.
  Count editors by `RuntimeId`, not by how many times you found one.
- The `Edit > Python Script` menu item has the automation id `CLO.action_Python_Script_CLO`.

**Rule.** If a worker has to run on more than one build, look the enum up with
`getattr(ApiTypes, "WELD_TYPE", None)` and treat a missing one as "this build cannot weld on
export". Do not pass an integer instead. An unwelded export reaches
`clo_bridge.mesh.largest_surface` as separate panels and is refused there, which is the right
outcome.

This package matches the editor by the suffix `textEditorFrame.QCodeEditor`, so on 2025.2.368 it
will not find it. The bridge has been run on 2026.1.310 and 2026.1.382 only. Matching by parent
frame instead would need testing against a real 2025.2 install, and that has not been done.

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

## Putting texture maps on a fabric set its thickness to zero

**Symptom.** You add maps to a fabric with `utility_api.SetMaterialProperties` — base colour,
normal, displacement, roughness. The call returns `"success"`, the maps are there, and the
fabric's thickness is now 0 mm.

**Cause.** `ApiTypes.MaterialPropertyOptions()` carries a field `physical_thickness_mm`, default
`0.0`, and `SetMaterialProperties` writes it back along with the maps you set. Nothing in the
call mentions thickness. Measured on CLO 2026.1.310: seven fabrics exported to `.jfab` before
and after, 85 physical fields compared, and `mapPhysical.fThickness` was the only one that
moved — every one to `0.0`.

**Rule.** Read the thickness first and put it in the options object before the call:

```python
nv = ApiTypes.MaterialPropertyOptions()
nv.physical_thickness_mm = thickness_mm      # from the fabric's own .jfab, mapPhysical.fThickness
# ... set nv.front maps ...
utility_api.SetMaterialProperties(0, obj_index, ctx, selection, nv)
```

Then export the fabric again and compare `mapPhysical` field by field. An appearance change
should leave every physical value where it was; check that it did.

---

## With a texture on the fabric, OBJ UVs are no longer millimetres

**Symptom.** You compute strain from an exported OBJ by comparing each triangle's UV (flat
pattern) shape with its 3D shape. On one garment the flat and draped areas agree to 1 %; on the
next the ratio is 15,000.

**Cause.** With no texture, CLO writes UVs in pattern millimetres. With a texture on the fabric
it writes them in texture repeats: one UV unit is one tile. The ratio of 15,000 was
125.0 × 122.1 mm, the size the texture had been placed at.

**Rule.** Multiply the UVs by the texture's width and height in millimetres before using them as
pattern coordinates, then check: total draped area over total flat area should be close to 1.
Trims and avatar parts carry 0–1 texture UVs either way; filter them out by material.

---

## Stress and strain maps: a picture, not data

What CLO 2026.1.310 does and does not give through the API:

- **No values.** Only display toggles: `Set/GetStressMapStatus`, `Set/GetStrainMapStatus`. No
  export option carries per-face stress or strain. Stress can only be compared as screenshots.
  Strain can be computed from the mesh yourself (previous section).
- **The two maps switch each other off.** Opening the strain map in the GUI turns the stress map
  off. Read the status right before you export.
- **The colour scale is not settable** through the API. It lives in the GUI map panel (mode
  Global or Fabric, and a range). Two screenshots are comparable only if they were taken under
  the same mode and range; record both.

---

## Exporting a view: which call honours the camera

Two reports from CLO 2026.1.310, from two different jobs:

- `utility_api.SetCamViewPoint(n)` followed by `export_api.ExportSnapshot3D(path)` gave
  different images for `n = 2` (front) and `n = 3` (three-quarter).
- With `SetViewPoint`, `ExportSnapshot3D` ignored the view and always wrote the same front image.
  `export_api.ExportStdViewImage(viewIndex, "<file>.png", colorway, width, height)` takes the
  view as an argument instead; the path must include the extension. Indices observed: 0 bottom,
  1 and 3 three-quarter, 2 front close, 4 and 6 side, 5 top, 7 full front, 8 back, 9 front.

Later runs added four things:

- `SetCamViewPoint(n)` has its own presets, separate from the view index of `ExportStdViewImage`
  above. In one job in September 2026 they were 0 bottom, 1 back, 2 front, 3 front
  three-quarter, 4 side and 5 top.
- `SetZoomView()` re-frames the camera automatically and replaces a framing you set by hand.
  `ExportSnapshot3D` keeps whatever zoom the 3D window has, so set the framing once in CLO, save
  the project, and leave `SetZoomView` out.
- `ExportStdViewImage`'s arguments are unnamed (`int, str, int, int, int`) and width and height
  are the last two. Put them one place early and the call still answers: a height of 0 returned
  the string `Failed to Save Image`, not an error, and heights of 1 to 3 wrote images 2000 pixels
  wide and 1 to 3 pixels high, with a success message.
- On CLO 2026.1.310 (27 October 2026) every overload of `export_api.ExportRenderingImage`
  returned `[]` and wrote nothing, while `ExportSnapshot3D(path)` wrote the current viewport.

**Rule.** Whichever you use, look at the first two images before running the batch, and check
their pixel size. View numbers do not match their names, and an export that ignores the view, or
writes the wrong size, still succeeds.

---

## A piece's outline comes back empty, and which call answers depends on the build

**Symptom.** `pattern_api.GetPatternOutlinePoints(i)` returns `[]` for every piece, or is not
there at all. Code that draws or compares outlines finds no garment.

**Cause.** No one call for reading an outline has worked on every build tried. Neither failing
call raises; each simply returns nothing.

| CLO build | `GetPatternOutlinePoints(i)` | `ExportPatternJSON(path)` | `GetPatternLineInfo(i)` |
|---|---|---|---|
| 2025.2.368 (September 2026) | not present | worked | not recorded |
| 2026.1, build not recorded (9 September 2026) | `[]` | worked | not recorded |
| 2026.1.382 (19 November 2026), 41-piece top | `[]` for every piece | `False` for any path, nothing written | answered |

The 2026.1.382 row comes from `examples/probe_outlines_1119.py` and
`examples/probe_pattern_json_1119.py`. So this is not one update breaking one call. Outline
reading has moved between calls from build to build.

**Rule.** Try the three in turn and record which one answered for each piece:

1. `GetPatternOutlinePoints(i)`, if the module has it and it returns points.
2. `ExportPatternJSON(path)`. The points are under
   `PatternList[i].ShapeInfo.LineList[].PointList[].Position`. Use the file only if it lists the
   same number of pieces as `GetPatternCount()`, with the same names in the same order.
3. `GetPatternLineInfo(i)`, which returns the piece's lines with their start and end points;
   join them in line order.

If none answers, stop, or carry on only with steps that do not need the outline and record that
it is missing. An empty list looks like a piece with no shape, not like a failed call.
`examples/07_garment_scope.py` does this.

---

## You need the cloth vertices without exporting a file

**Symptom.** `utility_api.GetClothPositions` is listed in the module, so you try to read vertex
positions directly instead of exporting an OBJ after every block of simulation.

**Cause.** On CLO 2026.1.382 it returns `None` from Python, and the list passed in as an output
argument comes back unfilled (`examples/probe_speed_levers_1119.py`). There is no vertex data to
be had this way.

**Rule.** Export an OBJ and read that. On a 41-piece top each `ExportOBJ` took 5–6 s, so a
convergence check that exports after every block spends more time exporting than simulating.
Check less often if you must, but do not skip the check (next entry).

---

## Sixty steps is not "simulated"

**Symptom.** You simulate a fixed number of steps, compare two fabrics, and get a clean,
repeatable difference.

**Cause.** The garment may still be falling. On one top (41 pieces, CLO 2026.1.382), comparing two
fabrics by the hem's lowest point:

| | 60 steps | Simulated until still |
|---|---|---|
| Fabric A | 997.4 mm | 1001.7 mm (420 steps) |
| Fabric B | 989.7 mm | 997.2 mm (360 steps) |
| B − A | −7.7 mm | −4.5 mm |

Both hems were 4–7 mm lower at 60 steps than at rest, and the fixed-step difference was 1.72
times the difference at rest. Four earlier runs of the same comparison at 60 steps gave −7.2 to −8.0 mm,
so repeatability did not reveal the problem.

**Rule.** Simulate in blocks (60 steps each here), export after each block, and stop when the
mean vertex movement between blocks falls below a threshold you state (0.5 mm here), with a
ceiling (1,200 steps here). Report how many steps each run took. This is one garment and two
fabrics, so treat the 1.72 as an example, not a constant; the point is that a fixed step count
has to be checked against rest before its numbers are compared.

The ceiling matters as much as the threshold. On a 22-piece top (CLO 2026.1.310, October 2026)
four of six runs in one fabric were still moving about 1 mm per 60 steps when they reached 1,200
steps. Record a settled flag with every run, so a run that stopped at the ceiling is not read as
one that stopped moving.

Check pieces, not only the garment. On a 41-piece top (CLO 2026.1.310, October 2026), between
the last two exports at 4,300 steps, the median strain of every piece changed by less than 0.5%
except on a few small underarm pieces, where it still moved by up to 2%. A mean over the whole
garment can hide that, because small pieces carry few vertices.
`examples/06_simulate_until_still.py` records the steps, the settled flag and the movement of
each OBJ group.

---

## `reload()` brought back the wrong file

**Symptom.** You edit a helper module, the job imports it with `import x; importlib.reload(x)`,
and the traceback still points at the old code, sometimes in a different folder entirely.

**Cause.** CLO's Python interpreter stays alive between jobs. The first `import x` decides which
file `x` is, and `reload` re-reads *that* file. If an earlier job imported a copy of the module
from another folder (an installed version, an older checkout), every later job keeps reloading
that copy, whatever `sys.path` says now.

**Rule.** Load the modules your job depends on by path, so each job gets the file next to it:

```python
import importlib.util, os
spec = importlib.util.spec_from_file_location('helper', os.path.join(HERE, 'helper.py'))
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
```

---

## Exporting part of a garment to GLB loses its trims, and the model is 1000× too big

**Symptom.** You want the top and the bottom of an outfit as two `.glb` files, so you set
`ImportExportOption.patternList` to the top's patterns and call `export_api.ExportGLBW`. The
file has the panels and nothing else: topstitching, piping and labels are gone. Loaded into a
web viewer, either file is a kilometre-scale object off the edge of the camera.

**Cause.** `patternList` filters by pattern; trims are not patterns, so none of them pass the
filter. Separately, CLO writes vertex positions in millimetres and glTF reads them as metres.

**Rule.** Export the whole garment once (`bExportAvatar = False`), then split the file yourself.
Under the root `Cloth` node every pattern and every trim is its own child node, named
`Pattern_<n>` for panels. Group panels by name; give each trim node to the group whose panels lie
closest (median distance from a sample of its vertices, with a KD-tree over each group's
vertices). Set the `Cloth` node's scale to `0.001`, then run `gltf-transform validate` on each
output and check the bounding box is in metres.

---

## Texture maps and colours are set per colorway, and need reading back

`fabric_api.SetBaseTextureMapImageGivenFilePathW(path, colorway, fabric)` and
`SetNormalMapImageGivenFilePathW(path, colorway, fabric)` take a colorway index. Replacing a
fabric's texture in a file with several colorways means looping over
`range(utility_api.GetColorwayCount())`, then exporting a view in each colorway to check.

Colour works the same way, with its own traps. Observed in November 2026 (CLO 2026.1, build not
recorded):

- Write a colorway's colour with `SetFabricPBRMaterialBaseColor(colorway, fabric, face, r, g, b,
  a)` and read it back from `GetColorwayFabricInfoW(colorway, fabric)`. The overload of
  `GetFabricPBRMaterialBaseColor` that takes a colorway raised a type-conversion error. A first
  run that failed halfway had already written wrong colours, which only a read-back showed.
- `DeleteFabricOpacityMap` straight after `AddFabricW` did not always take effect. Read back
  `GetOpacityMapImageFilePath`, and delete again until it returns `"NONE"`.
- A base texture with an alpha channel makes the whole fabric render as translucent in texture
  mode. Replace it with an RGB copy of the same size. CLO's interpreter has no PIL, so make the
  copy on the host.
- Two getters can report one property on different scales. `GetReflectionIntensity` returned
  `15.0` where `GetFabricInfoW` reported `reflectionIntensity` as `0.15`. Convert before you
  compare.
- The map paths a fabric reports can point into a working folder under CLO's local application
  data, not next to the fabric file. Copy the maps somewhere you control before relying on them.

---

## An OBJ export is hundreds of megabytes, nearly all of it topstitching

**Symptom.** A measurement export of an ordinary garment is far larger than the project. Parsing
it is slow, or CLO stops responding while you do.

**Cause.** 3D topstitches are exported as geometry. A 41-piece top saved as a 39 MB project
exported a 481.9 MB OBJ with 3,736,596 faces. Of those, 47,596 were cloth and 3,689,000 used
topstitch materials. A larger export of 861 MB, parsed by a script inside CLO's interpreter,
pushed CLO's private memory to about 8.8 GB and CLO had to be killed. Both were seen on
9 September 2026, build not recorded.

**Rule.** For a measurement export, switch each topstitch style to texture for the export only,
and restore it in `finally`:

```python
styles = [int(s["TopstitchStyleIndex"]) for s in pattern_api.GetTopstitchStyleList()]
before = {i: pattern_api.GetTopstitchStyleModelType(i) for i in styles}
try:
    for i, kind in before.items():
        if kind == 0:                                   # 0 drawn in 3D, 1 drawn as texture
            pattern_api.SetTopstitchStyleModelType(i, 1)
    export_api.ExportOBJW(path, opt)
finally:
    for i, kind in before.items():
        pattern_api.SetTopstitchStyleModelType(i, kind)
```

Read each type back on the way out, and refuse to start if any style reports a type other than
0 or 1. On the 41-piece top the export fell to 12.2 MB. It still held 7,550 tiny islands, which
`clo_bridge.mesh.largest_surface` drops. Check the file size before parsing anything:
`clo_bridge.mesh.read_obj` refuses a file over 64 MB before reading a line, and
`examples/06_simulate_until_still.py` does the same.

With `bSingleObject = False` the OBJ arrives in groups. On a 41-piece top (CLO 2025.2.368,
September 2026) the first 41 groups were the 41 pieces in order, and the 86 after them were
topstitches and trims.

---

## The maps went onto a different fabric

**Symptom.** `utility_api.SetMaterialProperties` returns `"success"` and the maps appear on the
wrong fabric. A script that looks a fabric up, fails to find it and adds it ends up with two
copies.

**Cause.** Its `objectIndex` counts items in the Object Browser, not `fabric_api` indices. By
default the browser hides fabrics that no piece uses (`ObjectBrowserContextOptions()` comes with
`bIncludeUnusedObjects = False`), so the two numberings differ as soon as one fabric is unused.
Seen in October 2026, build not recorded.

**Rule.** Show unused objects, look the index up by name, and put the browser back:

```python
ctx = utility_api.GetObjectBrowserContext()
was = ctx.bIncludeUnusedObjects
ctx.bIncludeUnusedObjects = True
utility_api.SetObjectBrowserContext(ctx)
try:
    names = json.loads(utility_api.GetObjectBrowserItems(ctx))["ObjectNameList"]
    index = names.index(fabric_name)
    utility_api.SetMaterialProperties(colorway, index, ctx, selection, new_values)
finally:
    ctx.bIncludeUnusedObjects = was
    utility_api.SetObjectBrowserContext(ctx)
```

Then read the maps back from the fabric you meant (`GetMaterialPropertiesAsJson`), and check
its thickness (see *Putting texture maps on a fabric set its thickness to zero*).

---

## Grain angles and bounding boxes come back raw

`pattern_api.GetPatternPieceGrainDirection(i)` is not normalised. On one 13-piece project
(October 2026, build not recorded) it returned 180.74, -180.74, 359.74 and -359.74 degrees, and
some mirrored pairs read back with opposite signs. Reduce angles with `% 360` before comparing
them. `GetBoundingBoxOfPattern(i)` returns a dict of strings (`{"Height": "225.871948",
"Width": "96.856201"}`), so convert with `float` before doing arithmetic.

---

## Each shape you draw appears twice

**Symptom.** `pattern_api.CreateInternalShapeWithPoints` draws a 16-point circle and it reads back
as 32 lines. Draw on both halves of a piece and you get a double layer, and turning it into a
hole fails with `Holes cannot overlap`.

**Cause.** The piece has symmetric editing switched on, so CLO mirrors every shape you add. The
same setting limits moving points: on a mirrored piece only half the points can be moved, and the
other half follow. Seen in September and November 2026, build not recorded.

**Rule.** Switch symmetric editing off in CLO before drawing, and read back the number of lines
of each shape after drawing it. When moving points on a mirrored piece, read back every corner
afterwards, not only the one you moved. `MovePatternPoint` takes absolute coordinates, not an
offset; that was confirmed by moving one point and reading it back.

---

## Resetting the cloth is not a quick way to start a run again

`utility_api.ResetClothArrangement()` is fast and does not restore the saved starting state. On a
102-piece project (13 September 2026, build not recorded) it took 0.19 s, and afterwards the
measured lowest point was 35.8 mm from its value at the start of the job. One coordinate had
moved by 422 mm. Re-import the project for each run, as `examples/04_sweep.py` does. On that
project the import took 12.3 s.

---

## CLO's interpreter is not your interpreter

**Symptom.** `ONLY=11 python my_job.py` limits the host as intended, and the worker still changes
every piece.

**Cause.** `main` runs inside CLO's process. Its environment was fixed when CLO started, so
variables set in the shell that runs the host never reach it. The same separation means CLO's
interpreter has none of your packages. It had no PIL in November 2026, and on 2025.2.368 no
PySide or PyQt either.

**Rule.** Pass every setting the worker needs in the payload: `clo.run(script, {"only": 11})`.
Do image processing and anything else that needs a package on the host, and hand CLO the result.

---

## A read-only probe changed the project

**Symptom.** A probe written to change nothing leaves the project's settings different.

**Cause.** The probe chose functions by name. It collected every `pattern_api` function whose name
contained `article` and called each with a piece index, which caught
`SetParticleDistanceOfPatterns`. By CLO's published signature that sets the particle distance of
every piece to the length given, and the probe called it with 0 and then 1. It returned `None`
both times, and nothing in the output looked wrong (2 October 2026, build not recorded).

**Rule.** A probe calls an explicit list of getters, written out by name. Never select calls by
substring or by `dir()`. Run probes on a copy, or re-import the project before any real run.

---

## There is no supported headless mode

Worth stating plainly, because it is the question everyone arrives with. CLO publishes no
instructions for running its Python API without the desktop application. Its API changelog does
mention a headless mode, and strings in the CLO 2026.1.224 binary suggest a command-line entry
point that needs an access key issued by CLO. How to obtain a key, and what a licence allows, are
not publicly documented. One launch tried without a key in September 2026 opened the interactive
sign-in window and ran nothing.

This package does not use that entry point. Running on a server here means running a full
desktop session with CLO signed in, and the licence terms for that, or for any headless use, are
between you and CLO. This package does not handle credentials, does not automate sign-in, and
does not attempt to bypass anything. It drives the editor of an instance a human has already
signed in to.
