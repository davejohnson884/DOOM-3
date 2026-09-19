#!/usr/bin/env python3
'''V18X: Dark Matter CORE-ONLY isolation fix.

Runs after V18U and intentionally does NOT apply V18V/V18W projectile changes.

The previous core updates were path-filtered. The cached BSE effect path can differ
from the DEF string (normalization/extension), so the visible core could start at
its initial transform and then never receive the later exact joint updates. That
matches the observed "stuck in the same wrong place" behavior.

This pass removes path identity from the live transform update for the Dark Matter
weapon:
  * all BSE effects attached to the Dark Matter weapon are stopped together when
    core mode changes (there are no other persistent attached weapon FX here);
  * a new entity-wide transform updater refreshes every attached core instance;
  * the updater is called from the exact final Q4-rendered weapon transform right
    before Present(), using the live inner_ring joint.

No projectile collision, fly-FX, radial-line, impact, suction, or damage behavior
is changed in this pass.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
HEADER = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.h'
WEAPON = ROOT / 'neo' / 'game' / 'Weapon.cpp'

for p in (IMPACT, HEADER, WEAPON):
    if not p.exists():
        raise SystemExit(f'ERROR: V18X prerequisite missing: {p}')

impact = IMPACT.read_text(encoding='utf-8-sig')
header = HEADER.read_text(encoding='utf-8-sig')
weapon = WEAPON.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V18X expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Public entity-wide attached-FX transform updater.
# ---------------------------------------------------------------------------
header = replace_once(
    header,
    '''bool Q4BSE_UpdateEntityEffectTransform(idEntity* entity, const char* fxPath, const idVec3& worldOrigin, const idMat3& worldAxis);
void Q4BSE_StopEntityEffectPath(idEntity* entity, const char* fxPath);''',
    '''bool Q4BSE_UpdateEntityEffectTransform(idEntity* entity, const char* fxPath, const idVec3& worldOrigin, const idMat3& worldAxis);
bool Q4BSE_UpdateEntityEffectsTransform(idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis);
void Q4BSE_StopEntityEffectPath(idEntity* entity, const char* fxPath);''',
    'entity-wide transform API declaration')

api_anchor = '''void Q4BSE_StopEntityEffectPath(idEntity* entity, const char* fxPath) {'''
if impact.count(api_anchor) != 1:
    raise SystemExit(f'ERROR: V18X API implementation anchor count={impact.count(api_anchor)}')

api_impl = r'''bool Q4BSE_UpdateEntityEffectsTransform(idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis) {
    if (!entity || !entity->GetPhysics()) return false;

    const idVec3 attachedOrigin = entity->GetPhysics()->GetOrigin();
    const idMat3 attachedAxis = entity->GetPhysics()->GetAxis();
    const idMat3 attachedAxisTranspose = attachedAxis.Transpose();
    bool updated = false;

    for (size_t i = 0; i < g_m3Impacts.size(); ++i) {
        M3ImpactInstance* instance = g_m3Impacts[i];
        if (!instance->attached || instance->attachedEntity.GetEntity() != entity) {
            continue;
        }

        instance->attachedLocalOrigin = (worldOrigin - attachedOrigin) * attachedAxisTranspose;
        instance->attachedLocalAxis = worldAxis * attachedAxisTranspose;
        instance->attachedLocalTransform = true;

        // Update immediately too; the normal BSE frame service will reconstruct
        // the same values from attachedLocal* on its next service pass.
        instance->origin = worldOrigin;
        instance->axis = worldAxis;
        updated = true;
    }

    return updated;
}

'''
impact = impact.replace(api_anchor, api_impl + api_anchor, 1)


# ---------------------------------------------------------------------------
# When the Dark Matter core mode changes, kill every attached BSE instance on
# the weapon instead of relying on exact string equality for normalized paths.
# ---------------------------------------------------------------------------
old_stop = '''			const char *q4CoreStartFx = weaponDef->dict.GetString( "fx_core_start" );
			const char *q4CoreFx = weaponDef->dict.GetString( "fx_core" );
			if ( q4CoreStartFx && q4CoreStartFx[0] ) Q4BSE_StopEntityEffectPath( this, q4CoreStartFx );
			if ( q4CoreFx && q4CoreFx[0] ) Q4BSE_StopEntityEffectPath( this, q4CoreFx );
			StopSound( SND_CHANNEL_VOICE, false );'''
new_stop = '''			const char *q4CoreStartFx = weaponDef->dict.GetString( "fx_core_start" );
			const char *q4CoreFx = weaponDef->dict.GetString( "fx_core" );
			// Core/core_start are the only persistent BSE effects attached to this
			// weapon. Avoid normalized-path mismatches by clearing them by owner.
			Q4BSE_StopEntityEffects( this );
			StopSound( SND_CHANNEL_VOICE, false );'''
weapon = replace_once(weapon, old_stop, new_stop, 'Dark Matter owner-wide core cleanup')


# ---------------------------------------------------------------------------
# Exact FINAL rendered joint transform, after the source-integrated Q4 viewstyle
# and foreshorten patch has already modified renderEntity.
# ---------------------------------------------------------------------------
present_anchor = '''	// present the model
	if ( showViewModel ) {
		Present();
	} else {
		FreeModelDef();
	}
'''

exact_update = r'''	// Q4 V18X CORE-ONLY: refresh every attached Dark Matter core instance from
	// the live inner_ring using the exact renderEntity that will be drawn below.
	// This intentionally does not identify the effect by path.
	if ( q4PresentationActive && weaponDef && weaponDef->dict.GetBool( "q4_darkmatter_runtime" ) ) {
		const int q4DmgCoreMode = spawnArgs.GetInt( "_q4_dmg_core_mode", "0" );
		if ( q4DmgCoreMode != 0 ) {
			const char *q4CoreJointName = weaponDef->dict.GetString( "joint_core" );
			const jointHandle_t q4CoreJoint = ( q4CoreJointName && q4CoreJointName[0] )
				? animator.GetJointHandle( q4CoreJointName ) : INVALID_JOINT;
			if ( q4CoreJoint != INVALID_JOINT ) {
				idVec3 q4JointLocalOrigin;
				idMat3 q4JointLocalAxis;
				if ( animator.GetJointTransform( q4CoreJoint, gameLocal.time, q4JointLocalOrigin, q4JointLocalAxis ) ) {
					// Position must use the exact foreshortened render axis because that is
					// where the visible gyro geometry is actually drawn.
					const idVec3 q4CoreWorldOrigin = q4JointLocalOrigin * renderEntity.axis + renderEntity.origin;

					// Raven's attached effect orientation is rotational, not foreshortened.
					idMat3 q4EffectBaseAxis = renderEntity.axis;
					const float q4Foreshorten = weaponDef->dict.GetFloat( "foreshorten", "1" );
					if ( idMath::Fabs( q4Foreshorten ) > 0.001f ) {
						q4EffectBaseAxis[0] *= ( 1.0f / q4Foreshorten );
					}
					const idMat3 q4CoreWorldAxis = q4JointLocalAxis * q4EffectBaseAxis;

					Q4BSE_UpdateEntityEffectsTransform( this, q4CoreWorldOrigin, q4CoreWorldAxis );
				}
			}
		}
	}

'''
weapon = replace_once(weapon, present_anchor, exact_update + present_anchor, 'final rendered core transform update')


combined = impact + header + weapon
for required in (
    'Q4BSE_UpdateEntityEffectsTransform',
    'Q4BSE_StopEntityEffects( this )',
    'q4JointLocalOrigin * renderEntity.axis + renderEntity.origin',
    'Q4 V18X CORE-ONLY',
):
    if required not in combined:
        raise SystemExit(f'ERROR: V18X verification missing: {required}')

IMPACT.write_text(impact, encoding='utf-8')
HEADER.write_text(header, encoding='utf-8')
WEAPON.write_text(weapon, encoding='utf-8')

print('Q4BSE V18X DARK MATTER CORE-ONLY ISOLATION PASS.')
print('  - no path filtering for live attached core transform')
print('  - stale attached core/core_start instances cleared by owner')
print('  - core transform refreshed from exact final rendered inner_ring')
print('  - projectile / impact / suction / collision behavior untouched')
