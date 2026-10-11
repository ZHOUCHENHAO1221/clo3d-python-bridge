# -*- coding: utf-8 -*-
"""Measure an exported garment mesh. No CLO, no Windows - so the tests cover it.

This is the half of a sweep that turns a simulation into a number, and it is the half where a
plausible wrong answer is easiest to produce. Two rules are built in because breaking either
yields numbers that look fine and are not:

**Never take the bounding box minimum as the hem.** The lowest vertex of a garment mesh is
whatever happens to hang lowest - a cuff, a tie, a stray welded stitch. The hem is a boundary:
a closed loop of edges that belong to exactly one face each. This module finds boundary loops
and nominates the lowest closed one, which is a different thing and usually a different number.

**It is a candidate, not a hem.** Nothing here knows what the garment is. The nomination is
"the lowest closed boundary loop", and whether that is the hem is for a person to confirm once
per garment. The field is called `lowestClosedLoop` rather than `hem` on purpose.

Units and axis are whatever the OBJ carries. CLO exports Y up in millimetres.
"""
import hashlib
import os
from collections import Counter, defaultdict
from math import dist, isfinite
from statistics import median

# Topology tables are built in Python, so bound the input before it can exhaust memory. An
# exported mesh's size is not predictable from the project that produced it.
MAX_BYTES = 64 * 1024 * 1024
MAX_VERTICES = 250_000
MAX_FACES = 500_000


class MeshTooLarge(ValueError):
    """The mesh is past a limit this module will build tables for."""


class MeshInvalid(ValueError):
    """The file is not a mesh this module can measure."""


def read_obj(path, max_bytes=MAX_BYTES, max_vertices=MAX_VERTICES, max_faces=MAX_FACES):
    """Return (vertices, faces). Faces are lists of 0-based vertex indices."""
    size = os.path.getsize(path)
    if size > max_bytes:
        raise MeshTooLarge("%s is %.1f MB; the limit is %.0f MB"
                           % (path, size / 1048576.0, max_bytes / 1048576.0))
    vertices, faces = [], []
    with open(path, encoding="utf-8", errors="strict") as fh:
        for line in fh:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "v":
                if len(vertices) >= max_vertices:
                    raise MeshTooLarge("more than %d vertices" % max_vertices)
                v = tuple(float(x) for x in parts[1:4])
                if len(v) != 3 or not all(isfinite(x) for x in v):
                    raise MeshInvalid("bad vertex: %r" % line.strip())
                vertices.append(v)
            elif parts[0] == "f":
                if len(faces) >= max_faces:
                    raise MeshTooLarge("more than %d faces" % max_faces)
                face = []
                for token in parts[1:]:
                    i = int(token.split("/")[0])
                    if i == 0:
                        raise MeshInvalid("OBJ vertex indices are 1-based; found 0")
                    face.append(i - 1 if i > 0 else len(vertices) + i)
                if len(face) < 3 or any(i < 0 or i >= len(vertices) for i in face):
                    raise MeshInvalid("face out of range: %r" % line.strip())
                faces.append(face)
    if not vertices or not faces:
        raise MeshInvalid("%s has no mesh" % path)
    return vertices, faces


def _boundary_graph(faces):
    """Edges used by exactly one face are the boundary. Returns (graph, edge_use_counts)."""
    used = Counter()
    for face in faces:
        for i, a in enumerate(face):
            b = face[(i + 1) % len(face)]
            if a != b:
                used[(a, b) if a < b else (b, a)] += 1
    graph = defaultdict(set)
    for (a, b), n in used.items():
        if n == 1:
            graph[a].add(b)
            graph[b].add(a)
    return graph, used


def measure(path, up=1, **limits):
    """Measure the mesh at `path`. `up` is the index of the up axis (1 = Y, CLO's default).

    Returns a dict. The fields worth knowing:

        lowestClosedLoop   the nominated loop, or None. CANDIDATE - confirm it per garment.
        boundaryLoops      every closed loop, lowest first
        openBoundaries     boundary components that are not simple closed loops
        nonManifoldEdges   edges used by more than two faces; non-zero means do not trust a
                           measurement off this mesh without looking at it
        bbox               for sanity checks only. Not a hem. See the module docstring.
        topologySha256     identifies the connectivity, so two meshes can be compared for
                           "same mesh, moved" versus "different mesh"
    """
    vertices, faces = read_obj(path, **limits)
    graph, used = _boundary_graph(faces)

    remaining, components = set(graph), []
    while remaining:
        stack, group = [min(remaining)], set()
        while stack:
            cur = stack.pop()
            if cur in group:
                continue
            group.add(cur)
            remaining.discard(cur)
            stack.extend(graph[cur] - group)
        ids = sorted(group)
        axis = [vertices[i][up] for i in ids]
        # A simple closed loop: at least three vertices, and every one has exactly two
        # boundary neighbours. A figure-of-eight or a torn edge fails this and is reported
        # separately rather than measured.
        closed = len(ids) >= 3 and all(len(graph[i]) == 2 for i in ids)
        components.append({
            "vertices": len(ids), "vertexIds": ids, "closed": closed,
            "min": min(axis), "median": median(axis), "max": max(axis),
            "perimeter": sum(dist(vertices[a], vertices[b]) for a in ids for b in graph[a]) / 2,
        })

    components.sort(key=lambda c: c["median"])
    loops = [c for c in components if c["closed"]]
    openings = [c for c in components if not c["closed"]]

    topo = hashlib.sha256()
    for face in faces:
        topo.update((",".join(map(str, face)) + ";").encode("ascii"))

    return {
        "path": path, "upAxis": up,
        "vertexCount": len(vertices), "faceCount": len(faces),
        "nonManifoldEdges": sum(n > 2 for n in used.values()),
        "boundaryLoops": loops, "openBoundaries": openings,
        "lowestClosedLoop": loops[0] if loops else None,
        "bbox": {"min": [min(v[a] for v in vertices) for a in range(3)],
                 "max": [max(v[a] for v in vertices) for a in range(3)]},
        "topologySha256": topo.hexdigest(),
        "note": "lowestClosedLoop is a candidate. Confirm once per garment that it is the hem.",
    }


def loop_span(measurement, loop=None, axis=0):
    """Width of a loop along `axis` - the hem width, once you have confirmed the loop.

    Separate from measure() because it answers a question about a loop you have chosen, and
    measure() does not choose for you.
    """
    loop = loop or measurement["lowestClosedLoop"]
    if loop is None:
        return None
    vertices, _ = read_obj(measurement["path"])
    xs = [vertices[i][axis] for i in loop["vertexIds"]]
    return max(xs) - min(xs)


def largest_surface(source, target, min_share=0.9, max_island=0.001):
    """Write the largest connected surface of `source` to `target`, or refuse.

    An exported garment can arrive as several disconnected shells: the garment, plus whatever
    was welded in. Measuring the lot gives boundary loops that belong to no single piece. This
    keeps the biggest surface by area and REFUSES rather than guessing when what it would be
    discarding is not obviously debris - another garment, a detached lining, a large pocket.

    Refusing is the point. Silently dropping half a garment produces a clean-looking number.
    """
    vertices, faces = read_obj(source)
    parent = list(range(len(vertices)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for face in faces:
        a = root(face[0])
        for i in face[1:]:
            parent[root(i)] = a

    areas = defaultdict(float)
    for face in faces:
        k, o = root(face[0]), vertices[face[0]]
        for j in range(1, len(face) - 1):
            b = [vertices[face[j]][i] - o[i] for i in range(3)]
            c = [vertices[face[j + 1]][i] - o[i] for i in range(3)]
            cr = (b[1] * c[2] - b[2] * c[1], b[2] * c[0] - b[0] * c[2], b[0] * c[1] - b[1] * c[0])
            areas[k] += (sum(x * x for x in cr)) ** 0.5 / 2

    main = max(areas, key=areas.get)
    total = sum(areas.values())
    others = [a for k, a in areas.items() if k != main]
    if not total or areas[main] / total < min_share or (
            others and max(others) > areas[main] * max_island):
        raise MeshInvalid(
            "the mesh is in several substantial pieces (largest is %.1f%% of the total area) "
            "and this cannot tell cloth from trim. Look at it rather than measuring it."
            % (100.0 * areas[main] / total if total else 0.0))

    keep = [f for f in faces if root(f[0]) == main]
    ids = sorted({i for f in keep for i in f})
    remap = {v: i + 1 for i, v in enumerate(ids)}
    tmp = str(target) + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as out:
        out.write("# largest connected surface; original vertex coordinates retained\n")
        for i in ids:
            out.write("v %s\n" % " ".join(repr(x) for x in vertices[i]))
        for f in keep:
            out.write("f %s\n" % " ".join(str(remap[i]) for i in f))
    os.replace(tmp, target)
    return {"sourceVertices": len(vertices), "sourceFaces": len(faces),
            "vertices": len(ids), "faces": len(keep),
            "areaShare": areas[main] / total, "discardedComponents": len(areas) - 1}
