# -*- coding: utf-8 -*-
"""Probe two speed levers on the scene left open by the Helper verification (TOP 1, 41 pieces).

1. utility_api.GetClothPositions - cloth vertex positions without a file export; if it answers,
   the between-block movement check of the converging comparison can skip the OBJ round trip.
2. fabric_api.AssignFabricToPattern versus pattern_api.SetPatternPieceFabricIndex - per-call time,
   and whether a frozen piece assigns faster. Assignments are restored at the end.
"""
import time

from clo_bridge.worker import run, beat


def main(payload):
    import pattern_api
    import fabric_api
    import utility_api
    out = {'fabricCount': fabric_api.GetFabricCount(False), 'patternCount': pattern_api.GetPatternCount()}

    beat('GetClothPositions')
    reader = getattr(utility_api, 'GetClothPositions', None)
    out['hasGetClothPositions'] = callable(reader)
    if callable(reader):
        for style in ('out-param', 'return'):
            try:
                t0 = time.perf_counter()
                if style == 'out-param':
                    buffer = []
                    ret = reader(buffer)
                    data = buffer if buffer else ret
                else:
                    data = reader([])
                seconds = time.perf_counter() - t0
                n = len(data) if hasattr(data, '__len__') else None
                out['clothPositions_' + style] = {'seconds': round(seconds, 4), 'len': n,
                                                  'type': type(data).__name__,
                                                  'sample': list(data)[:6] if n else None,
                                                  'verticesIfXYZ': (n // 3) if n else None}
            except Exception as error:
                out['clothPositions_' + style] = {'error': repr(error)}

    beat('assignment timing')
    count = out['patternCount']
    original = [pattern_api.GetPatternPieceFabricIndex(i) for i in range(count)]
    out['originalAssignment'] = sorted(set(original))
    other = next((k for k in range(out['fabricCount']) if k != original[0]), None)
    out['otherFabricIndex'] = other
    timings = {}
    if other is not None and count >= 6:
        sample = list(range(1, 6))
        # a) SetPatternPieceFabricIndex, as the Helper does now
        t = []
        for i in sample:
            t0 = time.perf_counter(); pattern_api.SetPatternPieceFabricIndex(i, other); t.append(time.perf_counter() - t0)
        timings['SetPatternPieceFabricIndex'] = [round(x, 3) for x in t]
        # b) AssignFabricToPattern back to the original
        t = []
        for i in sample:
            t0 = time.perf_counter(); r = fabric_api.AssignFabricToPattern(original[i], i, 0); t.append(time.perf_counter() - t0)
        timings['AssignFabricToPattern'] = [round(x, 3) for x in t]
        timings['AssignFabricToPattern_readback_ok'] = all(pattern_api.GetPatternPieceFabricIndex(i) == original[i] for i in sample)
        # c) frozen piece, SetPatternPieceFabricIndex
        t = []
        for i in sample:
            pattern_api.SetPatternFreeze(i, True)
            t0 = time.perf_counter(); pattern_api.SetPatternPieceFabricIndex(i, other); t.append(time.perf_counter() - t0)
            pattern_api.SetPatternFreeze(i, False)
        timings['SetPatternPieceFabricIndex_frozen'] = [round(x, 3) for x in t]
        # d) hidden piece
        t = []
        for i in sample:
            pattern_api.SetPatternHide3D(i, True)
            t0 = time.perf_counter(); pattern_api.SetPatternPieceFabricIndex(i, original[i]); t.append(time.perf_counter() - t0)
            pattern_api.SetPatternHide3D(i, False)
        timings['SetPatternPieceFabricIndex_hidden'] = [round(x, 3) for x in t]
        # restore
        for i in range(count):
            pattern_api.SetPatternPieceFabricIndex(i, original[i])
        timings['restored'] = [pattern_api.GetPatternPieceFabricIndex(i) for i in range(count)] == original
    out['timings'] = timings

    out['cpu'] = {name: getattr(utility_api, name)() for name in ('GetSimulationNumberOfCPUInUse', 'GetSimulationNumberOfSimulation')
                  if callable(getattr(utility_api, name, None))}
    out['simApiNames'] = sorted(n for n in dir(utility_api) if 'Simulation' in n)
    return out


run(main)
