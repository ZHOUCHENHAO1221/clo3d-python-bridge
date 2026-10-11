# -*- coding: utf-8 -*-
"""Mesh measurement tests. No CLO, no Windows - the shapes are built here.

Each shape is chosen to break a specific wrong implementation:

  open tube      the bbox minimum and the lowest boundary loop are DIFFERENT numbers, so an
                 implementation that returns the bbox passes on nothing else and fails here
  closed box     no boundary at all; a hem must not be invented
  torn tube      a boundary that is not a simple loop must be reported, not measured
  two tubes      largest_surface must refuse rather than silently keep one

    python tests/test_mesh.py      # or: pytest tests
"""
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from clo_bridge import mesh  # noqa: E402


def write_obj(vertices, faces, name="m.obj"):
    path = os.path.join(tempfile.mkdtemp(), name)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for v in vertices:
            fh.write("v %s\n" % " ".join(repr(float(x)) for x in v))
        for f in faces:
            fh.write("f %s\n" % " ".join(str(i + 1) for i in f))
    return path


def tube(y_bottom, y_top, radius=10.0, segments=12, dip=None, x_offset=0.0):
    """An open cylinder: two boundary loops, one at each end.

    `dip` replaces one wall quad with four triangles around a new centre vertex and puts that
    vertex at the given height. The centre is INTERIOR - every edge touching it is shared by
    two triangles - so it drags the bounding box down while belonging to no boundary loop. It
    is the fold of cloth that makes a bbox-based hem wrong.

    An earlier version of this helper hung the extra vertex off the bottom edge instead. That
    turns two hem edges into interior edges and splices the vertex INTO the hem loop, so the
    loop minimum moves with it and the test it was written for passes for the wrong reason.
    """
    verts, faces = [], []
    for level in (y_bottom, y_top):
        for s in range(segments):
            a = 2 * math.pi * s / segments
            verts.append((x_offset + radius * math.cos(a), level, radius * math.sin(a)))
    for s in range(segments):
        n = (s + 1) % segments
        faces.append([s, n, segments + n, segments + s])
    if dip is not None:
        quad = faces.pop(0)
        verts.append((x_offset + radius, dip, 0.0))
        c = len(verts) - 1
        for i in range(4):
            faces.append([quad[i], quad[(i + 1) % 4], c])
    return verts, faces


def test_lowest_closed_loop_is_not_the_bounding_box():
    """The headline rule. A fold dips 50 mm below the hem; the hem is still at 0."""
    path = write_obj(*tube(0.0, 100.0, dip=-50.0))
    m = mesh.measure(path)
    assert m["bbox"]["min"][1] == -50.0, m["bbox"]
    loop = m["lowestClosedLoop"]
    assert loop is not None
    assert loop["min"] == 0.0, loop["min"]
    assert loop["vertices"] == 12, loop["vertices"]
    assert abs(m["bbox"]["min"][1] - loop["min"]) == 50.0


def test_both_ends_of_a_tube_are_found_lowest_first():
    m = mesh.measure(write_obj(*tube(0.0, 100.0)))
    assert len(m["boundaryLoops"]) == 2, len(m["boundaryLoops"])
    assert [round(l["median"]) for l in m["boundaryLoops"]] == [0, 100]


def test_perimeter_is_the_loop_not_the_bbox():
    r, n = 10.0, 24
    m = mesh.measure(write_obj(*tube(0.0, 50.0, radius=r, segments=n)))
    expected = 2 * n * r * math.sin(math.pi / n)        # regular n-gon through the circle
    assert abs(m["lowestClosedLoop"]["perimeter"] - expected) < 1e-6


def test_loop_span_measures_the_loop():
    m = mesh.measure(write_obj(*tube(0.0, 50.0, radius=10.0, segments=4)))
    assert abs(mesh.loop_span(m, axis=0) - 20.0) < 1e-9


def test_a_closed_box_has_no_hem_to_find():
    """No boundary edges at all. A hem must not be invented."""
    v = [(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
    i = {p: n for n, p in enumerate(v)}

    def q(a, b, c, d):
        return [i[a], i[b], i[c], i[d]]

    faces = [
        q((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)),
        q((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)),
        q((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)),
        q((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)),
        q((0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)),
        q((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)),
    ]
    m = mesh.measure(write_obj(v, faces))
    assert m["lowestClosedLoop"] is None
    assert m["boundaryLoops"] == []
    assert m["nonManifoldEdges"] == 0


def test_a_hole_in_the_wall_merges_two_loops_into_one():
    """Not an error case - a real behaviour worth knowing, found by this test failing.

    Remove one quad from the tube wall and the two end loops do NOT become open. They join
    into a single closed loop that runs round the hole: every vertex still has exactly two
    boundary neighbours. So a tear between hem and neck leaves one loop spanning both, and
    "the lowest closed loop" silently becomes something that is not the hem.

    Check the loop count, not just that a loop exists.
    """
    verts, faces = tube(0.0, 100.0)
    whole = mesh.measure(write_obj(verts, faces))
    holed = mesh.measure(write_obj(verts, faces[1:]))
    assert len(whole["boundaryLoops"]) == 2
    assert len(holed["boundaryLoops"]) == 1, [l["vertices"] for l in holed["boundaryLoops"]]
    assert holed["boundaryLoops"][0]["vertices"] == 24
    assert holed["openBoundaries"] == []


def test_a_boundary_that_is_not_a_simple_loop_is_reported_not_measured():
    """Two quads meeting at a single vertex. That vertex has four boundary neighbours, so the
    component is not a simple loop and must be kept out of boundaryLoops."""
    v = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),      # quad A, shares vertex 2
         (2, 1, 0), (2, 2, 0), (1, 2, 0)]                 # quad B: 2, 4, 5, 6
    m = mesh.measure(write_obj(v, [[0, 1, 2, 3], [2, 4, 5, 6]]))
    assert m["boundaryLoops"] == [], m["boundaryLoops"]
    assert len(m["openBoundaries"]) == 1
    assert m["lowestClosedLoop"] is None


def test_largest_surface_refuses_two_garments():
    v1, f1 = tube(0.0, 100.0)
    v2, f2 = tube(0.0, 100.0, x_offset=500.0)
    verts = v1 + v2
    faces = f1 + [[i + len(v1) for i in f] for f in f2]
    src = write_obj(verts, faces)
    try:
        mesh.largest_surface(src, src + ".out")
    except mesh.MeshInvalid as exc:
        assert "several substantial pieces" in str(exc)
        assert not os.path.exists(src + ".out"), "nothing may be written on a refusal"
        return
    raise AssertionError("two whole garments must be refused, not silently halved")


def test_largest_surface_drops_only_debris():
    big, fbig = tube(0.0, 100.0, radius=100.0, segments=24)
    spec, fspec = tube(0.0, 1.0, radius=0.05, segments=3, x_offset=900.0)
    verts = big + spec
    faces = fbig + [[i + len(big) for i in f] for f in fspec]
    src = write_obj(verts, faces)
    dst = src + ".out"
    r = mesh.largest_surface(src, dst)
    assert r["discardedComponents"] == 1
    assert r["areaShare"] > 0.999
    kept = mesh.measure(dst)
    assert kept["vertexCount"] == len(big)


def test_topology_hash_separates_moved_from_different():
    a = write_obj(*tube(0.0, 100.0))
    moved = write_obj(*tube(5.0, 105.0))                 # same connectivity, different shape
    other = write_obj(*tube(0.0, 100.0, segments=16))    # different connectivity
    ma, mm, mo = (mesh.measure(p) for p in (a, moved, other))
    assert ma["topologySha256"] == mm["topologySha256"]
    assert ma["topologySha256"] != mo["topologySha256"]


def test_a_bad_face_index_is_refused():
    try:
        mesh.measure(write_obj([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [[0, 1, 99]]))
    except mesh.MeshInvalid:
        return
    raise AssertionError("a face pointing past the vertex list must be refused")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print("  ok  %s" % fn.__name__)
    print("\n%d passed" % len(tests))
