#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
W = ROOT / 'neo/game/Weapon.cpp'
if not W.exists():
    raise SystemExit(f'V20K prerequisite missing: {W}')

text = W.read_text(encoding='utf-8-sig')

# V20J finally put Raven's Railgun muzzle effect at the correct view joint, but
# Q4BSE_PlayEffectAxis is a world-space one-shot.  The muzzle FX itself contains
# locked particles, so its effect transform must remain attached to the moving
# weapon for the short lifetime of the flash.  Reuse the moving attachment path
# already proven by the Q4 Blaster integration.
old_muzzle = '''\t\t\tQ4BSE_PlayEffectAxis( railMuzzleFx, railMuzzleOrigin, railMuzzleAxis );\n'''
new_muzzle = '''\t\t\tQ4BSE_AttachEffectToEntityTransform( railMuzzleFx, this, railMuzzleOrigin, railMuzzleAxis );\n'''
hits = text.count(old_muzzle)
if hits != 1:
    raise SystemExit(f'V20K muzzle attachment call: expected 1, got {hits}')
text = text.replace(old_muzzle, new_muzzle, 1)

# V20I/J tried to reconstruct Raven's generic rvWeapon::UpdateGUI timing, but
# the retail Railgun warning is specifically meaningful at the native clip
# transition to zero.  Trigger a dedicated, opt-in GUI event at that exact
# transition.  The companion railgun.gui keeps Raven's original authored
# `anim` timeline and simply resets it without a second state-expression gate.
old_ammo = '''\t\t\tif ( clipSize && ammoRequired ) {\n\t\t\t\tammoClip--;\n\t\t\t}\n\t\t\towner->AddProjectilesFired( 1 );\n'''
new_ammo = '''\t\t\tif ( clipSize && ammoRequired ) {\n\t\t\t\tammoClip--;\n\n\t\t\t\t// Q4 V20K: fire the authored Railgun empty-warning timeline at the\n\t\t\t\t// exact 1 -> 0 clip transition.  Publishing zero here also keeps the\n\t\t\t\t// later generic UpdateGUI pass from replaying the same transition.\n\t\t\t\tif ( ammoClip == 0 && renderEntity.gui[ 0 ] &&\n\t\t\t\t\t weaponDef->dict.GetBool( "q4_gui_weapon_ammo_event" ) ) {\n\t\t\t\t\tidUserInterface *railGui = renderEntity.gui[ 0 ];\n\t\t\t\t\trailGui->SetStateInt( "player_ammo", 0 );\n\t\t\t\t\trailGui->SetStateFloat( "player_ammopct", 0.0f );\n\t\t\t\t\trailGui->SetStateInt( "player_cachedammo", 0 );\n\t\t\t\t\trailGui->StateChanged( gameLocal.time );\n\t\t\t\t\trailGui->HandleNamedEvent( "weapon_empty" );\n\t\t\t\t}\n\t\t\t}\n\t\t\towner->AddProjectilesFired( 1 );\n'''
hits = text.count(old_ammo)
if hits != 1:
    raise SystemExit(f'V20K native Railgun ammo decrement block: expected 1, got {hits}')
text = text.replace(old_ammo, new_ammo, 1)

for needle in (
    'Q4BSE_AttachEffectToEntityTransform( railMuzzleFx, this, railMuzzleOrigin, railMuzzleAxis )',
    'railGui->HandleNamedEvent( "weapon_empty" )',
    'railGui->SetStateInt( "player_cachedammo", 0 )',
    'Q4BSE_PlayEffectBetween( railTrailFx, railOrigin, railTrace.endpos, railFxAxis )',
):
    if needle not in text:
        raise SystemExit(f'V20K verification missing: {needle}')

W.write_text(text, encoding='utf-8')
print('V20K Railgun bound muzzle + exact empty-warning event applied')
