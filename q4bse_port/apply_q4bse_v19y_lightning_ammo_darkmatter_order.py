#!/usr/bin/env python3
'''V19Y: give the standalone Lightning Gun its own ammo type and move the
Dark Matter Gun/BFG-class weapon behind it in scroll order.

Runs after V19X.  Keeps the accepted Lightning Gun runtime intact.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PLAYER = ROOT / 'neo' / 'game' / 'Player.cpp'
WEAPON = ROOT / 'neo' / 'game' / 'Weapon.cpp'

for p in (PLAYER, WEAPON):
    if not p.exists():
        raise SystemExit(f'ERROR: V19Y prerequisite missing: {p}')

player = PLAYER.read_text(encoding='utf-8-sig')
weapon = WEAPON.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V19Y expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)

# -------------------------------------------------------------------------
# Inventory ordering.
# Slot 8 is the stock BFG slot.  The Q4 Dark Matter Gun port still owns the
# weapon_bfg classname, so move that classname to slot 14.  Lightning stays in
# slot 13.  Slots 13 and 14 are reached by next/previous weapon cycling; the
# stock impulses 13-15 remain reload/next/previous and are intentionally not
# repurposed.
# -------------------------------------------------------------------------
old_slot_block = '''\t// V19W2: the Q4 Lightning Gun is a true additional Doom 3 weapon.\n\t// Stock Doom 3 1.3.1 uses slot 11 for the flashlight and 12 for the PDA;\n\t// slot 13 is genuinely unused. Keep this local to the player spawnArgs so\n\t// no wholesale player.def replacement is required.\n\tspawnArgs.Set( "def_weapon13", "weapon_lightninggun" );\n\tspawnArgs.Set( "weapon13_best", "1" );\n\tspawnArgs.Set( "weapon13_cycle", "1" );\n\tspawnArgs.Set( "weapon13_toggle", "0" );\n\tspawnArgs.Set( "weapon13_allowempty", "1" );\n\tspawnArgs.Set( "weapon13_visible", "1" );\n'''

new_slot_block = '''\t// V19Y: standalone Q4 weapon ordering.  Lightning Gun occupies slot 13 and\n\t// the Q4 Dark Matter Gun (weapon_bfg classname) moves from stock BFG slot 8\n\t// to slot 14, so normal weapon scrolling reaches Lightning -> Dark Matter.\n\t// Stock impulses 13/14/15 remain reload/next/previous.\n\tspawnArgs.Set( "def_weapon8", "" );\n\tspawnArgs.Set( "weapon8_cycle", "0" );\n\tspawnArgs.Set( "weapon8_visible", "0" );\n\n\tspawnArgs.Set( "def_weapon13", "weapon_lightninggun" );\n\tspawnArgs.Set( "weapon13_best", "1" );\n\tspawnArgs.Set( "weapon13_cycle", "1" );\n\tspawnArgs.Set( "weapon13_toggle", "0" );\n\tspawnArgs.Set( "weapon13_allowempty", "1" );\n\tspawnArgs.Set( "weapon13_visible", "1" );\n\n\tspawnArgs.Set( "def_weapon14", "weapon_bfg" );\n\tspawnArgs.Set( "weapon14_best", "1" );\n\tspawnArgs.Set( "weapon14_cycle", "1" );\n\tspawnArgs.Set( "weapon14_toggle", "0" );\n\tspawnArgs.Set( "weapon14_allowempty", "0" );\n\tspawnArgs.Set( "weapon14_visible", "1" );\n\n\t// Dedicated Lightning Gun reserve.  Its weapon def uses ammo_lightninggun;\n\t// Doom 3's inventory asks the player spawnArgs for max_<ammo classname>.\n\tspawnArgs.Set( "max_ammo_lightninggun", "400" );\n'''
player = replace_once(player, old_slot_block, new_slot_block, 'V19W2 slot-13 block')

# -------------------------------------------------------------------------
# Dedicated ammo type.
# Stock Doom 3 base occupies ammo indexes 0..9, while AMMO_NUMTYPES is 16.
# Reserve index 10 for ammo_lightninggun without replacing ammo.def or the
# global ammo_types/ammo_names decls.  This avoids compatibility fights with
# content PK4s while still making persistence and pickup logic see a real,
# independent inventory ammo bucket.
# -------------------------------------------------------------------------
old_num = '''ammo_t idWeapon::GetAmmoNumForName( const char *ammoname ) {\n\tint num;\n\tconst idDict *ammoDict;\n\n\tassert( ammoname );\n'''
new_num = '''ammo_t idWeapon::GetAmmoNumForName( const char *ammoname ) {\n\tint num;\n\tconst idDict *ammoDict;\n\n\tassert( ammoname );\n\n\t// V19Y: dedicated Q4 Lightning Gun ammo bucket.\n\tif ( !idStr::Icmp( ammoname, "ammo_lightninggun" ) ) {\n\t\treturn ( ammo_t )10;\n\t}\n'''
weapon = replace_once(weapon, old_num, new_num, 'GetAmmoNumForName header')

old_name = '''const char *idWeapon::GetAmmoNameForNum( ammo_t ammonum ) {\n\tint i;\n\tint num;\n\tconst idDict *ammoDict;\n\tconst idKeyValue *kv;\n\tchar text[ 32 ];\n\n\tammoDict = gameLocal.FindEntityDefDict( "ammo_types", false );\n'''
new_name = '''const char *idWeapon::GetAmmoNameForNum( ammo_t ammonum ) {\n\tint i;\n\tint num;\n\tconst idDict *ammoDict;\n\tconst idKeyValue *kv;\n\tchar text[ 32 ];\n\n\t// V19Y: persistence/name lookup for the dedicated Lightning Gun ammo.\n\tif ( ammonum == ( ammo_t )10 ) {\n\t\treturn "ammo_lightninggun";\n\t}\n\n\tammoDict = gameLocal.FindEntityDefDict( "ammo_types", false );\n'''
weapon = replace_once(weapon, old_name, new_name, 'GetAmmoNameForNum header')

old_pickup = '''const char *idWeapon::GetAmmoPickupNameForNum( ammo_t ammonum ) {\n\tint i;\n\tint num;\n\tconst idDict *ammoDict;\n\tconst idKeyValue *kv;\n\n\tammoDict = gameLocal.FindEntityDefDict( "ammo_names", false );\n'''
new_pickup = '''const char *idWeapon::GetAmmoPickupNameForNum( ammo_t ammonum ) {\n\tint i;\n\tint num;\n\tconst idDict *ammoDict;\n\tconst idKeyValue *kv;\n\n\t// V19Y: HUD pickup label for the dedicated Lightning Gun reserve.\n\tif ( ammonum == ( ammo_t )10 ) {\n\t\treturn "Lightning Ammo";\n\t}\n\n\tammoDict = gameLocal.FindEntityDefDict( "ammo_names", false );\n'''
weapon = replace_once(weapon, old_pickup, new_pickup, 'GetAmmoPickupNameForNum header')

PLAYER.write_text(player, encoding='utf-8')
WEAPON.write_text(weapon, encoding='utf-8')

# Hard gates so the patch cannot silently build the wrong inventory/ammo layout.
checks = {
    'Lightning slot 13': 'spawnArgs.Set( "def_weapon13", "weapon_lightninggun" )' in player,
    'Dark Matter slot 14': 'spawnArgs.Set( "def_weapon14", "weapon_bfg" )' in player,
    'stock BFG slot cleared': 'spawnArgs.Set( "def_weapon8", "" )' in player,
    'Lightning max ammo': 'spawnArgs.Set( "max_ammo_lightninggun", "400" )' in player,
    'Lightning ammo name->10': 'ammoname, "ammo_lightninggun"' in weapon and 'return ( ammo_t )10;' in weapon,
    'Lightning ammo 10->name': 'return "ammo_lightninggun";' in weapon,
    'Lightning pickup label': 'return "Lightning Ammo";' in weapon,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit('ERROR: V19Y verification failed: ' + ', '.join(failed))

print('V19Y applied: Lightning slot13 + ammo_lightninggun index10; Dark Matter/weapon_bfg slot14.')
