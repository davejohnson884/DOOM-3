#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
W = ROOT / 'neo/game/Weapon.cpp'
if not W.exists():
    raise SystemExit(f'V20J prerequisite missing: {W}')

text = W.read_text(encoding='utf-8-sig')

# V20I correctly stopped hammering weapon_ammo every frame, but Doom 3 GUI
# state vars are synchronized into window expressions by StateChanged().
# Without that sync, the named event can run while gui::player_ammo still
# evaluates to the previous clip count (1), so Railgun's "== 0" warning gate
# misses the transition completely.
old_gui = '''\t\t\tgui->SetStateInt( "player_cachedammo", q4Ammo );\n\t\t\tgui->HandleNamedEvent( "weapon_ammo" );\n'''
new_gui = '''\t\t\tgui->SetStateInt( "player_cachedammo", q4Ammo );\n\t\t\t// Q4 V20J: publish the freshly-written state to GUI expressions BEFORE\n\t\t\t// running Raven's named event.  railgun.gui tests gui::player_ammo\n\t\t\t// inside weapon_ammo, so stale winvars make the zero-ammo warning miss.\n\t\t\tgui->StateChanged( gameLocal.time );\n\t\t\tgui->HandleNamedEvent( "weapon_ammo" );\n'''
hits = text.count(old_gui)
if hits != 1:
    raise SystemExit(f'V20J GUI sync block: expected 1, got {hits}')
text = text.replace(old_gui, new_gui, 1)

# The trail intentionally uses Raven's hitscan fxOriginOffset so the visible
# beam converges from the gun toward center aim.  The muzzle flash does NOT:
# it belongs directly on srocket_muzzle_flash.  V20I spawned both from the
# offset railOrigin, displacing the 0.1s flash away from the muzzle.
old_muzzle = '''\t\tconst char *railMuzzleFx = weaponDef->dict.GetString( "fx_muzzleflash" );\n\t\tif ( railMuzzleFx && railMuzzleFx[0] ) {\n\t\t\tQ4BSE_PlayEffectAxis( railMuzzleFx, railOrigin, railAxis );\n\t\t}\n'''
new_muzzle = '''\t\tconst char *railMuzzleFx = weaponDef->dict.GetString( "fx_muzzleflash" );\n\t\tif ( railMuzzleFx && railMuzzleFx[0] ) {\n\t\t\t// Q4 V20J: muzzle FX is joint-local.  Keep fxOriginOffset exclusively\n\t\t\t// for the authored rail/trail origin below.\n\t\t\tidVec3 railMuzzleOrigin = railOrigin;\n\t\t\tidMat3 railMuzzleAxis = railAxis;\n\t\t\tGetQ4PresentedJointTransform( flashJointView, railMuzzleOrigin, railMuzzleAxis, vec3_origin );\n\t\t\tQ4BSE_PlayEffectAxis( railMuzzleFx, railMuzzleOrigin, railMuzzleAxis );\n\t\t}\n'''
hits = text.count(old_muzzle)
if hits != 1:
    raise SystemExit(f'V20J muzzle block: expected 1, got {hits}')
text = text.replace(old_muzzle, new_muzzle, 1)

for needle in (
    'gui->StateChanged( gameLocal.time )',
    'GetQ4PresentedJointTransform( flashJointView, railMuzzleOrigin, railMuzzleAxis, vec3_origin )',
    'Q4BSE_PlayEffectAxis( railMuzzleFx, railMuzzleOrigin, railMuzzleAxis )',
    'Q4BSE_PlayEffectBetween( railTrailFx, railOrigin, railTrace.endpos, railFxAxis )',
):
    if needle not in text:
        raise SystemExit(f'V20J verification missing: {needle}')

W.write_text(text, encoding='utf-8')
print('V20J Railgun GUI state sync + muzzle joint fix applied')
