# -*- coding: utf-8 -*-
"""api_surface.json -> reference/API_MAP.md

A flat list of 800+ names sorted alphabetically is a dictionary, and nobody learns an API from a
dictionary. What you actually ask is "how do I apply a fabric", so the map is grouped by task
first and module second, with the alphabetical index kept at the end for lookup.

    python scripts/build_api_map.py [api_surface.json]

Grouping is by keyword against the function name. That is a heuristic and it is allowed to be:
a name landing in two groups is listed in both, and whatever matches nothing lands in "Other",
which is printed with a count so you can see how much the heuristic missed.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ordered: the first group a name matches wins its headline slot, but a name may appear again
# under a later group if it also matches there - duplication helps a reader, it does not hurt
GROUPS = [
    ("Open, save and project state",
     r"^(Open|Save|New|Close|Clear)|Project|Snapshot$"),
    ("Import geometry and avatars",
     r"^Import|^Load|^Add(Avatar|Trim)"),
    ("Export: files, images, video",
     r"^Export|^Convert|^Save.*(Image|File)"),
    ("Patterns: create, edit, sew",
     r"Pattern|Seam|Sewing|Line|Point|Segment|Dart|Notch|Fold|Internal"),
    ("Grading and sizing",
     r"Grading|Size|Measure|Measurement"),
    ("Fabric and material properties",
     r"Fabric|Texture|Material|Xtex|Color|Colour|Swatch|Physical|Preset|Zfab"),
    ("Surface shading (PBR maps)",
     r"Metalness|Roughness|NormalMap|NormalBlending|Opacity|Reflection|Displacement|SBSAR"),
    ("Simulation and solver",
     r"Simulat|Solver|Particle|Animat|Freeze|Pin|Gravity|Collision|ClothCache|ClothPosition"),
    ("3D arrangement and draping",
     r"Arrangement|AutoHang|ReDrape|SetAPF"),
    ("Wind",
     r"Wind(?!ow)"),
    ("Strain, stress and fit maps",
     r"StrainMap|StressMap|FitMap|PressureMap"),
    ("Shrinkage",
     r"Shrinkage"),
    ("Camera, view and render",
     r"Camera|View|Render|Light|Image|Snapshot|Resolution|Background|3DWindow|Schematic"),
    ("Avatar and pose",
     r"Avatar|Pose|Skin|Body|Hair"),
    ("Trims, buttons, topstitch, graphics",
     r"Button|Trim|[Tt]op[Ss]titch|Stitch|Graphic|Print|Puckering|Zipper"),
    ("Nesting, marker and UV",
     r"Nesting|UVPacking|FitAllUV|UVExpansion|ResetUV"),
    ("Library, metadata and tech pack",
     r"Library|MetaData|BOM|TechPack|Category|Style|Annotation|Comment|Asset"),
    ("Selection and visibility",
     r"Select|Activate|Deactivate|Show|Hide|Visib|Toggle|DisplayProperties"),
    ("Plug-ins, widgets and progress UI",
     r"PlugIn|Widget|Progress|MessageBox|ObjectBrowser|Refresh|UpdateProperty|Theme|"
     r"RegisterPythonScript"),
    ("Version, paths and environment",
     r"(Major|Minor|Patch)Version|BasePath|CleanFilePath|HeadQuarter|NetworkAuth|"
     r"toUtf8|stringToMD5|MeshType|MeshCount"),
]


def signatures(doc):
    """Pull the callable signature(s) out of a pybind11 __doc__.

    Two shapes exist. A plain function documents itself on the first line:

        ImportDXFW(arg0: str, arg1: Marvelous::ImportDxfOption) -> bool

    An overloaded one declares (*args, **kwargs) and then numbers its forms:

        ExportOBJ(*args, **kwargs)
        Overloaded function.

        1. ExportOBJ() -> List[str]
        2. ExportOBJ(arg0: str) -> List[str]

    Returns the real forms in both cases, so the reader never sees (*args, **kwargs) - which
    tells them nothing - when the actual arities are right there.
    """
    if not doc:
        return []
    lines = [l.strip() for l in doc.splitlines() if l.strip()]
    numbered = [re.sub(r"^\d+\.\s*", "", l) for l in lines if re.match(r"^\d+\.\s", l)]
    if numbered:
        return numbered
    first = lines[0] if lines else ""
    return [first] if "(" in first else []


def classify(names):
    buckets = {title: [] for title, _ in GROUPS}
    seen = set()
    for name in names:
        for title, pattern in GROUPS:
            if re.search(pattern, name):
                buckets[title].append(name)
                seen.add(name)
    other = [n for n in names if n not in seen]
    return buckets, other


# ApiTypes holds enums, constants and struct types, not callable functions. Grouping it by task
# alongside the *_api modules would inflate every count and answer a different question from the
# one the map exists to answer, so it gets a section of its own.
TYPES_MODULE = "ApiTypes"


def render(surface):
    all_modules = {k: v for k, v in surface["modules"].items()
                   if isinstance(v, dict) and "error" not in v}
    types = sorted(all_modules.pop(TYPES_MODULE, {}))
    modules = all_modules
    by_name, docs = {}, {}
    for module, entries in modules.items():
        for name, doc in entries.items():
            by_name.setdefault(name, []).append(module)
            if doc and name not in docs:
                docs[name] = doc

    buckets, other = classify(sorted(by_name))
    version = surface.get("version") or "unverified - regenerate with scripts/probe_api.py"

    out = ["# CLO Python API map", "",
           "Generated by `scripts/build_api_map.py` from a live probe of **CLO %s**." % version,
           "",
           "`%d` callable names across %d modules: %s."
           % (len(by_name), len(modules),
              ", ".join("`%s` %d" % (m, len(v)) for m, v in sorted(modules.items()))),
           "",
           "> Signatures come from each function's `__doc__`: the API is a pybind11 binding, so",
           "> every callable carries its own argument list, overloads included. That is the only",
           "> machine-readable source for them - `inspect.signature()` raises on these builtins.",
           "> Types such as `Marvelous::ImportDxfOption` are C++ names; the corresponding Python",
           "> object is usually in `ApiTypes` at the end of this file. Names and arities differ",
           "> between builds, so regenerate rather than trusting the copy committed here.", "",
           "A trailing `W` on a name is CLO's wide-string variant - use it for any path or label",
           "that may contain non-ASCII characters.", "",
           "---", ""]

    def entry(name):
        where = ", ".join(by_name[name])
        forms = signatures(docs.get(name, ""))
        if not forms:
            return ["- `%s`  <sub>%s</sub>" % (name, where)]
        if len(forms) == 1:
            return ["- `%s`  <sub>%s</sub>" % (forms[0], where)]
        lines = ["- `%s`  <sub>%s &middot; %d overloads</sub>" % (name, where, len(forms))]
        lines += ["  - `%s`" % f for f in forms]
        return lines

    for title, _ in GROUPS:
        names = buckets[title]
        if not names:
            continue
        out.append("## %s  <sub>%d</sub>" % (title, len(names)))
        out.append("")
        for name in names:
            out.extend(entry(name))
        out.append("")

    out.append("## Other  <sub>%d</sub>" % len(other))
    out.append("")
    out.append("Names the keyword grouping did not place. Not less important - just not named")
    out.append("in a way the heuristic recognises.")
    out.append("")
    for name in other:
        out.extend(entry(name))
    out.append("")

    if types:
        out.append("---")
        out.append("")
        out.append("## `ApiTypes` - enums, constants and struct types  <sub>%d</sub>" % len(types))
        out.append("")
        out.append("Not callable, which is why these are kept out of the task grouping above.")
        out.append("They are the vocabulary the functions expect: anchor points, units, option")
        out.append("flags and the small result objects some calls return.")
        out.append("")
        out.append(", ".join("`%s`" % n for n in types))
        out.append("")
    return "\n".join(out)


def main(argv):
    src = argv[1] if len(argv) > 1 else os.path.join(HERE, "api_surface.json")
    with open(src, encoding="utf-8") as fh:
        surface = json.load(fh)
    text = render(surface)
    target = os.path.join(ROOT, "reference", "API_MAP.md")
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, target)
    print("wrote %s  (%d lines)" % (target, text.count("\n") + 1))


if __name__ == "__main__":
    main(sys.argv)
