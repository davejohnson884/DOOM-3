#!/usr/bin/env python3
'''V19Z.2: Quake 4 flashlight selection logic for Blaster + Machinegun.

F / weapon_flashlight behavior:
- Blaster (weapon_pistol): toggle its flashlight, never switch weapons.
- Machinegun: toggle its flashlight, never switch weapons.
- Any other weapon: raise Machinegun with flashlight ON.

q4_flashlight is shared by the two Q4 flashlight-capable view weapons, so reset it
when leaving either one. This keeps each weapon's visible flashlight behavior
independent even though they use the same transient cvar.
'''
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
player = root / 'neo' / 'game' / 'Player.cpp'
if not player.exists():
    raise SystemExit(f'V19Z.2 prerequisite missing: {player}')

text = player.read_text(encoding='utf-8-sig')

old_select = '''\t// Q4 V19Z: Doom 3's flashlight slot is now a virtual Q4 flashlight action.\n\t// F can stay bound to _impulse11: from another weapon it raises the\n\t// Machinegun with its light ON; while already on the Machinegun it toggles\n\t// that light. The stock handheld flashlight can never become currentWeapon.\n\tif ( !idStr::Icmp( weap, "weapon_flashlight" ) ) {\n\t\tconst int mgSlot = SlotForWeapon( "weapon_machinegun" );\n\t\tif ( mgSlot < 0 || mgSlot >= MAX_WEAPONS || ( inventory.weapons & ( 1 << mgSlot ) ) == 0 ) {\n\t\t\treturn;\n\t\t}\n\n\t\tif ( currentWeapon == mgSlot && idealWeapon == mgSlot ) {\n\t\t\tcvarSystem->SetCVarBool( "q4_flashlight", !cvarSystem->GetCVarBool( "q4_flashlight" ) );\n\t\t} else {\n\t\t\tcvarSystem->SetCVarBool( "q4_flashlight", true );\n\t\t\tidealWeapon = mgSlot;\n\t\t\tweaponSwitchTime = gameLocal.time + WEAPON_SWITCH_DELAY;\n\t\t\tUpdateHudWeapon();\n\t\t}\n\t\treturn;\n\t}\n'''

new_select = '''\t// Q4 V19Z.2: Doom 3's flashlight slot is a virtual Q4 flashlight action.\n\t// - On the Blaster: toggle the Blaster flashlight in place.\n\t// - On the Machinegun: toggle the Machinegun flashlight in place.\n\t// - On any other weapon: raise the Machinegun with its flashlight ON.\n\t// The stock handheld Doom 3 flashlight can never become currentWeapon.\n\tif ( !idStr::Icmp( weap, "weapon_flashlight" ) ) {\n\t\tconst int blasterSlot = SlotForWeapon( "weapon_pistol" );\n\t\tconst int mgSlot = SlotForWeapon( "weapon_machinegun" );\n\n\t\tconst bool onBlaster = ( blasterSlot >= 0 && blasterSlot < MAX_WEAPONS &&\n\t\t\tcurrentWeapon == blasterSlot && idealWeapon == blasterSlot );\n\t\tconst bool onMachinegun = ( mgSlot >= 0 && mgSlot < MAX_WEAPONS &&\n\t\t\tcurrentWeapon == mgSlot && idealWeapon == mgSlot );\n\n\t\tif ( onBlaster || onMachinegun ) {\n\t\t\tcvarSystem->SetCVarBool( "q4_flashlight", !cvarSystem->GetCVarBool( "q4_flashlight" ) );\n\t\t\treturn;\n\t\t}\n\n\t\tif ( mgSlot < 0 || mgSlot >= MAX_WEAPONS || ( inventory.weapons & ( 1 << mgSlot ) ) == 0 ) {\n\t\t\treturn;\n\t\t}\n\n\t\tcvarSystem->SetCVarBool( "q4_flashlight", true );\n\t\tidealWeapon = mgSlot;\n\t\tweaponSwitchTime = gameLocal.time + WEAPON_SWITCH_DELAY;\n\t\tUpdateHudWeapon();\n\t\treturn;\n\t}\n'''

hits = text.count(old_select)
if hits != 1:
    raise SystemExit(f'V19Z.2 expected one flashlight selection block, found {hits}')
text = text.replace(old_select, new_select, 1)

old_reset = '''\t\t\t\tconst char *q4OldWeaponDef = spawnArgs.GetString( va( "def_weapon%d", currentWeapon ) );\n\t\t\t\tconst char *q4NewWeaponDef = spawnArgs.GetString( va( "def_weapon%d", idealWeapon ) );\n\t\t\t\tif ( !idStr::Icmp( q4OldWeaponDef, "weapon_machinegun" ) && idStr::Icmp( q4NewWeaponDef, "weapon_machinegun" ) ) {\n\t\t\t\t\tcvarSystem->SetCVarBool( "q4_flashlight", false );\n\t\t\t\t}\n'''

new_reset = '''\t\t\t\tconst char *q4OldWeaponDef = spawnArgs.GetString( va( "def_weapon%d", currentWeapon ) );\n\t\t\t\tconst char *q4NewWeaponDef = spawnArgs.GetString( va( "def_weapon%d", idealWeapon ) );\n\t\t\t\tconst bool q4OldWeaponHasFlashlight =\n\t\t\t\t\t!idStr::Icmp( q4OldWeaponDef, "weapon_machinegun" ) ||\n\t\t\t\t\t!idStr::Icmp( q4OldWeaponDef, "weapon_pistol" );\n\t\t\t\tif ( q4OldWeaponHasFlashlight && idStr::Icmp( q4OldWeaponDef, q4NewWeaponDef ) ) {\n\t\t\t\t\tcvarSystem->SetCVarBool( "q4_flashlight", false );\n\t\t\t\t}\n'''

hits = text.count(old_reset)
if hits != 1:
    raise SystemExit(f'V19Z.2 expected one flashlight reset block, found {hits}')
text = text.replace(old_reset, new_reset, 1)

for needle in (
    'SlotForWeapon( "weapon_pistol" )',
    'const bool onBlaster',
    'const bool onMachinegun',
    'if ( onBlaster || onMachinegun )',
    'q4OldWeaponHasFlashlight',
    '!idStr::Icmp( q4OldWeaponDef, "weapon_pistol" )',
):
    if needle not in text:
        raise SystemExit(f'V19Z.2 verification missing: {needle}')

player.write_text(text, encoding='utf-8')
print('V19Z.2 Q4 Blaster/Machinegun flashlight logic applied')
