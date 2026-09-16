#!/usr/bin/env python3
'''V18K: Quake 4 Rocket Launcher bridges on top of the accepted V18J baseline.

Runs AFTER V18J. Adds two opt-in, data-driven capabilities only:
  * q4_gui_weapon_ammo_event: fire the Raven weapon_ammo named GUI event after
    Doom 3 has refreshed player_ammo/player_totalammo state.
  * q4_projectile_forward_x: preserve a projectile model's authored local +X
    forward axis instead of Doom 3's stock local +Z projectile convention.

Weapons/projectiles without these keys retain stock/V18J behavior byte-for-byte.
No BSE ownership, impact, muzzle, sound, viewmodel, or existing weapon behavior is
changed.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
WEAPON = ROOT / 'neo' / 'game' / 'Weapon.cpp'
PROJECTILE = ROOT / 'neo' / 'game' / 'Projectile.cpp'

for p in (WEAPON, PROJECTILE):
    if not p.exists():
        raise SystemExit(f'ERROR: V18K prerequisite missing: {p}')

weapon = WEAPON.read_text(encoding='utf-8-sig')
projectile = PROJECTILE.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V18K expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Raven weapon GUI named-event bridge.
# Doom 3 already refreshes player_ammo every UpdateGUI(), but Q4 weapon GUIs
# commonly put their visibility logic inside `onNamedEvent weapon_ammo`.
# Keep this opt-in so stock D3 and completed Q4 weapons are untouched.
# ---------------------------------------------------------------------------
gui_anchor = '''\trenderEntity.gui[ 0 ]->SetStateBool( "player_ammo_empty", ( ammoamount == 0 ) );
\trenderEntity.gui[ 0 ]->SetStateBool( "player_clip_empty", ( inclip == 0 ) );
\trenderEntity.gui[ 0 ]->SetStateBool( "player_clip_low", ( inclip <= lowAmmo ) );
}'''

gui_new = '''\trenderEntity.gui[ 0 ]->SetStateBool( "player_ammo_empty", ( ammoamount == 0 ) );
\trenderEntity.gui[ 0 ]->SetStateBool( "player_clip_empty", ( inclip == 0 ) );
\trenderEntity.gui[ 0 ]->SetStateBool( "player_clip_low", ( inclip <= lowAmmo ) );

\t// Q4 V18K: Raven weapon GUIs may update visibility in a named event rather
\t// than directly from state expressions. Fire it only for opted-in weapons,
\t// after all ammo state keys above have been refreshed.
\tif ( weaponDef && weaponDef->dict.GetBool( "q4_gui_weapon_ammo_event" ) ) {
\t\trenderEntity.gui[ 0 ]->HandleNamedEvent( "weapon_ammo" );
\t}
}'''
weapon = replace_once(weapon, gui_anchor, gui_new, 'weapon GUI ammo event hook')


# ---------------------------------------------------------------------------
# Q4 projectile local-forward convention.
# Doom 3's idProjectile converts +X direction into local +Z for its stock
# projectile models. Raven's Q4 rocket.lwo is authored long/forward on local +X.
# Preserve axis=dir.ToMat3() for opted-in projectiles, and launch velocity on
# that same +X axis. This also makes the existing attached BSE fx_fly basis line
# up naturally with the original Raven +X-authored FX.
# ---------------------------------------------------------------------------
axis_old = '''\t// align z-axis of model with the direction
\taxis = dir.ToMat3();
\ttmp = axis[2];
\taxis[2] = axis[0];
\taxis[0] = -tmp;'''

axis_new = '''\t// Doom 3 stock projectiles author model-forward on local +Z. Raven Q4
\t// projectile assets such as rocket.lwo author forward on local +X.
\taxis = dir.ToMat3();
\tif ( !spawnArgs.GetBool( "q4_projectile_forward_x" ) ) {
\t\ttmp = axis[2];
\t\taxis[2] = axis[0];
\t\taxis[0] = -tmp;
\t}'''

axis_hits = projectile.count(axis_old)
if axis_hits != 2:
    raise SystemExit(f'ERROR: V18K expected exactly two projectile axis blocks, found {axis_hits}')
projectile = projectile.replace(axis_old, axis_new)

velocity_old = '''\tphysicsObj.SetLinearVelocity( axis[ 2 ] * speed + pushVelocity );'''
velocity_new = '''\tphysicsObj.SetLinearVelocity( ( spawnArgs.GetBool( "q4_projectile_forward_x" ) ? axis[ 0 ] : axis[ 2 ] ) * speed + pushVelocity );'''
projectile = replace_once(projectile, velocity_old, velocity_new, 'projectile launch velocity axis')


# Verification: both features must be present, and existing BSE fly lifecycle
# must still exist after the cumulative V18J patch chain.
combined = weapon + projectile
for required in (
    'q4_gui_weapon_ammo_event',
    'HandleNamedEvent( "weapon_ammo" )',
    'q4_projectile_forward_x',
    '? axis[ 0 ] : axis[ 2 ]',
    'spawnArgs.GetString( "fx_fly" )',
    'Q4BSE_AttachEffectToEntity( q4bseFlyFx, this )',
):
    if required not in combined:
        raise SystemExit(f'ERROR: V18K verification missing: {required}')

# Ensure the +X override is exactly opt-in at both orientation sites.
if projectile.count('!spawnArgs.GetBool( "q4_projectile_forward_x" )') != 2:
    raise SystemExit('ERROR: V18K +X orientation hook count mismatch')

WEAPON.write_text(weapon, encoding='utf-8')
PROJECTILE.write_text(projectile, encoding='utf-8')

print('Q4BSE V18K ROCKET LAUNCHER BRIDGE PASS.')
print('  - opt-in Raven weapon_ammo named-event bridge enabled')
print('  - opt-in local +X projectile forward convention enabled')
print('  - existing V18J BSE fx_fly lifecycle retained')
print('  - all weapons/projectiles without V18K keys remain unchanged')
