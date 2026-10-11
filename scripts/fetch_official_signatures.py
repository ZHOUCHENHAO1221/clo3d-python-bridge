# -*- coding: utf-8 -*-
"""Read the parameter names out of CLO's published API list.

    python scripts/fetch_official_signatures.py

A runtime probe gives you `arg0, arg1` - pybind11 does not keep the C++ parameter names. CLO
publishes them, with the module grouping, at developer.clo3d.com/list.html. This fetches that
page and extracts one record per function: the name, the Python signature as CLO writes it,
and the `@ingroup` it belongs to.

**What this deliberately does not take.** CLO's `@brief` and `@param` prose is their
documentation, not ours to republish, so none of it is written to disk or into the map. What
is kept is the interface itself - names, parameter names, types - which is the same kind of
fact the runtime probe already records, and the map links back to the official page for the
descriptions.

The page documents one SDK release, which is not necessarily the build you are running. The
map keeps both sources and says where they disagree; see build_api_map.py.
"""
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://developer.clo3d.com/list.html"
OUT = os.path.join(HERE, "official_signatures.json")

# The python tab of each function block holds `def Name(args) -> ret`, marked up span by span.
DEF = re.compile(
    r'<span class="k">def</span>\s*<span class="nf">(?P<name>\w+)</span>(?P<body>.*?)</pre>',
    re.S)
INGROUP = re.compile(r"@ingroup\s+(\w+)")
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")


def _text(html_fragment):
    import html as _html
    return WS.sub(" ", _html.unescape(TAG.sub("", html_fragment))).strip()


def parse(page):
    """Return {name: {"signature": str, "ingroup": str|None}}."""
    out = {}
    for m in DEF.finditer(page):
        name = m.group("name")
        body = m.group("body")
        # the signature runs to the end of the first line; the docstring follows
        flat = _text(body)
        sig = flat.split('"""')[0].strip()
        if not sig.startswith("("):
            continue
        group = INGROUP.search(flat)
        record = {"signature": "%s%s" % (name, sig),
                  "ingroup": group.group(1) if group else None}
        # Overloads repeat the name; keep each distinct signature.
        if name in out:
            prev = out[name]
            forms = prev.get("overloads") or [prev["signature"]]
            if record["signature"] not in forms:
                forms.append(record["signature"])
            prev["overloads"] = forms
            prev["ingroup"] = prev["ingroup"] or record["ingroup"]
        else:
            out[name] = record
    return out


def main(argv):
    src = argv[1] if len(argv) > 1 else URL
    if os.path.exists(src):
        page = open(src, encoding="utf-8", errors="replace").read()
        where = os.path.abspath(src)
    else:
        print("fetching %s" % src)
        with urllib.request.urlopen(src, timeout=120) as fh:
            page = fh.read().decode("utf-8", "replace")
        where = src
    sigs = parse(page)
    if not sigs:
        raise SystemExit("no signatures parsed - the page layout has changed")
    payload = {"_source": where,
               "_note": ("Parameter names and types from CLO's published API list. CLO's "
                         "descriptions are not reproduced; see the source page for those."),
               "functions": sigs}
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, OUT)
    groups = {}
    for rec in sigs.values():
        groups[rec["ingroup"] or "(none)"] = groups.get(rec["ingroup"] or "(none)", 0) + 1
    print("%d functions -> %s" % (len(sigs), OUT))
    for g, n in sorted(groups.items(), key=lambda kv: -kv[1]):
        print("   %-18s %4d" % (g, n))


if __name__ == "__main__":
    main(sys.argv)
