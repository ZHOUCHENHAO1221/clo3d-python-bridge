# -*- coding: utf-8 -*-
"""Generate the README's diagrams.

    python scripts/build_diagrams.py

They are committed as SVG so GitHub renders them without a build step, and generated from this
script rather than drawn by hand so a change to the protocol can be reflected in one place.

The palette is deliberately light-background: GitHub serves the same file to light and dark
readers, and a white card on a dark page is legible while the reverse is not.
"""
import os

import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(os.path.dirname(HERE), "docs")

INK = "#14161a"
MUTE = "#6b7280"
LINE = "#c7cbd1"
RED = "#e5242b"
FILL = "#f6f7f9"
PAPER = "#ffffff"
FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,"
        "'Noto Sans',sans-serif")
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,monospace"


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def text(x, y, s, size=15, fill=INK, weight="400", anchor="start", mono=False):
    return ('<text x="%g" y="%g" font-family="%s" font-size="%g" fill="%s" '
            'font-weight="%s" text-anchor="%s">%s</text>'
            % (x, y, MONO if mono else FONT, size, fill, weight, anchor, esc(s)))


def box(x, y, w, h, fill=FILL, stroke=LINE, rx=10, dash=None, sw=1.5):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    return ('<rect x="%g" y="%g" width="%g" height="%g" rx="%g" fill="%s" '
            'stroke="%s" stroke-width="%g"%s/>' % (x, y, w, h, rx, fill, stroke, sw, d))


def arrow(x1, y1, x2, y2, stroke=INK, dash=None, sw=1.8, head="end"):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    m = ' marker-end="url(#a)"' if head == "end" else ""
    return ('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="%s" stroke-width="%g"%s%s/>'
            % (x1, y1, x2, y2, stroke, sw, d, m))


def svg(w, h, body, title, desc):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %g %g" width="%g" '
            'height="%g" role="img" aria-labelledby="t d">\n'
            '<title id="t">%s</title><desc id="d">%s</desc>\n'
            '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
            'markerHeight="6" orient="auto-start-reverse">'
            '<path d="M0,0 L10,5 L0,10 z" fill="%s"/></marker>'
            '<marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
            'markerHeight="6" orient="auto-start-reverse">'
            '<path d="M0,0 L10,5 L0,10 z" fill="%s"/></marker></defs>\n'
            '<rect width="%g" height="%g" fill="%s"/>\n%s\n</svg>\n'
            % (w, h, w, h, esc(title), esc(desc), INK, RED, w, h, PAPER, body))


# --------------------------------------------------------------- 1. architecture
def architecture():
    p = []
    W, H = 1120, 600
    p.append(text(40, 46, "How a job reaches CLO and how its result comes back", 19, INK, "700"))
    p.append(text(40, 72, "CLO has no headless mode, so the host drives the GUI's Python "
                          "editor. The GUI cannot answer back.", 14, MUTE))

    # columns
    p.append(box(40, 104, 310, 220, PAPER, LINE))
    p.append(text(60, 134, "YOUR PYTHON PROCESS", 12, MUTE, "700"))
    p.append(text(60, 164, "CloSession.run(script, payload)", 14, INK, "600", mono=True))
    for i, s in enumerate(["1  create the job directory",
                           "2  write request.json",
                           "3  type the loader, click Play",
                           "6  poll for result.json"]):
        p.append(text(60, 196 + i * 26, s, 13.5, INK if i != 3 else RED,
                      "600" if i == 3 else "400"))

    p.append(box(770, 104, 310, 220, PAPER, LINE))
    p.append(text(790, 134, "CLO STANDALONE  (GUI)", 12, MUTE, "700"))
    p.append(text(790, 164, "Edit › Python Script", 14, INK, "600"))
    for i, s in enumerate(["4  the loader execs your worker",
                           "5  worker writes heartbeat.json",
                           "   then result.json",
                           "   nothing is returned to the host"]):
        p.append(text(790, 196 + i * 26, s, 13.5, MUTE if i == 3 else INK))

    # the disk, in the middle
    p.append(box(400, 150, 320, 174, FILL, LINE))
    p.append(text(560, 180, "THE JOB DIRECTORY (on disk)", 12, MUTE, "700", anchor="middle"))
    for i, (f, who) in enumerate([("request.json", "host → worker"),
                                  ("heartbeat.json", "worker → host"),
                                  ("result.json", "worker → host")]):
        y = 212 + i * 34
        p.append(text(424, y, f, 13.5, RED if i == 2 else INK, "700" if i == 2 else "500",
                      mono=True))
        p.append(text(696, y, who, 12, MUTE, anchor="end"))

    # arrows
    p.append(arrow(350, 196, 398, 196))                                  # host -> request
    p.append(arrow(722, 246, 768, 246, head="none"))
    p.append(arrow(722, 246, 768, 246))                                  # disk -> clo (reads)
    p.append(arrow(768, 280, 724, 280, RED))                             # clo -> result
    p.append(arrow(398, 280, 352, 280, RED))                             # result -> host
    # the GUI "reply" that does not exist
    p.append(arrow(768, 140, 352, 140, MUTE, dash="6 6", sw=1.4))
    p.append(text(560, 132, "no return channel from the editor", 12, MUTE, anchor="middle"))

    # the rule
    p.append('<rect x="40" y="372" width="1040" height="2" fill="%s"/>' % LINE)
    p.append(text(40, 414, "Pressing Play tells you nothing.", 17, INK, "700"))
    p.append(text(40, 444,
                  "Qt can invalidate the editor's automation handle while CLO is still "
                  "executing, so the host sees an error for a job", 14, INK))
    p.append(text(40, 468,
                  "that succeeded. The click, the control state and any pywinauto exception "
                  "are all ignored. Only result.json decides.", 14, INK))

    p.append(box(40, 496, 1040, 72, FILL, LINE))
    p.append(text(64, 526, "result, stage = wait_for_result(job_dir, timeout=900)",
                  14, INK, "600", mono=True))
    p.append(text(64, 552, "stage is the last heartbeat, which is what turns a timeout into "
                           "“it got as far as simulating”.", 13, MUTE))
    return svg(W, H, "\n".join(p), "Architecture of the CLO bridge",
               "The host writes a request file, drives CLO's Python editor, and polls a "
               "result file that the worker writes. The GUI provides no return channel.")


# --------------------------------------------------------------- 2. the API surface, measured
def api_surface():
    """A real measurement, not an illustration: the counts come from the committed probe."""
    import json
    import build_api_map as bam

    surface = json.load(open(os.path.join(HERE, "api_surface.json"), encoding="utf-8"))
    modules = {k: v for k, v in surface["modules"].items()
               if isinstance(v, dict) and "error" not in v and k != bam.TYPES_MODULE}
    by_name = {}
    for mod, names in modules.items():
        for n in names:
            by_name.setdefault(n, []).append(mod)
    buckets, other = bam.classify(sorted(by_name))
    rows = [(t, len(buckets[t])) for t, _ in bam.GROUPS if buckets[t]]
    rows.append(("Other (the grouping did not place these)", len(other)))

    p = []
    top, pitch = 136, 25
    W, H = 1120, top + pitch * len(rows) + 92
    p.append(text(40, 46, "The CLO Python API, grouped by what you want to do", 19, INK, "700"))
    p.append(text(40, 72, "%d callable names across %d modules, read out of a live interpreter "
                          "by scripts/probe_api.py." % (len(by_name), len(modules)), 14, MUTE))
    p.append(text(40, 94, "Alphabetical order is a dictionary. This is the index you would "
                          "actually search.", 14, MUTE))

    x0, bar_x, bar_w = 40, 470, 520
    biggest = max(n for _, n in rows)
    p.append('<rect x="%g" y="%g" width="%g" height="1" fill="%s"/>' % (x0, top - 18, 1040, LINE))
    for i, (label, n) in enumerate(rows):
        y = top + i * pitch
        last = i == len(rows) - 1
        p.append(text(x0, y, label, 13.5, MUTE if last else INK, "400" if last else "500"))
        w = max(2.0, bar_w * n / biggest)
        p.append('<rect x="%g" y="%g" width="%g" height="12" rx="2" fill="%s"/>'
                 % (bar_x, y - 10, w, LINE if last else RED))
        p.append(text(bar_x + w + 10, y, str(n), 13, MUTE if last else INK, "600"))

    y = top + pitch * len(rows) + 22
    p.append('<rect x="%g" y="%g" width="%g" height="1" fill="%s"/>' % (x0, y - 16, 1040, LINE))
    p.append(text(x0, y + 8, "A name may appear under more than one task, and that is the "
                             "point: you find it from whichever one you were thinking of.",
                  13, MUTE))
    p.append(text(x0, y + 30, "A trailing W is CLO's wide-string variant — use it for any "
                              "path or label that may contain non-ASCII characters.", 13, MUTE))
    return svg(W, H, "\n".join(p), "The CLO Python API surface grouped by task",
               "A horizontal bar chart of how many API functions fall into each task group, "
               "measured from a live probe of CLO.")


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, fn in (("architecture.svg", architecture), ("api_surface.svg", api_surface)):
        path = os.path.join(OUT, name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(fn())
        os.replace(tmp, path)
        print("wrote %s  (%d bytes)" % (path, os.path.getsize(path)))


if __name__ == "__main__":
    main()
