#!/usr/bin/env python3
'''V19F / user-facing V28H: Dark Matter BSE light -> first-person weapon view.

Root cause:
The BSE light primitive was being created as a generic world renderLight. Doom 3
and Quake 4 both explicitly tag first-person weapon lights with
allowLightInViewID = owner->entityNumber + 1. The Dark Matter core effect surface
already received the equivalent allowSurfaceInViewID + weaponDepthHack treatment,
but its BSE light did not.

Result: the purple core image rendered on the depth-hacked weapon correctly, yet
the dynamic light did not participate as a proper view-weapon light and therefore
did not visibly illuminate the gun model.

This patch extends the existing Q4BSE_SetEntityEffectsViewWeaponMode() API so the
attached BSE light receives the exact same first-person view ID as the effect
surface, then immediately updates any live light handle.

No FX files, radius, tint, fade, texture, electricity, line rendering, lifecycle,
projectile code, or geometry are changed here.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'

if not IMPACT.exists():
    raise SystemExit(f'ERROR: V19F prerequisite missing: {IMPACT}')

text = IMPACT.read_text(encoding='utf-8-sig')

old = '''        instance->renderEntity.weaponDepthHack = true;
        instance->renderEntity.allowSurfaceInViewID = allowSurfaceInViewID;
        instance->renderEntity.noShadow = true;
        instance->renderEntity.noSelfShadow = true;
        instance->renderEntity.forceUpdate = 1;

        if (gameRenderWorld && instance->entityHandle >= 0) {
            gameRenderWorld->UpdateEntityDef(instance->entityHandle, &instance->renderEntity);
        }
        updated = true;'''

new = '''        instance->renderEntity.weaponDepthHack = true;
        instance->renderEntity.allowSurfaceInViewID = allowSurfaceInViewID;
        instance->renderEntity.noShadow = true;
        instance->renderEntity.noSelfShadow = true;
        instance->renderEntity.forceUpdate = 1;

        // Raven / Doom 3 first-person weapon lights are explicitly restricted
        // to the owning player's view. The BSE core surface already used the
        // matching allowSurfaceInViewID, but its dynamic light was left as a
        // generic world light. Mirror the native muzzle/gui-light behavior.
        instance->q4Light.allowLightInViewID = allowSurfaceInViewID;
        instance->q4Light.suppressLightInViewID = 0;

        if (gameRenderWorld && instance->entityHandle >= 0) {
            gameRenderWorld->UpdateEntityDef(instance->entityHandle, &instance->renderEntity);
        }
        if (gameRenderWorld && instance->q4LightHandle >= 0) {
            gameRenderWorld->UpdateLightDef(instance->q4LightHandle, &instance->q4Light);
        }
        updated = true;'''

hits = text.count(old)
if hits != 1:
    raise SystemExit(f'ERROR: V19F expected exactly one view-weapon mode body, found {hits}')

text = text.replace(old, new, 1)

for required in (
    'q4Light.allowLightInViewID = allowSurfaceInViewID',
    'q4Light.suppressLightInViewID = 0',
    'UpdateLightDef(instance->q4LightHandle',
):
    if required not in text:
        raise SystemExit(f'ERROR: V19F verification missing: {required}')

IMPACT.write_text(text, encoding='utf-8')

print('Q4BSE V19F DARK MATTER VIEW-WEAPON LIGHT PASS.')
print('  - BSE core light now uses owner view ID exactly like native weapon lights')
print('  - live light handle updated when view-weapon mode is applied')
print('  - core FX / radius / color / textures / lifecycle untouched')
