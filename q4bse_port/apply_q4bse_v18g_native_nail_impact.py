#!/usr/bin/env python3
'''V18G: let selected BSE projectiles keep Raven flight/muzzle FX but use Doom 3 impact presentation.

Opt-in spawnarg:
    q4UseD3ImpactVisuals 1

When enabled on a projectile that still declares Raven fx_impact* keys:
  * the Raven/BSE collision effect is NOT spawned;
  * q4bseOwnsImpactVisual becomes false, so Doom 3 AddDefaultDamageEffect runs;
  * the existing V18F audio bridge is naturally bypassed because it only executes
    inside the BSE-owned impact branch, preventing duplicate surface sounds;
  * Explode() no longer suppresses Doom 3 model_detonate/model_smokespark/model_smoke
    selection for the opted-in projectile;
  * Raven BSE fly FX, muzzle FX, parser/runtime, GUI, brass, and all other weapon
    presentation remain untouched.

This is intentionally an opt-in collision ownership switch rather than deleting
fx_impact* spawnargs. The Nailgun keeps its proven BSE wiring intact.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PROJECTILE = ROOT / "neo" / "game" / "Projectile.cpp"

if not PROJECTILE.exists():
    raise SystemExit(f"ERROR: V18G missing Projectile.cpp: {PROJECTILE}")

text = PROJECTILE.read_text(encoding="utf-8-sig")

# Collide(): retain the resolved Raven effect and all BSE plumbing, but allow an
# opted-in projectile to decline BSE ownership of the collision presentation.
old_collide = '\tconst bool q4bseOwnsImpactVisual = ( q4bseImpactFx && *q4bseImpactFx );\n'
new_collide = (
    '\tconst bool q4UseD3ImpactVisuals = spawnArgs.GetBool( "q4UseD3ImpactVisuals" );\n'
    '\tconst bool q4bseOwnsImpactVisual = !q4UseD3ImpactVisuals && ( q4bseImpactFx && *q4bseImpactFx );\n'
)

hits = text.count(old_collide)
if hits != 1:
    raise SystemExit(f"ERROR: V18G expected one Collide BSE ownership line, found {hits}")
text = text.replace(old_collide, new_collide, 1)

# Explode(): the generic BSE finalizer also suppresses Doom 3's impact particle
# model whenever fx_impact/fx_impact_default exists. The opt-in must override
# that suppression without removing those Raven keys from the projectile def.
old_explode = '''\tconst bool q4bseOwnsImpactVisual =
\t\tspawnArgs.GetString( "fx_impact" )[0] ||
\t\tspawnArgs.GetString( "fx_impact_default" )[0];
'''
new_explode = '''\tconst bool q4UseD3ImpactVisuals = spawnArgs.GetBool( "q4UseD3ImpactVisuals" );
\tconst bool q4bseOwnsImpactVisual =
\t\t!q4UseD3ImpactVisuals &&
\t\t( spawnArgs.GetString( "fx_impact" )[0] ||
\t\t  spawnArgs.GetString( "fx_impact_default" )[0] );
'''

hits = text.count(old_explode)
if hits != 1:
    raise SystemExit(f"ERROR: V18G expected one Explode BSE ownership block, found {hits}")
text = text.replace(old_explode, new_explode, 1)

# Safety checks: V18F must still be present, and the stock D3 damage-effect gate
# must remain keyed from q4bseOwnsImpactVisual so this switch actually hands
# collision presentation back to the native path.
required = (
    'spawnArgs.GetBool( "q4UseD3ImpactVisuals" )',
    '!q4UseD3ImpactVisuals && ( q4bseImpactFx && *q4bseImpactFx )',
    '!q4UseD3ImpactVisuals &&',
    'else if ( !q4bseOwnsImpactVisual )',
    '!q4bseOwnsImpactVisual && !( fxname && *fxname )',
    'spawnArgs.GetBool( "q4UseD3ImpactAudio" )',
)
for needle in required:
    if needle not in text:
        raise SystemExit(f"ERROR: V18G verification missing: {needle}")

PROJECTILE.write_text(text, encoding="utf-8")

print("Q4BSE V18G NATIVE IMPACT OWNERSHIP PASS.")
print("  - q4UseD3ImpactVisuals opt-in suppresses ONLY Raven collision FX")
print("  - Raven BSE muzzle/fly/runtime wiring is untouched")
print("  - Doom 3 AddDefaultDamageEffect owns opted-in world decals + surface audio")
print("  - Doom 3 Explode impact particle selection is restored for opted-in projectiles")
print("  - existing V18F BSE surface-audio bridge is bypassed for opted-in impacts")
