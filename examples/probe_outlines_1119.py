# -*- coding: utf-8 -*-
"""Probe: which pattern pieces have outline points on CLO 2026.1.382? Read-only."""
from clo_bridge.worker import run, beat


def main(payload):
    import pattern_api
    count = pattern_api.GetPatternCount()
    rows = []
    for i in range(count):
        try:
            pts = pattern_api.GetPatternOutlinePoints(i)
            n = len(pts)
            sample = [list(p) for p in list(pts)[:1]]
        except Exception as error:
            n, sample = None, repr(error)
        rows.append({'i': i, 'name': pattern_api.GetPatternPieceName(i), 'points': n, 'sample': sample,
                     'seams': len(set(pattern_api.GetSeamlinePairGroupListInPattern(i)))})
    empty = [r['i'] for r in rows if not r['points']]
    out = {'count': count, 'empty': empty, 'nonEmpty': count - len(empty), 'rows': rows[:45]}
    try:
        out['lineInfo0'] = str(pattern_api.GetPatternLineInfo(0))[:300]
    except Exception as error:
        out['lineInfo0'] = repr(error)
    return out


run(main)
