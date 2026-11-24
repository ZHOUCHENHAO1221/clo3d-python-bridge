# -*- coding: utf-8 -*-
"""The pure-Python helpers in examples 06 and 07. No CLO.

    python tests/test_examples.py
"""
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = os.path.join(os.path.dirname(HERE), "examples")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(EXAMPLES, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pieces_sharing_a_seam_are_one_group():
    scope = _load("07_garment_scope")
    # 0-1 share seam 5, 1-2 share seam 7, 3 is sewn to nothing, 4-5 share seam 9
    seams = {0: [5], 1: [5, 7], 2: [7], 3: [], 4: [9], 5: [9]}
    assert scope.seam_groups(seams) == [[0, 1, 2], [3], [4, 5]], scope.seam_groups(seams)


def test_movement_is_reported_per_group():
    still = _load("06_simulate_until_still")
    path = os.path.join(tempfile.mkdtemp(), "a.obj")

    def write(dy):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("g big\nv 0 0 0\nv 1 0 0\nv 0 1 0\nv 1 1 0\nf 1 2 3\nf 2 4 3\n")
            fh.write("g small\nv 5 %s 0\nv 6 %s 0\nv 5 %s 1\nf 5 6 7\n" % (dy, dy, dy))
        return still.read_groups(path)

    mean, per_group = still.movement(write(0), write(2))
    assert per_group == {"big": 0.0, "small": 2.0}, per_group
    assert abs(mean - 6.0 / 7) < 1e-9, mean          # the mean hides the piece still moving


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print("  ok  %s" % fn.__name__)
    print("\n%d passed" % len(tests))
