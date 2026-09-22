#!/usr/bin/env python3
'''V19H / user-facing V37: Dark Matter projectile motion parity.

Runs after V19G.

Restores two Raven rvDarkMatterProjectile behavior details that generic Doom 3
idProjectile does not guarantee for this port:
  - +X forward projectile axis, matching Q4 effect authoring;
  - constant 250 u/s flight with a solid-only collision mask, matching the
    Q4 DMG projectile's zero-friction / MASK_DMGSOLID behavior.

Also corrects the travelling RadiusDamage ignorePush argument to Raven's NULL.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PROJECTILE = ROOT / 'neo' / 'game' / 'Projectile.cpp'
if not PROJECTILE.exists():
    raise SystemExit(f'ERROR: missing Projectile.cpp: {PROJECTILE}')

text = PROJECTILE.read_text(encoding='utf-8-sig')

def replace_once(old, new, label):
    global text
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V19H expected exactly one {label}, found {hits}')
    text = text.replace(old, new, 1)

# Raven rvDarkMatterProjectile::Think() sets MASK_DMGSOLID before base Think.
# Doom 3 has no CONTENTS_LARGESHOTCLIP, so MASK_SOLID is the closest exact
# available subset. Also explicitly preserve the authored constant speed so
# generic rigid-body quirks cannot make the ball visibly decelerate.
anchor = '''	if ( thinkFlags & TH_THINK ) {
		if ( thrust && ( gameLocal.time < thrust_end ) ) {
			// evaluate force
			thruster.SetForce( GetPhysics()->GetAxis()[ 0 ] * thrust );
			thruster.Evaluate( gameLocal.time );
		}
	}

	// run physics
	RunPhysics();
'''
replacement = '''	if ( thinkFlags & TH_THINK ) {
		if ( thrust && ( gameLocal.time < thrust_end ) ) {
			// evaluate force
			thruster.SetForce( GetPhysics()->GetAxis()[ 0 ] * thrust );
			thruster.Evaluate( gameLocal.time );
		}
	}

	// Q4 Dark Matter flight parity. Raven's rvDarkMatterProjectile keeps the
	// DMG on a zero-friction constant-speed path and replaces the normal shot
	// mask with MASK_DMGSOLID each Think. Doom 3 lacks LARGESHOTCLIP, so use
	// solid-only collision and explicitly preserve the authored speed.
	if ( state == LAUNCHED && spawnArgs.GetBool( "q4_darkmatter_projectile" ) ) {
		physicsObj.SetClipMask( MASK_SOLID );

		idVec3 q4DMGDirection = physicsObj.GetLinearVelocity();
		if ( q4DMGDirection.Normalize() > 0.001f ) {
			const float q4DMGSpeed = spawnArgs.GetFloat( "q4_constant_speed", "250" );
			physicsObj.SetLinearVelocity( q4DMGDirection * q4DMGSpeed );

			// Q4 projectile/effect content is authored with local +X forward.
			if ( spawnArgs.GetBool( "q4_projectile_forward_x" ) ) {
				physicsObj.SetAxis( q4DMGDirection.ToMat3() );
			}
		}
	}

	// run physics
	RunPhysics();
'''
replace_once(anchor, replacement, 'Dark Matter pre-physics motion hook')

old_radius = '''				gameLocal.RadiusDamage(
					GetPhysics()->GetOrigin(),
					this,
					owner.GetEntity(),
					owner.GetEntity(),
					owner.GetEntity(),
					q4RadiusDamage,
					1.0f );'''
new_radius = '''				gameLocal.RadiusDamage(
					GetPhysics()->GetOrigin(),
					this,
					owner.GetEntity(),
					owner.GetEntity(),
					NULL,
					q4RadiusDamage,
					1.0f );'''
replace_once(old_radius, new_radius, 'Raven RadiusDamage ignorePush parity')

for required in (
    'q4_constant_speed',
    'physicsObj.SetClipMask( MASK_SOLID )',
    'q4_projectile_forward_x',
    'physicsObj.SetAxis( q4DMGDirection.ToMat3() )',
):
    if required not in text:
        raise SystemExit(f'ERROR: V19H verification missing: {required}')

PROJECTILE.write_text(text, encoding='utf-8')
print('Q4BSE V19H DARK MATTER MOTION PARITY.')
print('  - solid-only Raven-like DMG collision mask')
print('  - explicit constant-speed flight')
print('  - +X-forward effect/projectile axis kept aligned to travel')
print('  - Raven RadiusDamage ignorePush=NULL restored')
