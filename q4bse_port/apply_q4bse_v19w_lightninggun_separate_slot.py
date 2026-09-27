#!/usr/bin/env python3
'''V19W2: move the finished Q4 Lightning Gun out of Doom 3's chainsaw slot.

The accepted V19V gun remains unchanged at the weapon/runtime level. This overlay:
- assigns weapon_lightninggun to Doom 3's actually-unused weapon slot 13
- preserves stock slot 11 weapon_flashlight and slot 12 weapon_pda
- moves V19V's empty-ammo selection exception from weapon_chainsaw to weapon_lightninggun
- aliases the new Lightning Gun player animation prefix to Doom 3's two-handed Plasma Gun set

The weapon_chainsaw classname is therefore free for the future Q4 Gauntlet/Ripper.
'''
from pathlib import Path
import re
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
player_cpp = root / 'neo' / 'game' / 'Player.cpp'
if not player_cpp.exists():
    raise SystemExit(f'V19W2 prerequisite missing: {player_cpp}')

text = player_cpp.read_text(encoding='utf-8-sig')

# V19V intentionally special-cased weapon_chainsaw because the LG lived in that
# slot. V19W2 gives the LG its own real classname/slot, so move those four gates.
old_gate = 'weapon_chainsaw'
new_gate = 'weapon_lightninggun'
old_count = text.count(f'"{old_gate}"')
if old_count != 4:
    raise SystemExit(f'V19W2: expected exactly 4 V19V weapon_chainsaw gates, found {old_count}')
text = text.replace(f'"{old_gate}"', f'"{new_gate}"')

# Stock Doom 3 1.3.1 uses slot 11 for weapon_flashlight and slot 12 for
# weapon_pda. Slots 13-15 are unused. Put the Lightning Gun in slot 13 so
# flashlight/PDA inventory pickups remain valid and no stock slot is stolen.
spawn_marker = '''void idPlayer::Spawn( void ) {\n\tidStr\t\ttemp;\n\tidBounds\tbounds;\n'''
spawn_insert = '''void idPlayer::Spawn( void ) {\n\tidStr\t\ttemp;\n\tidBounds\tbounds;\n\n\t// V19W2: the Q4 Lightning Gun is a true additional Doom 3 weapon.\n\t// Stock Doom 3 1.3.1 uses slot 11 for the flashlight and 12 for the PDA;\n\t// slot 13 is genuinely unused. Keep this local to the player spawnArgs so\n\t// no wholesale player.def replacement is required.\n\tspawnArgs.Set( "def_weapon13", "weapon_lightninggun" );\n\tspawnArgs.Set( "weapon13_best", "1" );\n\tspawnArgs.Set( "weapon13_cycle", "1" );\n\tspawnArgs.Set( "weapon13_toggle", "0" );\n\tspawnArgs.Set( "weapon13_allowempty", "1" );\n\tspawnArgs.Set( "weapon13_visible", "1" );\n'''
if text.count(spawn_marker) != 1:
    raise SystemExit(f'V19W2: player Spawn marker count was {text.count(spawn_marker)}')
text = text.replace(spawn_marker, spawn_insert, 1)

# The new classname naturally produces the player animation prefix
# "lightninggun". Reuse Doom 3's proven two-handed Plasma Gun body animation
# prefix while still loading the actual weapon_lightninggun weaponDef.
anim_pattern = re.compile(
    r'(?P<indent>\t+)animPrefix = spawnArgs\.GetString\( va\( "def_weapon%d", currentWeapon \) \);\n'
    r'(?P=indent)weapon\.GetEntity\(\)->GetWeaponDef\( animPrefix, inventory\.clip\[ currentWeapon \] \);\n'
    r'(?P=indent)animPrefix\.Strip\( "weapon_" \);\n'
)

def anim_repl(m):
    i = m.group('indent')
    return (
        f'{i}animPrefix = spawnArgs.GetString( va( "def_weapon%d", currentWeapon ) );\n'
        f'{i}weapon.GetEntity()->GetWeaponDef( animPrefix, inventory.clip[ currentWeapon ] );\n'
        f'{i}if ( !idStr::Icmp( animPrefix.c_str(), "weapon_lightninggun" ) ) {{\n'
        f'{i}\t// Two-handed world/player stance: reuse the native Plasma Gun set.\n'
        f'{i}\tanimPrefix = "weapon_plasmagun";\n'
        f'{i}}}\n'
        f'{i}animPrefix.Strip( "weapon_" );\n'
    )

text, anim_hits = anim_pattern.subn(anim_repl, text)
if anim_hits != 2:
    raise SystemExit(f'V19W2: expected 2 weapon-switch animPrefix blocks, found {anim_hits}')

checks = (
    'spawnArgs.Set( "def_weapon13", "weapon_lightninggun" )',
    'inventory.HasAmmo( weap ) || !idStr::Icmp( weap, "weapon_lightninggun" )',
    'idStr::Icmp( q4CurrentWeaponDef, "weapon_lightninggun" )',
    'animPrefix = "weapon_plasmagun";',
)
for needle in checks:
    if needle not in text:
        raise SystemExit(f'V19W2 verification missing: {needle}')
if 'spawnArgs.Set( "def_weapon11", "weapon_lightninggun" )' in text:
    raise SystemExit('V19W2: stale slot-11 Lightning Gun override remains')
if '"weapon_chainsaw"' in text:
    raise SystemExit('V19W2: stale quoted weapon_chainsaw runtime gate remains in generated Player.cpp')

player_cpp.write_text(text, encoding='utf-8')
print('V19W2 separate Lightning Gun slot applied')
print(' - slot 13 -> weapon_lightninggun')
print(' - stock slot 11 flashlight and slot 12 PDA remain untouched')
print(' - cycle/direct/empty-raise exception moved off weapon_chainsaw')
print(' - player third-person animation prefix aliases to plasmagun')
print(' - chainsaw classname is free for the future Q4 Gauntlet/Ripper')
