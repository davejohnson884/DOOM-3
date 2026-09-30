#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
W = ROOT / 'neo/game/Weapon.cpp'
if not W.exists():
    raise SystemExit(f'V20I prerequisite missing: {W}')

text = W.read_text(encoding='utf-8-sig')

old = '''\t// Q4 V18K: Raven weapon GUIs may update visibility in a named event rather\n\t// than directly from state expressions. Fire it only for opted-in weapons,\n\t// after all ammo state keys above have been refreshed.\n\tif ( weaponDef && weaponDef->dict.GetBool( "q4_gui_weapon_ammo_event" ) ) {\n\t\trenderEntity.gui[ 0 ]->HandleNamedEvent( "weapon_ammo" );\n\t}\n'''

new = '''\t// Q4 V20I: match Raven's rvWeapon::UpdateGUI semantics. Q4 does NOT post\n\t// weapon_ammo every frame; it caches AmmoInClip() and only fires the named\n\t// event when that value changes. This matters for Railgun's warning timeline:\n\t// repeatedly resetting it every frame prevents the authored orange warning\n\t// animation from advancing.\n\tif ( weaponDef && weaponDef->dict.GetBool( "q4_gui_weapon_ammo_event" ) ) {\n\t\tidUserInterface *gui = renderEntity.gui[ 0 ];\n\t\tconst int q4Ammo = inclip;\n\t\tif ( gui->State().GetInt( "player_cachedammo", "-1" ) != q4Ammo ) {\n\t\t\tgui->SetStateInt( "player_ammo", q4Ammo );\n\t\t\tif ( ClipSize() ) {\n\t\t\t\tgui->SetStateFloat( "player_ammopct", (float)q4Ammo / (float)ClipSize() );\n\t\t\t\tgui->SetStateInt( "player_clip_size", ClipSize() );\n\t\t\t}\n\t\t\tgui->SetStateInt( "player_cachedammo", q4Ammo );\n\t\t\tgui->HandleNamedEvent( "weapon_ammo" );\n\t\t}\n\t}\n'''

hits = text.count(old)
if hits != 1:
    raise SystemExit(f'V20I ammo event block: expected 1, got {hits}')
text = text.replace(old, new, 1)

for needle in (
    'player_cachedammo',
    'gui->HandleNamedEvent( "weapon_ammo" )',
    'gui->SetStateFloat( "player_ammopct"',
):
    if needle not in text:
        raise SystemExit(f'V20I verification missing: {needle}')

W.write_text(text, encoding='utf-8')
print('V20I Raven ammo GUI event parity applied')
