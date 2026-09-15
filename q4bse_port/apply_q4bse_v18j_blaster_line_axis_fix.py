#!/usr/bin/env python3
'''V18J: correct Raven Blaster useEndOrigin world->local transform.

V18I introduced endpoint-driven line FX for the original Q4 Blaster hitscan
trail, but converted the world endpoint with vector * axis.Transpose(). The M3
runtime itself renders local particle position/length as axis * local, so the
inverse conversion must use axis.Transpose() * worldVector.

This pass is intentionally one-line/surgical. It does not touch projectile BSE
ownership, attached fly FX, muzzle attachment, Nailgun impact behavior, or any
other weapon path.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'

if not IMPACT.exists():
    raise SystemExit(f'ERROR: V18J missing cumulative BSE runtime: {IMPACT}')

text = IMPACT.read_text(encoding='utf-8-sig')
old = 'const idVec3 endpointLocal = (g_m3EndOrigin - g_m3Impact.origin) * g_m3Impact.axis.Transpose();'
new = 'const idVec3 endpointLocal = g_m3Impact.axis.Transpose() * (g_m3EndOrigin - g_m3Impact.origin);'

hits = text.count(old)
if hits != 1:
    raise SystemExit(f'ERROR: V18J expected exactly one V18I endpoint transform, found {hits}')
text = text.replace(old, new, 1)

for required in (
    'startLength->useEndOrigin && g_m3UseEndOrigin',
    'Q4BSE_PlayEffectBetween',
    new,
):
    if required not in text:
        raise SystemExit(f'ERROR: V18J verification missing: {required}')

for forbidden in (
    '!q4UseD3ImpactVisuals && ( q4bseImpactFx && *q4bseImpactFx )',
    'const bool q4UseD3ImpactVisuals = spawnArgs.GetBool( "q4UseD3ImpactVisuals" );',
):
    if forbidden in text:
        raise SystemExit(f'ERROR: V18J found stale V18G ownership override: {forbidden}')

IMPACT.write_text(text, encoding='utf-8')

print('Q4BSE V18J BLASTER LINE AXIS FIX PASS.')
print('  - useEndOrigin world endpoint now uses the exact inverse of axis * local rendering')
print('  - Raven trail.fx endpoint should land on the real trace hit')
print('  - projectile fly/muzzle/impact ownership untouched')
print('  - Nailgun / MG / Shotgun / GL paths untouched')
