#!/usr/bin/env python3
"""Small V10 build-tree correction after promote_q4bse_gameplay.py.

The manual q4bse_m3_impact diagnostic command lives inside the implementation
namespace, while Q4BSE_PlayEffect is defined later as the public gameplay API.
Use the already-visible private StartEffectAt helper for that diagnostic path.
The real idProjectile::Collide integration continues to use Q4BSE_PlayEffect.
"""
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"
PROJECTILE = ROOT / "neo" / "game" / "Projectile.cpp"

if not IMPACT.exists() or not PROJECTILE.exists():
    raise SystemExit("ERROR: V10 gameplay promotion must run before this correction")

text = IMPACT.read_text(encoding="utf-8-sig")
old = '    Q4BSE_PlayEffect(g_m3DefaultImpact->path.c_str(), trace.point + trace.normal * 0.15f, trace.normal);'
new = '    StartEffectAt(&g_m3DefaultImpact->effect, g_m3DefaultImpact->path.c_str(), trace.point + trace.normal * 0.15f, trace.normal);'

hits = text.count(old)
if hits != 1:
    raise SystemExit(f"ERROR: expected exactly one diagnostic Q4BSE_PlayEffect call, found {hits}")
text = text.replace(old, new, 1)
IMPACT.write_text(text, encoding="utf-8")

projectile = PROJECTILE.read_text(encoding="utf-8-sig")
if 'Q4BSE_PlayEffect( q4bseImpactFx' not in projectile:
    raise SystemExit("ERROR: real projectile gameplay API hook is missing")

print("Q4BSE V10 diagnostic compile correction PASS.")
print("  - manual command calls private StartEffectAt")
print("  - idProjectile::Collide still calls public Q4BSE_PlayEffect")
