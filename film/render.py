# -*- coding: utf-8 -*-
"""Render stage.html to video. Time is a variable, not a clock: every frame is seek(t) + screenshot.

    python film/render.py verify            layout checks: on the grid, in the frame, nothing wrapped
    python film/render.py keys              stills at the film's key moments -> out/keys.png
    python film/render.py probe 3.5 12 40   stills at given seconds       -> out/probe.png
    python film/render.py frames [k n]      all frames, or chunk k of n   -> out/frames/
    python film/render.py encode            frames (+ out/audio.wav)      -> out/clo3d-python-bridge.mp4
    python film/render.py pops              scan the film for single-frame jumps

Needs: pip install playwright pillow numpy; python -m playwright install chromium; ffmpeg on PATH.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
FRAMES = OUT / "frames"
FILM = OUT / "clo3d-python-bridge.mp4"
URL = (HERE / "stage.html").as_uri() + "?render=1"
W, H, FPS = 1920, 1080, 60
# ponytail: one sample per frame, no motion blur. Nothing here moves more than 16 px, and blur on
# type meant to be read costs sharpness for nothing. Add subframes if a fast move ever goes in.
FF = shutil.which("ffmpeg") or sys.exit("ffmpeg is not on PATH")


def stage(pw):
    browser = pw.chromium.launch(args=["--force-device-scale-factor=1", "--hide-scrollbars",
                                       "--font-render-hinting=none", "--force-color-profile=srgb"])
    page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL)
    page.wait_for_function("window.ready === true", timeout=60000)
    # an image that has not decoded renders as an empty box, silently
    page.wait_for_function("() => [...document.images].every(i => i.complete && i.naturalWidth > 0)")
    fonts = page.evaluate("[...document.fonts].filter(f => f.status === 'loaded').map(f => f.family)")
    if len(fonts) < 2:
        sys.exit("the film's fonts did not load (%s); every measurement would be of a fallback" % fonts)
    return browser, page, errors


def shot(page, t, path):
    page.evaluate("t => window.seek(t)", t)
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    page.screenshot(path=str(path), animations="disabled")


def sheet(paths, dest, cols=4, width=640):
    from PIL import Image
    ims = [Image.open(p).convert("RGB") for p in paths]
    h = width * H // W
    rows = -(-len(ims) // cols)
    out = Image.new("RGB", (cols * width, rows * h), "white")
    for i, im in enumerate(ims):
        out.paste(im.resize((width, h), Image.LANCZOS), ((i % cols) * width, (i // cols) * h))
    out.save(dest)
    print("->", dest)


def stills(times, name):
    from playwright.sync_api import sync_playwright
    d = OUT / "stills"
    d.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser, page, errors = stage(pw)
        paths = []
        for i, t in enumerate(times):
            paths.append(d / ("%s_%02d.png" % (name, i)))
            shot(page, t, paths[-1])
        browser.close()
    if errors:
        sys.exit("page errors: %s" % errors[:5])
    sheet(paths, OUT / (name + ".png"))


def main():
    from playwright.sync_api import sync_playwright
    cmd = sys.argv[1] if len(sys.argv) > 1 else "keys"
    OUT.mkdir(exist_ok=True)

    if cmd == "verify":
        with sync_playwright() as pw:
            browser, page, errors = stage(pw)
            report = page.evaluate("window.verify()")
            cues = page.evaluate("({cues: window.CUES, dur: window.DUR, cuts: window.CUTS, pulse: window.PULSE, sections: window.SECTIONS})")
            browser.close()
        (OUT / "cues.json").write_text(json.dumps(cues, indent=1), encoding="utf-8")
        bad = {k: v for k, v in report.items() if v}
        print(json.dumps(report, indent=1))
        print("%d cue(s) -> out/cues.json" % len(cues["cues"]))
        if bad or errors:
            sys.exit("LAYOUT VERIFY: FAIL %s" % (errors[:5] or ""))
        print("LAYOUT VERIFY: PASS")

    elif cmd == "keys":
        with sync_playwright() as pw:
            browser, page, _ = stage(pw)
            times = page.evaluate("window.KEYS")
            browser.close()
        stills(times, "keys")

    elif cmd == "probe":
        stills([float(x) for x in sys.argv[2:]], "probe")

    elif cmd == "frames":
        k, n = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (0, 1)
        FRAMES.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as pw:
            browser, page, errors = stage(pw)
            total = int(round(page.evaluate("window.DUR") * FPS))
            a, b = total * k // n, total * (k + 1) // n
            for i in range(a, b):
                shot(page, i / FPS, FRAMES / ("f%05d.png" % i))
                if (i - a) % 300 == 0:
                    print("chunk %d: %d/%d" % (k, i - a, b - a), flush=True)
            browser.close()
        if errors:
            sys.exit("page errors: %s" % errors[:5])
        print("chunk %d done: frames %d..%d" % (k, a, b - 1))

    elif cmd == "encode":
        dur = json.loads((OUT / "cues.json").read_text(encoding="utf-8"))["dur"]
        want, have = int(round(dur * FPS)), len(list(FRAMES.glob("f*.png")))
        if have != want:
            sys.exit("%d of %d frames rendered" % (have, want))
        audio = OUT / "audio.wav"
        cmd = [FF, "-v", "error", "-y", "-framerate", str(FPS), "-i", str(FRAMES / "f%05d.png")]
        if audio.exists():
            cmd += ["-i", str(audio), "-c:a", "aac", "-b:a", "256k"]
        cmd += ["-vf", "scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p",
                "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709",
                "-color_trc", "bt709", "-c:v", "libx264", "-preset", "slow", "-crf", "22",
                "-movflags", "+faststart", "-t", str(dur), str(FILM)]
        subprocess.run(cmd, check=True)
        print("-> %s  %.1f MB  %s" % (FILM, FILM.stat().st_size / 1e6,
                                      "with sound" if audio.exists() else "SILENT"))

    elif cmd == "pops":
        import numpy as np
        raw = subprocess.run([FF, "-v", "quiet", "-i", str(FILM), "-vf", "scale=180:180,format=gray",
                              "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        fr = np.frombuffer(raw, np.uint8).reshape(-1, 180, 180).astype(np.float32)
        d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
        meta = json.loads((OUT / "cues.json").read_text(encoding="utf-8"))
        cuts = {int(round(c * FPS)) for c in meta["cuts"]}
        p0, p1, beat = meta["pulse"]            # the picture flashes on the beat here, on purpose
        beats = {int(round(b * beat * FPS)) for b in range(int(p0 / beat), int(p1 / beat))}
        hits = [(i + 1, round((i + 1) / FPS, 3), round(float(d[i]), 2)) for i in range(1, len(d) - 1)
                if d[i] > 3 * max(d[i - 1], d[i + 1], 0.3) and d[i] > 2.0]
        stray = [h for h in hits if h[0] not in cuts and h[0] not in beats]
        print("%d frames, %d jump(s): %d on a camera cut, %d on a beat, %d unexplained" %
              (len(fr), len(hits), sum(h[0] in cuts for h in hits),
               sum(h[0] in beats and h[0] not in cuts for h in hits), len(stray)))
        for h in stray:
            print("  frame %d  t=%.3f  diff %.2f" % h)
        if stray:
            sys.exit(1)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
