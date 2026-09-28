#!/usr/bin/env python3
'''V19Z.1: never auto-raise Doom 3's handheld flashlight on pickup.

V19Z virtualizes weapon_flashlight selection into the Quake 4 Machinegun
flashlight action, but idInventory::Give can auto-switch by writing idealWeapon
directly. Keep flashlight ownership for stock map/save compatibility while
preventing that bypass from ever raising the handheld light.
'''
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
player = root / 'neo' / 'game' / 'Player.cpp'
if not player.exists():
    raise SystemExit(f'V19Z.1 prerequisite missing: {player}')

text = player.read_text(encoding='utf-8-sig')
old = '''\t\t\t\t\tif ( owner->GetUserInfo()->GetBool( "ui_autoSwitch" ) && idealWeapon ) {\n\t\t\t\t\t\tassert( !gameLocal.isClient );\n\t\t\t\t\t\t*idealWeapon = i;\n\t\t\t\t\t} '''
new = '''\t\t\t\t\tif ( owner->GetUserInfo()->GetBool( "ui_autoSwitch" ) && idealWeapon && weaponName != "weapon_flashlight" ) {\n\t\t\t\t\t\tassert( !gameLocal.isClient );\n\t\t\t\t\t\t*idealWeapon = i;\n\t\t\t\t\t} '''

hits = text.count(old)
if hits != 1:
    raise SystemExit(f'V19Z.1 expected one weapon pickup auto-switch block, found {hits}')
text = text.replace(old, new, 1)

if 'weaponName != "weapon_flashlight"' not in text:
    raise SystemExit('V19Z.1 verification failed')

player.write_text(text, encoding='utf-8')
print('V19Z.1 flashlight pickup auto-switch suppression applied')
