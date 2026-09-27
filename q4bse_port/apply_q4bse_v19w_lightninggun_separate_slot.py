#!/usr/bin/env python3
'''V19W: move the finished Q4 Lightning Gun out of Doom 3's chainsaw slot.

The accepted V19V gun remains unchanged at the weapon/runtime level. This overlay:
- assigns weapon_lightninggun to Doom 3's unused weapon slot 11
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
    raise SystemExit(f'V19W prerequisite missing: {player_cpp}')

text = player_cpp.read_text(encoding='utf-8-sig')

# V19V intentionally special-cased weapon_chainsaw because the LG lived in that
# slot. V19W gives the LG its own real classname/slot, so move those four gates.
old_gate = 'weapon_chainsaw'
new_gate = 'weapon_lightninggun'
old_count = text.count(f'"{old_gate}"')
if old_count != 4:
    raise SystemExit(f'V19W: expected exactly 4 V19V weapon_chainsaw gates, found {old_count}')
text = text.replace(f'"{old_gate}"', f'"{new_gate}"')

# Populate Doom 3's unused slot 11 at runtime. This avoids replacing the full
# player.def and leaves stock slots, Soul Cube, PDA, etc. untouched.
spawn_marker = '''void idPlayer::Spawn( void ) {\n\tidStr\t\ttemp;\n\tidBounds\tbounds;\n'''
spawn_insert = '''void idPlayer::Spawn( void ) {\n\tidStr\t\ttemp;\n\tidBounds\tbounds;\n\n\t// V19W: the Q4 Lightning Gun is a true additional Doom 3 weapon.\n\t// Slot 11 is unused by the stock player definition. Keep this local to the\n\t// player spawnArgs so no wholesale player.def replacement is required.\n\tspawnArgs.Set( "def_weapon11", "weapon_lightninggun" );\n\tspawnArgs.Set( "weapon11_best", "1" );\n\tspawnArgs.Set( "weapon11_cycle", "1" );\n\tspawnArgs.Set( "weapon11_toggle", "0" );\n\tspawnArgs.Set( "weapon11_allowempty", "1" );\n\tspawnArgs.Set( "weapon11_visible", "1" );\n'''
if text.count(spawn_marker) != 1:
    raise SystemExit(f'V19W: player Spawn marker count was {text.count(spawn_marker)}')
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
    raise SystemExit(f'V19W: expected 2 weapon-switch animPrefix blocks, found {anim_hits}')

checks = (
    'spawnArgs.Set( "def_weapon11", "weapon_lightninggun" )',
    'inventory.HasAmmo( weap ) || !idStr::Icmp( weap, "weapon_lightninggun" )',
    'idStr::Icmp( q4CurrentWeaponDef, "weapon_lightninggun" )',
    'animPrefix = "weapon_plasmagun";',
)
for needle in checks:
    if needle not in text:
        raise SystemExit(f'V19W verification missing: {needle}')
if '"weapon_chainsaw"' in text:
    raise SystemExit('V19W: stale quoted weapon_chainsaw reference remains in generated Player.cpp')

player_cpp.write_text(text, encoding='utf-8')
print('V19W separate Lightning Gun slot applied')
print(' - slot 11 -> weapon_lightninggun')
print(' - cycle/direct/empty-raise exception moved off weapon_chainsaw')
print(' - player third-person animation prefix aliases to plasmagun')
print(' - chainsaw classname is free for the future Q4 Gauntlet/Ripper')
