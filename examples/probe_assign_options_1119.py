# -*- coding: utf-8 -*-
"""Which AssignFabricToPattern call actually changes a piece's fabric? Restores everything after."""
import time

from clo_bridge.worker import run, beat


def main(payload):
    import pattern_api
    import fabric_api
    count = pattern_api.GetPatternCount()
    original = [pattern_api.GetPatternPieceFabricIndex(i) for i in range(count)]
    other = next(k for k in range(fabric_api.GetFabricCount(False)) if k != original[1])
    out = {'original1': original[1], 'other': other, 'tries': []}
    variants = [
        ('3arg opt0', lambda i: fabric_api.AssignFabricToPattern(other, i, 0)),
        ('3arg opt1', lambda i: fabric_api.AssignFabricToPattern(other, i, 1)),
        ('3arg opt2', lambda i: fabric_api.AssignFabricToPattern(other, i, 2)),
        ('4arg cw0 opt0', lambda i: fabric_api.AssignFabricToPattern(0, other, i, 0)),
        ('4arg cw0 opt1', lambda i: fabric_api.AssignFabricToPattern(0, other, i, 1)),
        ('3arg opt0 x2', lambda i: (fabric_api.AssignFabricToPattern(other, i, 0), fabric_api.AssignFabricToPattern(other, i, 0))[-1]),
    ]
    for label, call in variants:
        i = 1
        pattern_api.SetPatternPieceFabricIndex(i, original[i])
        beat(label)
        try:
            t0 = time.perf_counter(); ret = call(i); seconds = time.perf_counter() - t0
            readback = pattern_api.GetPatternPieceFabricIndex(i)
            out['tries'].append({'variant': label, 'ret': ret, 'seconds': round(seconds, 4),
                                 'readback': readback, 'tookEffect': readback == other})
        except Exception as error:
            out['tries'].append({'variant': label, 'error': repr(error)})
    # does the slow call get faster the second time for the same piece? (cache / refresh hypothesis)
    t = []
    for _ in range(3):
        t0 = time.perf_counter(); pattern_api.SetPatternPieceFabricIndex(2, other); t.append(round(time.perf_counter() - t0, 3))
        t0 = time.perf_counter(); pattern_api.SetPatternPieceFabricIndex(2, original[2]); t.append(round(time.perf_counter() - t0, 3))
    out['set_repeat_seconds'] = t
    for i in range(count):
        pattern_api.SetPatternPieceFabricIndex(i, original[i])
    out['restored'] = [pattern_api.GetPatternPieceFabricIndex(i) for i in range(count)] == original
    return out


run(main)
