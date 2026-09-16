#!/usr/bin/env python3
'''V18Q: move Rocket Launcher manual guidance off Doom 3 BUTTON_ZOOM and onto
BUTTON_5, the dedicated secondary/alt-fire transport used by the Q4 weapon
layer in this Doom 3 port.

Runs AFTER V18P.  It deliberately restores stock Doom 3 camera zoom handling,
so the user's normal Z zoom remains available while Mouse2 can operate the Q4
weapon-specific designator path.

No Rocket Launcher projectile, BSE, damage, trail, explosion, beam, or marker
presentation behavior is otherwise changed.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
WEAPON_CPP = ROOT / 'neo' / 'game' / 'Weapon.cpp'
PROJECTILE_CPP = ROOT / 'neo' / 'game' / 'Projectile.cpp'
PLAYER_CPP = ROOT / 'neo' / 'game' / 'Player.cpp'

for p in (WEAPON_CPP, PROJECTILE_CPP, PLAYER_CPP):
    if not p.exists():
        raise SystemExit(f'ERROR: V18Q prerequisite missing: {p}')

weapon = WEAPON_CPP.read_text(encoding='utf-8-sig')
projectile = PROJECTILE_CPP.read_text(encoding='utf-8-sig')
player = PLAYER_CPP.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V18Q expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)


# Weapon-side presentation gate: Mouse2/secondary button owns the designator.
weapon = replace_once(
    weapon,
    '''\t\t !( owner->usercmd.buttons & BUTTON_ZOOM ) ) {''',
    '''\t\t !( owner->usercmd.buttons & BUTTON_5 ) ) {''',
    'weapon guidance input gate')

# Projectile-side steering gate: use the exact same secondary button.
projectile = replace_once(
    projectile,
    '''\t\tif ( guidePlayer->usercmd.buttons & BUTTON_ZOOM ) {''',
    '''\t\tif ( guidePlayer->usercmd.buttons & BUTTON_5 ) {''',
    'projectile guidance input gate')

# Keep comments accurate for future cumulative work.
projectile = projectile.replace(
    'Releasing BUTTON_ZOOM immediately stops steering and preserves the current',
    'Releasing BUTTON_5 immediately stops steering and preserves the current',
    1)

# V18P suppressed normal zoom because it was reusing BUTTON_ZOOM.  V18Q no
# longer does that, so restore the stock Doom 3 zoom transition block exactly.
v18p_zoom = '''\t// zooming. Q4 V18P guide weapons reuse BUTTON_ZOOM as alt-fire, so they\n\t// deliberately keep the normal camera FOV while the designator is held.\n\tif ( ( usercmd.buttons ^ oldCmd.buttons ) & BUTTON_ZOOM ) {\n\t\tif ( ( usercmd.buttons & BUTTON_ZOOM ) && weapon.GetEntity() &&\n\t\t\t !weapon.GetEntity()->IsQ4GuidedLaserWeapon() ) {\n\t\t\tzoomFov.Init( gameLocal.time, 200.0f, CalcFov( false ), weapon.GetEntity()->GetZoomFov() );\n\t\t} else {\n\t\t\tzoomFov.Init( gameLocal.time, 200.0f, zoomFov.GetCurrentValue( gameLocal.time ), DefaultFov() );\n\t\t}\n\t}'''
stock_zoom = '''\t// zooming\n\tif ( ( usercmd.buttons ^ oldCmd.buttons ) & BUTTON_ZOOM ) {\n\t\tif ( ( usercmd.buttons & BUTTON_ZOOM ) && weapon.GetEntity() ) {\n\t\t\tzoomFov.Init( gameLocal.time, 200.0f, CalcFov( false ), weapon.GetEntity()->GetZoomFov() );\n\t\t} else {\n\t\t\tzoomFov.Init( gameLocal.time, 200.0f, zoomFov.GetCurrentValue( gameLocal.time ), DefaultFov() );\n\t\t}\n\t}'''
player = replace_once(player, v18p_zoom, stock_zoom, 'Player zoom suppression restore')

v18p_fov = '''\t\tfov = ( honorZoom && ( usercmd.buttons & BUTTON_ZOOM ) && weapon.GetEntity() &&\n\t\t\t !weapon.GetEntity()->IsQ4GuidedLaserWeapon() ) ? weapon.GetEntity()->GetZoomFov() : DefaultFov();'''
stock_fov = '''\t\tfov = ( honorZoom && usercmd.buttons & BUTTON_ZOOM ) && weapon.GetEntity() ? weapon.GetEntity()->GetZoomFov() : DefaultFov();'''
player = replace_once(player, v18p_fov, stock_fov, 'Player CalcFov restore')

# Strict sanity checks: guide presentation and steering must be BUTTON_5-only,
# while stock BUTTON_ZOOM handling remains in Player.cpp.
if '!( owner->usercmd.buttons & BUTTON_5 )' not in weapon:
    raise SystemExit('ERROR: V18Q weapon BUTTON_5 gate missing')
if 'guidePlayer->usercmd.buttons & BUTTON_5' not in projectile:
    raise SystemExit('ERROR: V18Q projectile BUTTON_5 gate missing')
if '!weapon.GetEntity()->IsQ4GuidedLaserWeapon()' in player:
    raise SystemExit('ERROR: V18Q Player zoom suppression still present')
if stock_zoom not in player or stock_fov not in player:
    raise SystemExit('ERROR: V18Q stock Doom 3 zoom path not restored')

WEAPON_CPP.write_text(weapon, encoding='utf-8')
PROJECTILE_CPP.write_text(projectile, encoding='utf-8')
PLAYER_CPP.write_text(player, encoding='utf-8')

print('Q4BSE V18Q MOUSE2 GUIDANCE INPUT PASS.')
print('  - Rocket designator presentation uses BUTTON_5 / Q4 secondary input')
print('  - guided rockets steer only while BUTTON_5 is held')
print('  - Doom 3 BUTTON_ZOOM / Z camera zoom behavior restored unchanged')
print('  - V18P beam, marker, trace, steering math, and prior Rocket behavior retained')
