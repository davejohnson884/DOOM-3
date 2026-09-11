#!/usr/bin/env python3
"""Small V10 build-tree correction after promote_q4bse_gameplay.py.

The gameplay promotion intentionally preserves the proven M3 renderer/evaluator and
changes ownership from one global test impact to cached declarations plus independent
live instances.  This post-promotion correction removes a few stale references from the
old single-instance lifecycle and keeps the manual diagnostic command inside the private
implementation namespace.  The real idProjectile::Collide integration continues to use
the public Q4BSE_PlayEffect API.
"""
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"
PROJECTILE = ROOT / "neo" / "game" / "Projectile.cpp"

if not IMPACT.exists() or not PROJECTILE.exists():
    raise SystemExit("ERROR: V10 gameplay promotion must run before this correction")

text = IMPACT.read_text(encoding="utf-8-sig")

# The manual console diagnostic lives inside the implementation namespace, before the
# public Q4BSE_PlayEffect definition.  Call the already-visible private helper there.
old_cmd = '    Q4BSE_PlayEffect(g_m3DefaultImpact->path.c_str(), trace.point + trace.normal * 0.15f, trace.normal);'
new_cmd = '    StartEffectAt(&g_m3DefaultImpact->effect, g_m3DefaultImpact->path.c_str(), trace.point + trace.normal * 0.15f, trace.normal);'
cmd_hits = text.count(old_cmd)
if cmd_hits != 1:
    raise SystemExit(f"ERROR: expected exactly one diagnostic Q4BSE_PlayEffect call, found {cmd_hits}")
text = text.replace(old_cmd, new_cmd, 1)

# The original M3 BeginMap loaded into one global q4bse::Effect object.  V10 removed
# that object in favor of the shared declaration cache, so load the default impact into
# the cache and retain only a pointer to the cached declaration.
old_begin = '    g_m3ImpactLoaded = LoadEffect("effects/weapons/hyperblaster/impact_default.fx", g_m3ImpactEffect);'
new_begin = ('    g_m3DefaultImpact = GetOrLoadEffect("effects/weapons/hyperblaster/impact_default.fx");\n'
             '    g_m3ImpactLoaded = (g_m3DefaultImpact != NULL);')
begin_hits = text.count(old_begin)
if begin_hits != 1:
    raise SystemExit(f"ERROR: expected exactly one stale single-instance BeginMap load, found {begin_hits}")
text = text.replace(old_begin, new_begin, 1)

# EndMap already calls ClearEffectCache(), which releases every cached declaration and
# nulls g_m3DefaultImpact.  Replace the obsolete value-object reset so no reference to
# the deleted g_m3ImpactEffect object survives compilation.
old_end = '    g_m3ImpactEffect = q4bse::Effect();'
new_end = '    g_m3DefaultImpact = NULL;'
end_hits = text.count(old_end)
if end_hits != 1:
    raise SystemExit(f"ERROR: expected exactly one stale single-instance EndMap reset, found {end_hits}")
text = text.replace(old_end, new_end, 1)

if 'g_m3ImpactEffect' in text:
    raise SystemExit("ERROR: stale g_m3ImpactEffect reference remains after V10 correction")

IMPACT.write_text(text, encoding="utf-8")

projectile = PROJECTILE.read_text(encoding="utf-8-sig")
if 'Q4BSE_PlayEffect( q4bseImpactFx' not in projectile:
    raise SystemExit("ERROR: real projectile gameplay API hook is missing")

print("Q4BSE V10 gameplay compile correction PASS.")
print("  - manual command calls private StartEffectAt")
print("  - default HyperBlaster impact loads through the shared FX cache")
print("  - stale single-instance g_m3ImpactEffect lifecycle removed")
print("  - idProjectile::Collide still calls public Q4BSE_PlayEffect")
