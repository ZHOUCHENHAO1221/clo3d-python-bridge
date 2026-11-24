# -*- coding: utf-8 -*-
"""Probe: why does pattern_api.ExportPatternJSON return False on CLO 2026.1.382?

Read-only apart from writing JSON files to the paths in the payload. Does not change the scene.
"""
import os

from clo_bridge.api import require
from clo_bridge.worker import run, beat


def main(payload):
    import pattern_api
    import utility_api
    out = {}
    out['project'] = utility_api.GetProjectFilePath()
    out['version'] = [getattr(utility_api, n, lambda: None)() for n in ('GetMajorVersion', 'GetMinorVersion', 'GetPatchVersion')]
    count = pattern_api.GetPatternCount()
    out['count'] = count
    out['names'] = [pattern_api.GetPatternPieceName(i) for i in range(min(3, count))]
    out['api_names'] = sorted(n for n in dir(pattern_api) if 'Outline' in n or 'JSON' in n or 'Json' in n or 'Export' in n)
    reader = getattr(pattern_api, 'GetPatternOutlinePoints', None)
    out['has_outline_reader'] = callable(reader)
    if callable(reader):
        try:
            pts = reader(0)
            out['outline0'] = {'type': type(pts).__name__, 'len': len(pts) if hasattr(pts, '__len__') else None,
                               'sample': [list(p) if hasattr(p, '__iter__') else p for p in list(pts)[:2]]}
        except Exception as error:
            out['outline0_error'] = repr(error)
    for label, path in payload['paths'].items():
        beat('export ' + label)
        try:
            ret = pattern_api.ExportPatternJSON(path)
            out['export_' + label] = {'ret': ret, 'exists': os.path.exists(path),
                                      'size': os.path.getsize(path) if os.path.exists(path) else None}
        except Exception as error:
            out['export_' + label] = {'error': repr(error)}
    return out


run(main)
