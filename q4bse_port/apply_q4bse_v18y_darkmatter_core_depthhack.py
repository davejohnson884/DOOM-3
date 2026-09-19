#!/usr/bin/env python3
'''V18Y: Dark Matter CORE-ONLY view-weapon projection parity.

Runs after V18X. No projectile/impact/collision/suction changes.

Root cause addressed:
Doom 3 first-person weapons are submitted with renderEntity.weaponDepthHack=true,
which changes the projection matrix as well as the depth range. The Q4BSE core
was a separate ordinary world renderEntity, so even a mathematically correct
inner_ring world transform could not line up on screen with the depth-hacked gun.

This pass marks only BSE effects attached to the Dark Matter weapon as
view-weapon surfaces:
  * weaponDepthHack = true
  * allowSurfaceInViewID = owner entity number + 1

The core still receives the live inner_ring transform from V18X. This pass only
makes the renderer project that effect in the same first-person space as the gun.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
HEADER = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.h'
WEAPON = ROOT / 'neo' / 'game' / 'Weapon.cpp'

for p in (IMPACT, HEADER, WEAPON):
    if not p.exists():
        raise SystemExit(f'ERROR: V18Y prerequisite missing: {p}')

impact = IMPACT.read_text(encoding='utf-8-sig')
header = HEADER.read_text(encoding='utf-8-sig')
weapon = WEAPON.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V18Y expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)


header = replace_once(
    header,
    '''bool Q4BSE_UpdateEntityEffectsTransform(idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis);
void Q4BSE_StopEntityEffectPath(idEntity* entity, const char* fxPath);''',
    '''bool Q4BSE_UpdateEntityEffectsTransform(idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis);
bool Q4BSE_SetEntityEffectsViewWeaponMode(idEntity* entity, int allowSurfaceInViewID);
void Q4BSE_StopEntityEffectPath(idEntity* entity, const char* fxPath);''',
    'view-weapon BSE API declaration')

api_anchor = '''void Q4BSE_StopEntityEffectPath(idEntity* entity, const char* fxPath) {'''
if impact.count(api_anchor) != 1:
    raise SystemExit(f'ERROR: V18Y API implementation anchor count={impact.count(api_anchor)}')

api_impl = r'''bool Q4BSE_SetEntityEffectsViewWeaponMode(idEntity* entity, int allowSurfaceInViewID) {
    if (!entity) return false;
    bool updated = false;

    for (size_t i = 0; i < g_m3Impacts.size(); ++i) {
        M3ImpactInstance* instance = g_m3Impacts[i];
        if (!instance->attached || instance->attachedEntity.GetEntity() != entity) {
            continue;
        }

        instance->renderEntity.weaponDepthHack = true;
        instance->renderEntity.allowSurfaceInViewID = allowSurfaceInViewID;
        instance->renderEntity.noShadow = true;
        instance->renderEntity.noSelfShadow = true;
        instance->renderEntity.forceUpdate = 1;

        if (gameRenderWorld && instance->entityHandle >= 0) {
            gameRenderWorld->UpdateEntityDef(instance->entityHandle, &instance->renderEntity);
        }
        updated = true;
    }

    return updated;
}

'''
impact = impact.replace(api_anchor, api_impl + api_anchor, 1)

# Call this immediately after the V18X exact core transform update. It is harmless
# to repeat every frame and guarantees a newly-created core/core_start receives
# the view-weapon projection flags on its first presented frame.
call_anchor = '''					Q4BSE_UpdateEntityEffectsTransform( this, q4CoreWorldOrigin, q4CoreWorldAxis );
'''
call_new = '''					Q4BSE_UpdateEntityEffectsTransform( this, q4CoreWorldOrigin, q4CoreWorldAxis );
					Q4BSE_SetEntityEffectsViewWeaponMode( this, owner ? owner->entityNumber + 1 : 0 );
'''
weapon = replace_once(weapon, call_anchor, call_new, 'view-weapon mode call')

combined = impact + header + weapon
for required in (
    'Q4BSE_SetEntityEffectsViewWeaponMode',
    'renderEntity.weaponDepthHack = true',
    'renderEntity.allowSurfaceInViewID = allowSurfaceInViewID',
    'owner ? owner->entityNumber + 1 : 0',
):
    if required not in combined:
        raise SystemExit(f'ERROR: V18Y verification missing: {required}')

IMPACT.write_text(impact, encoding='utf-8')
HEADER.write_text(header, encoding='utf-8')
WEAPON.write_text(weapon, encoding='utf-8')

print('Q4BSE V18Y DARK MATTER CORE VIEW-WEAPON PROJECTION PASS.')
print('  - core BSE renderEntity now uses Doom 3 weaponDepthHack')
print('  - core BSE surface restricted to the owning first-person view')
print('  - live inner_ring transform remains V18X-owned')
print('  - projectile/impact/collision/suction untouched')
