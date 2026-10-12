# The film

A 72-second film about this package, drawn by code. [Watch it](https://cdn.jsdelivr.net/gh/ZHOUCHENHAO1221/clo3d-python-bridge@master/docs/film.mp4): that is the 720p copy in
`docs/film.mp4`, served through jsDelivr because GitHub will not play a video stored in a
repository. This folder is everything needed to render it again at 1080p, 60 fps.

## What is real in it

- **The 846 dots.** One per function name in `scripts/api_surface.json`. The red counts — 207,
  173, 106, 43 — are section sizes in `reference/API_MAP.md`.
- **The flat pattern.** The cut lines and internal lines of the DXF the garment was simulated
  from, in millimetres, as CLO wrote them.
- **The garments.** Every point is a vertex CLO solved: three patterns, each in seven measured
  fabrics, 21 meshes. Within one pattern the seven share a topology, so when the cloth changes
  fabric on screen, vertex *i* is moving to where vertex *i* ended up in the other simulation.
- **The numbers.** Each hem width is measured off the mesh by `clo_bridge.mesh` when the data
  is packed, and the packing stops if one disagrees with `docs/fabric_sweep_3x7.jpg`. The
  fabric weight and thickness are the output of `examples/03_load_measured_fabric.py`.
- **The soundtrack's melody.** One note per fabric, ordered by hem width: the narrowest hem is
  the lowest note.

Two moves are transitions and carry no data: dots to pattern, and pattern to garment. Which
point goes where between those states means nothing.

## Render it

```bash
pip install playwright pillow numpy
python -m playwright install chromium        # ffmpeg must be on PATH

python film/render.py verify     # layout checks; writes out/cues.json
python film/audio.py             # the soundtrack, synthesised -> out/audio.wav
python film/render.py frames     # 4,320 frames -> out/frames/   (or: frames 0 4 ... frames 3 4, in parallel)
python film/render.py encode     # -> out/clo3d-python-bridge.mp4
python film/render.py pops       # single-frame jumps: every one should be a cut or a beat
```

Open `stage.html` in a browser to watch it without rendering: Space pauses, the arrow keys step
one frame, `?t=36` starts at a second.

## How it is made

`stage.html` holds the whole film as one function, `seek(t)`. It has no clock and keeps nothing
between frames, so frame 2,000 can be drawn without drawing the 1,999 before it, and two
renders of the same second are identical. `render.py` calls `seek` once per frame and takes a
screenshot. `audio.py` reads its cue times from the same page, so picture and sound cannot
drift apart.

`build_clouds.py` packed the meshes and the pattern into `assets/clouds.js`. You only need it
to make a film from your own garments:

```bash
pip install ezdxf
python film/build_clouds.py <folder of exported .obj files> <pattern.dxf>
```

## Not mine

The typefaces are Geist and Geist Mono, under the SIL Open Font License; the licence texts are
in `fonts/`. The pipeline — one `seek(t)` function, frame-by-frame capture, a scan for
single-frame jumps — follows [howseen-ai/claude-motion-design](https://github.com/howseen-ai/claude-motion-design).
