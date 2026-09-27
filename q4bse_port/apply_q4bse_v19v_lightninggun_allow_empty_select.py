#!/usr/bin/env python3
'''V19V: keep the Lightning Gun selectable at zero ammo.

Doom 3's stock weapon cycling intentionally skips weapons with no ammo, and its
weapon-raise path auto-selects another weapon if AmmoAvailable()==0.  That is
undesirable for the Quake 4 Lightning Gun port: after exhausting cells the gun
should remain an owned/selectable inventory item so the player can scroll back
to it and hear/see its dry state.

This patch is deliberately scoped to the repurposed weapon_chainsaw classname.
Automatic NextBestWeapon behavior for every other empty weapon remains stock.
'''
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
player_cpp = root / 'neo' / 'game' / 'Player.cpp'
if not player_cpp.exists():
    raise SystemExit(f'V19V prerequisite missing: {player_cpp}')

text = player_cpp.read_text(encoding='utf-8-sig')


def function_slice(src, name, next_name):
    # Signatures differ: NextWeapon/PrevWeapon take void, SelectWeapon takes
    # (int num, bool force), DropWeapon takes bool. Match only the function name.
    start_token = f'void idPlayer::{name}'
    end_token = f'void idPlayer::{next_name}'
    start = src.find(start_token)
    if start < 0:
        raise SystemExit(f'V19V: function not found: {name}')
    end = src.find(end_token, start + len(start_token))
    if end < 0:
        raise SystemExit(f'V19V: next function marker not found after {name}: {next_name}')
    return start, end, src[start:end]


def replace_in_function(src, name, next_name, old, new, expected=1):
    start, end, block = function_slice(src, name, next_name)
    hits = block.count(old)
    if hits != expected:
        raise SystemExit(f'V19V: {name} expected {expected} match(es), found {hits}: {old!r}')
    block = block.replace(old, new, expected)
    return src[:start] + block + src[end:]

# Mouse-wheel / inventory cycling: stock Doom 3 only breaks on a weapon with
# ammo. Permit the repurposed chainsaw slot even when its cells are at zero.
cycle_old = '''\t\tif ( inventory.HasAmmo( weap ) ) {\n\t\t\tbreak;\n\t\t}\n'''
cycle_new = '''\t\tif ( inventory.HasAmmo( weap ) || !idStr::Icmp( weap, "weapon_chainsaw" ) ) {\n\t\t\tbreak;\n\t\t}\n'''

text = replace_in_function(text, 'NextWeapon', 'PrevWeapon', cycle_old, cycle_new, 1)
text = replace_in_function(text, 'PrevWeapon', 'SelectWeapon', cycle_old, cycle_new, 1)

# Direct selection path: preserve normal allowempty behavior and additionally
# allow this one classname to be selected empty.
select_old = '''\t\tif ( !inventory.HasAmmo( weap ) && !spawnArgs.GetBool( va( "weapon%d_allowempty", num ) ) ) {\n\t\t\treturn;\n\t\t}\n'''
select_new = '''\t\tif ( !inventory.HasAmmo( weap ) &&\n\t\t\t !spawnArgs.GetBool( va( "weapon%d_allowempty", num ) ) &&\n\t\t\t idStr::Icmp( weap, "weapon_chainsaw" ) ) {\n\t\t\treturn;\n\t\t}\n'''
text = replace_in_function(text, 'SelectWeapon', 'DropWeapon', select_old, select_new, 1)

# When a newly selected weapon reaches its holstered/raise transition Doom 3
# normally refuses to raise an empty weapon and immediately calls
# NextBestWeapon(). Keep that behavior for everything except the Q4 LG slot.
raise_old = '''\t\tif ( weapon.GetEntity()->IsHolstered() ) {\n\t\t\tif ( !weapon.GetEntity()->AmmoAvailable() ) {\n\t\t\t\t// weapons can switch automatically if they have no more ammo\n\t\t\t\tNextBestWeapon();\n\t\t\t} else {\n'''
raise_new = '''\t\tif ( weapon.GetEntity()->IsHolstered() ) {\n\t\t\tconst char *q4CurrentWeaponDef = spawnArgs.GetString( va( "def_weapon%d", currentWeapon ) );\n\t\t\tif ( !weapon.GetEntity()->AmmoAvailable() && idStr::Icmp( q4CurrentWeaponDef, "weapon_chainsaw" ) ) {\n\t\t\t\t// Stock behavior for unrelated empty weapons. The Q4 Lightning Gun\n\t\t\t\t// remains selectable/raiseable at zero cells.\n\t\t\t\tNextBestWeapon();\n\t\t\t} else {\n'''
hits = text.count(raise_old)
if hits != 1:
    raise SystemExit(f'V19V: expected one holstered empty-ammo raise gate, found {hits}')
text = text.replace(raise_old, raise_new, 1)

for needle in (
    'inventory.HasAmmo( weap ) || !idStr::Icmp( weap, "weapon_chainsaw" )',
    'q4CurrentWeaponDef',
    'The Q4 Lightning Gun',
):
    if needle not in text:
        raise SystemExit(f'V19V verification missing: {needle}')

player_cpp.write_text(text, encoding='utf-8')
print('V19V Lightning Gun empty-selection fix applied')
print(' - next/previous weapon cycling includes owned weapon_chainsaw at zero cells')
print(' - direct SelectWeapon permits the empty Lightning Gun')
print(' - raise transition no longer auto-skips the empty Lightning Gun')
print(' - all unrelated empty-weapon behavior remains stock')
