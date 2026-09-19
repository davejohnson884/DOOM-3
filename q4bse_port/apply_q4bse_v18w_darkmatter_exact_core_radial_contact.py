#!/usr/bin/env python3
'''V18W: Dark Matter exact presented-joint core, radial generated lengths, and hard contact detonation.

Runs after V18V. Scoped to the Dark Matter/BFG port. No suction/radius loop.

Fixes three V4 misses:
  1) core attachment now uses the ACTUAL Q4-transformed renderEntity origin/axis
     that is submitted for the first-person weapon, instead of recreating that
     transform earlier from viewWeaponOrigin/viewWeaponAxis;
  2) generatedNormal now rotates authored line/electricity length for Dark
     Matter FX, so black streaks, tiny streaks and lightning radiate out from
     their sampled sphere normals instead of stacking in one effect-axis plane;
  3) Dark Matter checks current rigid-body contacts after physics and routes
     ANY armed solid contact through normal Collide(), rather than waiting for
     a near-zero velocity heuristic that misses wedged/glancing corners.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
WEAPON = ROOT / 'neo' / 'game' / 'Weapon.cpp'
PROJECTILE = ROOT / 'neo' / 'game' / 'Projectile.cpp'

for p in (IMPACT, WEAPON, PROJECTILE):
    if not p.exists():
        raise SystemExit(f'ERROR: V18W prerequisite missing: {p}')

impact = IMPACT.read_text(encoding='utf-8-sig')
weapon = WEAPON.read_text(encoding='utf-8-sig')
projectile = PROJECTILE.read_text(encoding='utf-8-sig')

def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V18W expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# Raven generatedNormal parity for Dark Matter line/electricity LENGTH.
# V18N already stores p.generatedNormal. V18T transformed velocity/acceleration
# but left line length in raw effect X, which is why DM radial streaks/bolts
# could read like stacked flat/square planes.
# ---------------------------------------------------------------------------
line_old = '''    if (pt.primitive == "line") {
        const float width = EvalFloat(p.sizeStart.x, p.sizeEnd.x, FindDomain(pt.motion, "size"), life);
        const idVec3 localLength = EvalVec3(p.lengthStart, p.lengthEnd, FindDomain(pt.motion, "length"), life);
        const idVec3 length = g_m3Impact.axis * localLength;'''
line_new = '''    if (pt.primitive == "line") {
        const float width = EvalFloat(p.sizeStart.x, p.sizeEnd.x, FindDomain(pt.motion, "size"), life);
        idVec3 localLength = EvalVec3(p.lengthStart, p.lengthEnd, FindDomain(pt.motion, "length"), life);
        if (p.hasGeneratedNormal &&
            g_m3Impact.effectPath.find("effects/weapons/dmg/") != std::string::npos) {
            localLength = p.generatedNormal.ToMat3() * localLength;
        }
        const idVec3 length = g_m3Impact.axis * localLength;'''
impact = replace_once(impact, line_old, line_new, 'Dark Matter generatedNormal line length')

elec_old = '''        const idVec3 localLength = EvalVec3(p.lengthStart, p.lengthEnd, FindDomain(pt.motion, "length"), life);
        const idVec3 worldLength = g_m3Impact.axis * localLength;
        const idVec3 end = worldPos + worldLength;'''
elec_new = '''        idVec3 localLength = EvalVec3(p.lengthStart, p.lengthEnd, FindDomain(pt.motion, "length"), life);
        if (p.hasGeneratedNormal &&
            g_m3Impact.effectPath.find("effects/weapons/dmg/") != std::string::npos) {
            localLength = p.generatedNormal.ToMat3() * localLength;
        }
        const idVec3 worldLength = g_m3Impact.axis * localLength;
        const idVec3 end = worldPos + worldLength;'''
impact = replace_once(impact, elec_old, elec_new, 'Dark Matter generatedNormal electricity length')

# ---------------------------------------------------------------------------
# Core transform: update from the exact renderEntity transform AFTER the source
# Q4 presentation patch has applied viewoffset/viewangles/foreshorten and before
# the model is submitted. Position uses the foreshortened render axis just like
# Raven GetGlobalJointTransform; effect orientation removes only the forward
# foreshorten because Raven does not scale attached effect axes.
# ---------------------------------------------------------------------------
present_anchor = '''	// present the model
	if ( showViewModel ) {
		Present();
	} else {
		FreeModelDef();
	}
'''
core_exact = r'''	// Q4 V18W: Dark Matter core uses the exact first-person transform that is
	// about to be submitted to the renderer. This avoids reconstructing Raven's
	// view transform earlier and keeps the effect centered in the physical rings.
	if ( q4PresentationActive && weaponDef && weaponDef->dict.GetBool( "q4_darkmatter_runtime" ) ) {
		const int q4DmgCoreMode = spawnArgs.GetInt( "_q4_dmg_core_mode", "0" );
		if ( q4DmgCoreMode != 0 ) {
			const char *q4CoreFx = ( q4DmgCoreMode == 1 )
				? weaponDef->dict.GetString( "fx_core_start" )
				: weaponDef->dict.GetString( "fx_core" );
			const char *q4CoreJointName = weaponDef->dict.GetString( "joint_core" );
			const jointHandle_t q4CoreJoint = ( q4CoreJointName && q4CoreJointName[0] )
				? animator.GetJointHandle( q4CoreJointName ) : INVALID_JOINT;
			if ( q4CoreJoint != INVALID_JOINT && q4CoreFx && q4CoreFx[0] ) {
				idVec3 q4JointLocalOrigin;
				idMat3 q4JointLocalAxis;
				if ( animator.GetJointTransform( q4CoreJoint, gameLocal.time, q4JointLocalOrigin, q4JointLocalAxis ) ) {
					const idVec3 q4CoreWorldOrigin = q4JointLocalOrigin * renderEntity.axis + renderEntity.origin;
					idMat3 q4EffectBaseAxis = renderEntity.axis;
					const float q4Foreshorten = weaponDef->dict.GetFloat( "foreshorten", "1" );
					if ( idMath::Fabs( q4Foreshorten ) > 0.001f ) {
						q4EffectBaseAxis[0] *= ( 1.0f / q4Foreshorten );
					}
					const idMat3 q4CoreWorldAxis = q4JointLocalAxis * q4EffectBaseAxis;
					Q4BSE_UpdateEntityEffectTransform( this, q4CoreFx, q4CoreWorldOrigin, q4CoreWorldAxis );
				}
			}
		}
	}

'''
weapon = replace_once(weapon, present_anchor, core_exact + present_anchor, 'exact presented Dark Matter core update')

# ---------------------------------------------------------------------------
# Replace V18V's stopped-velocity recovery with direct post-physics contact
# ownership. This is what a detonate-on-contact projectile actually needs:
# if its rigid body is touching world solid after the 80ms muzzle safety window,
# send that real contact through idProjectile::Collide immediately.
# ---------------------------------------------------------------------------
start_marker = '''	// A zero-gravity Dark Matter shot should never naturally come to rest.  If
	// a glancing corner contact leaves the rigid body stopped without a normal
	// projectile detonation callback, recover the actual solid contact and feed
	// it back through the ordinary Collide() path.
'''
start = projectile.find(start_marker)
if start < 0:
    raise SystemExit('ERROR: V18W could not find V18V corner recovery start')
end = projectile.find('\n\tPresent();', start)
if end < 0:
    raise SystemExit('ERROR: V18W could not find Present() after V18V recovery block')

contact_block = r'''	// Q4 V18W: Dark Matter detonates on ANY real world-solid contact after a
	// short muzzle-clear safety window. Raven's rvDarkMatterProjectile changes
	// to MASK_DMGSOLID before base Think; Doom 3's closest mask is MASK_SOLID.
	if ( q4DarkMatterProjectile && state == LAUNCHED ) {
		int q4ContactArmTime = spawnArgs.GetInt( "_q4_dmg_contact_arm_time", "0" );
		if ( q4ContactArmTime == 0 ) {
			q4ContactArmTime = gameLocal.time + spawnArgs.GetInt( "q4_darkmatter_contact_arm_ms", "80" );
			spawnArgs.Set( "_q4_dmg_contact_arm_time", va( "%d", q4ContactArmTime ) );
		}
		if ( gameLocal.time >= q4ContactArmTime ) {
			contactInfo_t q4Contacts[8];
			idVec6 q4ContactDir;
			q4ContactDir.Zero();
			q4ContactDir.SubVec3(0) = physicsObj.GetLinearVelocity();
			if ( q4ContactDir.SubVec3(0).Normalize() < 0.001f ) {
				q4ContactDir.SubVec3(0) = q4DarkMatterPrePhysicsVelocity;
				if ( q4ContactDir.SubVec3(0).Normalize() < 0.001f ) {
					q4ContactDir.SubVec3(0) = physicsObj.GetAxis()[2];
				}
			}
			const int q4NumContacts = gameLocal.clip.Contacts(
				q4Contacts, 8, physicsObj.GetOrigin(), q4ContactDir, 2.0f,
				physicsObj.GetClipModel(), physicsObj.GetAxis(), MASK_SOLID, this );
			if ( q4NumContacts > 0 ) {
				trace_t q4ContactTrace;
				memset( &q4ContactTrace, 0, sizeof( q4ContactTrace ) );
				q4ContactTrace.fraction = 0.0f;
				q4ContactTrace.endpos = physicsObj.GetOrigin();
				q4ContactTrace.endAxis = physicsObj.GetAxis();
				q4ContactTrace.c = q4Contacts[0];
				idVec3 q4ImpactVelocity = q4DarkMatterPrePhysicsVelocity;
				if ( q4ImpactVelocity.LengthSqr() < 1.0f ) {
					q4ImpactVelocity = physicsObj.GetLinearVelocity();
				}
				Collide( q4ContactTrace, q4ImpactVelocity );
			}
		}
	}
'''
projectile = projectile[:start] + contact_block + projectile[end:]

for required in (
    'localLength = p.generatedNormal.ToMat3() * localLength;',
    'Q4 V18W: Dark Matter core uses the exact first-person transform',
    'q4JointLocalOrigin * renderEntity.axis + renderEntity.origin',
    'q4EffectBaseAxis[0] *= ( 1.0f / q4Foreshorten )',
    'q4_darkmatter_contact_arm_ms',
    'gameLocal.clip.Contacts(',
    'q4ContactTrace.c = q4Contacts[0];',
):
    combined = impact + weapon + projectile
    if required not in combined:
        raise SystemExit(f'ERROR: V18W verification missing: {required}')

IMPACT.write_text(impact, encoding='utf-8')
WEAPON.write_text(weapon, encoding='utf-8')
PROJECTILE.write_text(projectile, encoding='utf-8')

print('Q4BSE V18W DARK MATTER PARITY FIX PASS.')
print('  - core transform now comes from the exact Q4-presented renderEntity')
print('  - DM generatedNormal rotates line/electricity length radially')
print('  - armed DM projectile detonates from direct post-physics solid contacts')
print('  - suction/radius-damage loop remains intentionally absent')
