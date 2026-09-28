#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT = Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd()
PLAYER=ROOT/'Player.cpp' if (ROOT/'Player.cpp').exists() else ROOT/'neo/game/Player.cpp'
WEAPON=ROOT/'Weapon.cpp' if (ROOT/'Weapon.cpp').exists() else ROOT/'neo/game/Weapon.cpp'


def replace_once(text, old, new, label):
    hits=text.count(old)
    if hits!=1:
        raise SystemExit(f'ERROR {label}: expected 1 hit, got {hits}')
    return text.replace(old,new,1)

p=PLAYER.read_text(encoding='utf-8-sig')
w=WEAPON.read_text(encoding='utf-8-sig')

# Dedicated ammo max + reset legacy flashlight cvar at player spawn.
spawn_anchor='''void idPlayer::Spawn( void ) {\n\tidStr\t\ttemp;\n\tidBounds\tbounds;\n'''
spawn_new='''void idPlayer::Spawn( void ) {\n\tidStr\t\ttemp;\n\tidBounds\tbounds;\n\n\t// Q4 V19Z: the Lightning Gun still replaces weapon_chainsaw, but now owns\n\t// an independent Raven-style ammo reserve. Keep this global capacity in the\n\t// DLL so the Lightning Gun PK4 can remain self-contained.\n\tspawnArgs.Set( "max_ammo_lightninggun", "400" );\n\n\t// Stock Doom 3's flashlight weapon is no longer a usable weapon in the Q4\n\t// control scheme. The cvar is driven by the Machinegun flashlight action.\n\tcvarSystem->SetCVarBool( "q4_flashlight", false );\n'''
p=replace_once(p,spawn_anchor,spawn_new,'Spawn anchor')

# Replace NextWeapon and PrevWeapon as a pair by slicing exact function regions.
def replace_function(text, signature, next_marker, new_body):
    start=text.find(signature)
    if start<0: raise SystemExit(f'missing {signature}')
    end=text.find(next_marker,start)
    if end<0: raise SystemExit(f'missing marker after {signature}')
    return text[:start]+new_body+text[end:]

next_func=r'''void idPlayer::NextWeapon( void ) {
	const char *weap;
	int w;

	if ( !weaponEnabled || spectating || hiddenWeapon || gameLocal.inCinematic || gameLocal.world->spawnArgs.GetBool( "no_Weapons" ) || health < 0 ) {
		return;
	}

	if ( gameLocal.isClient || !inventory.weapons ) {
		return;
	}

	// Q4 V19Z: explicit gameplay cycle order. Soul Cube and Doom 3's handheld
	// flashlight are intentionally excluded from the mouse wheel. The Soul Cube
	// remains directly selectable, while the flashlight slot is a Machinegun
	// flashlight action handled by SelectWeapon().
	static const char *q4Cycle[] = {
		"weapon_fists",
		"weapon_pistol",
		"weapon_shotgun",
		"weapon_machinegun",
		"weapon_chaingun",
		"weapon_handgrenade",
		"weapon_plasmagun",
		"weapon_rocketlauncher",
		"weapon_chainsaw",
		"weapon_bfg"
	};
	const int q4Count = sizeof( q4Cycle ) / sizeof( q4Cycle[0] );
	int start = -1;
	for ( int i = 0; i < q4Count; ++i ) {
		if ( SlotForWeapon( q4Cycle[i] ) == idealWeapon ) {
			start = i;
			break;
		}
	}

	// If a directly-selected utility weapon (Soul Cube/PDA/etc.) is active, map
	// its numeric position to a sensible point in the Q4 cycle before advancing.
	if ( start < 0 ) {
		const char *currentDef = spawnArgs.GetString( va( "def_weapon%d", idealWeapon ) );
		if ( !idStr::Icmp( currentDef, "weapon_soulcube" ) ) {
			start = 7; // after Rocket comes Lightning Gun
		} else if ( !idStr::Icmp( currentDef, "weapon_flashlight" ) ) {
			start = 2; // legacy flashlight maps around the Machinegun position
		} else {
			start = q4Count - 1;
		}
	}

	w = idealWeapon;
	for ( int step = 1; step <= q4Count; ++step ) {
		const int orderIndex = ( start + step ) % q4Count;
		const int candidate = SlotForWeapon( q4Cycle[ orderIndex ] );
		if ( candidate < 0 || candidate >= MAX_WEAPONS ) {
			continue;
		}
		weap = spawnArgs.GetString( va( "def_weapon%d", candidate ) );
		if ( !weap[0] || !spawnArgs.GetBool( va( "weapon%d_cycle", candidate ) ) ) {
			continue;
		}
		if ( ( inventory.weapons & ( 1 << candidate ) ) == 0 ) {
			continue;
		}
		if ( !inventory.HasAmmo( weap ) && idStr::Icmp( weap, "weapon_chainsaw" ) ) {
			continue;
		}
		w = candidate;
		break;
	}

	if ( ( w != currentWeapon ) && ( w != idealWeapon ) ) {
		idealWeapon = w;
		weaponSwitchTime = gameLocal.time + WEAPON_SWITCH_DELAY;
		UpdateHudWeapon();
	}
}

'''
prev_func=r'''void idPlayer::PrevWeapon( void ) {
	const char *weap;
	int w;

	if ( !weaponEnabled || spectating || hiddenWeapon || gameLocal.inCinematic || gameLocal.world->spawnArgs.GetBool( "no_Weapons" ) || health < 0 ) {
		return;
	}

	if ( gameLocal.isClient || !inventory.weapons ) {
		return;
	}

	static const char *q4Cycle[] = {
		"weapon_fists",
		"weapon_pistol",
		"weapon_shotgun",
		"weapon_machinegun",
		"weapon_chaingun",
		"weapon_handgrenade",
		"weapon_plasmagun",
		"weapon_rocketlauncher",
		"weapon_chainsaw",
		"weapon_bfg"
	};
	const int q4Count = sizeof( q4Cycle ) / sizeof( q4Cycle[0] );
	int start = -1;
	for ( int i = 0; i < q4Count; ++i ) {
		if ( SlotForWeapon( q4Cycle[i] ) == idealWeapon ) {
			start = i;
			break;
		}
	}

	if ( start < 0 ) {
		const char *currentDef = spawnArgs.GetString( va( "def_weapon%d", idealWeapon ) );
		if ( !idStr::Icmp( currentDef, "weapon_soulcube" ) ) {
			start = 9; // previous from Soul Cube lands on Dark Matter
		} else if ( !idStr::Icmp( currentDef, "weapon_flashlight" ) ) {
			start = 4; // previous around the Machinegun position
		} else {
			start = 0;
		}
	}

	w = idealWeapon;
	for ( int step = 1; step <= q4Count; ++step ) {
		int orderIndex = start - step;
		while ( orderIndex < 0 ) {
			orderIndex += q4Count;
		}
		const int candidate = SlotForWeapon( q4Cycle[ orderIndex ] );
		if ( candidate < 0 || candidate >= MAX_WEAPONS ) {
			continue;
		}
		weap = spawnArgs.GetString( va( "def_weapon%d", candidate ) );
		if ( !weap[0] || !spawnArgs.GetBool( va( "weapon%d_cycle", candidate ) ) ) {
			continue;
		}
		if ( ( inventory.weapons & ( 1 << candidate ) ) == 0 ) {
			continue;
		}
		if ( !inventory.HasAmmo( weap ) && idStr::Icmp( weap, "weapon_chainsaw" ) ) {
			continue;
		}
		w = candidate;
		break;
	}

	if ( ( w != currentWeapon ) && ( w != idealWeapon ) ) {
		idealWeapon = w;
		weaponSwitchTime = gameLocal.time + WEAPON_SWITCH_DELAY;
		UpdateHudWeapon();
	}
}

'''
p=replace_function(p,'void idPlayer::NextWeapon( void ) {','/*\n===============\nidPlayer::PrevWeapon',next_func)
p=replace_function(p,'void idPlayer::PrevWeapon( void ) {','/*\n===============\nidPlayer::SelectWeapon',prev_func)

# Flashlight slot becomes a Q4 Machinegun flashlight action rather than a weapon.
sel_anchor='''\tweap = spawnArgs.GetString( va( "def_weapon%d", num ) );\n\tif ( !weap[ 0 ] ) {\n\t\tgameLocal.Printf( "Invalid weapon\\n" );\n\t\treturn;\n\t}\n\n\tif ( force || ( inventory.weapons & ( 1 << num ) ) ) {'''
sel_new='''\tweap = spawnArgs.GetString( va( "def_weapon%d", num ) );\n\tif ( !weap[ 0 ] ) {\n\t\tgameLocal.Printf( "Invalid weapon\\n" );\n\t\treturn;\n\t}\n\n\t// Q4 V19Z: Doom 3's flashlight slot is now a virtual Q4 flashlight action.\n\t// F can stay bound to _impulse11: from another weapon it raises the\n\t// Machinegun with its light ON; while already on the Machinegun it toggles\n\t// that light. The stock handheld flashlight can never become currentWeapon.\n\tif ( !idStr::Icmp( weap, "weapon_flashlight" ) ) {\n\t\tconst int mgSlot = SlotForWeapon( "weapon_machinegun" );\n\t\tif ( mgSlot < 0 || mgSlot >= MAX_WEAPONS || ( inventory.weapons & ( 1 << mgSlot ) ) == 0 ) {\n\t\t\treturn;\n\t\t}\n\n\t\tif ( currentWeapon == mgSlot && idealWeapon == mgSlot ) {\n\t\t\tcvarSystem->SetCVarBool( "q4_flashlight", !cvarSystem->GetCVarBool( "q4_flashlight" ) );\n\t\t} else {\n\t\t\tcvarSystem->SetCVarBool( "q4_flashlight", true );\n\t\t\tidealWeapon = mgSlot;\n\t\t\tweaponSwitchTime = gameLocal.time + WEAPON_SWITCH_DELAY;\n\t\t\tUpdateHudWeapon();\n\t\t}\n\t\treturn;\n\t}\n\n\tif ( force || ( inventory.weapons & ( 1 << num ) ) ) {'''
p=replace_once(p,sel_anchor,sel_new,'SelectWeapon flashlight redirect')

# When an illuminated Machinegun is actually put away, reset the persistent cvar
# so the next F press from another weapon always produces a 0->1 transition.
holster_anchor='''\t\t\tif ( weapon.GetEntity()->IsHolstered() ) {\n\t\t\t\tassert( idealWeapon >= 0 );\n\t\t\t\tassert( idealWeapon < MAX_WEAPONS );\n\n\t\t\t\tif ( currentWeapon != weapon_pda && !spawnArgs.GetBool( va( "weapon%d_toggle", currentWeapon ) ) ) {'''
holster_new='''\t\t\tif ( weapon.GetEntity()->IsHolstered() ) {\n\t\t\t\tassert( idealWeapon >= 0 );\n\t\t\t\tassert( idealWeapon < MAX_WEAPONS );\n\n\t\t\t\tconst char *q4OldWeaponDef = spawnArgs.GetString( va( "def_weapon%d", currentWeapon ) );\n\t\t\t\tconst char *q4NewWeaponDef = spawnArgs.GetString( va( "def_weapon%d", idealWeapon ) );\n\t\t\t\tif ( !idStr::Icmp( q4OldWeaponDef, "weapon_machinegun" ) && idStr::Icmp( q4NewWeaponDef, "weapon_machinegun" ) ) {\n\t\t\t\t\tcvarSystem->SetCVarBool( "q4_flashlight", false );\n\t\t\t\t}\n\n\t\t\t\tif ( currentWeapon != weapon_pda && !spawnArgs.GetBool( va( "weapon%d_toggle", currentWeapon ) ) ) {'''
p=replace_once(p,holster_anchor,holster_new,'Weapon_Combat flashlight reset')

# Dedicated ammo index 10. Doom 3 base data uses 0..9 and engine reserves 16 slots.
ammo_num_anchor='''\tassert( ammoname );\n\n\tammoDict = gameLocal.FindEntityDefDict( "ammo_types", false );'''
ammo_num_new='''\tassert( ammoname );\n\n\t// Q4 V19Z: independent Lightning Gun reserve.\n\tif ( !idStr::Icmp( ammoname, "ammo_lightninggun" ) ) {\n\t\treturn ( ammo_t )10;\n\t}\n\n\tammoDict = gameLocal.FindEntityDefDict( "ammo_types", false );'''
w=replace_once(w,ammo_num_anchor,ammo_num_new,'GetAmmoNumForName')

ammo_name_anchor='''\tchar text[ 32 ];\n\n\tammoDict = gameLocal.FindEntityDefDict( "ammo_types", false );'''
ammo_name_new='''\tchar text[ 32 ];\n\n\tif ( ammonum == ( ammo_t )10 ) {\n\t\treturn "ammo_lightninggun";\n\t}\n\n\tammoDict = gameLocal.FindEntityDefDict( "ammo_types", false );'''
w=replace_once(w,ammo_name_anchor,ammo_name_new,'GetAmmoNameForNum')

pickup_anchor='''\tconst idKeyValue *kv;\n\n\tammoDict = gameLocal.FindEntityDefDict( "ammo_names", false );'''
pickup_new='''\tconst idKeyValue *kv;\n\n\tif ( ammonum == ( ammo_t )10 ) {\n\t\treturn "Lightning Ammo";\n\t}\n\n\tammoDict = gameLocal.FindEntityDefDict( "ammo_names", false );'''
w=replace_once(w,pickup_anchor,pickup_new,'GetAmmoPickupNameForNum')

for needle in [
    'spawnArgs.Set( "max_ammo_lightninggun", "400" )',
    '"weapon_rocketlauncher",\n\t\t"weapon_chainsaw",\n\t\t"weapon_bfg"',
    'if ( !idStr::Icmp( weap, "weapon_flashlight" ) )',
    'SlotForWeapon( "weapon_machinegun" )',
    'SetCVarBool( "q4_flashlight", true )',
    'idStr::Icmp( weap, "weapon_chainsaw" )',
]:
    if needle not in p: raise SystemExit('missing player verification '+needle)
for needle in ['ammoname, "ammo_lightninggun"','return ( ammo_t )10;','return "ammo_lightninggun"','return "Lightning Ammo"']:
    if needle not in w: raise SystemExit('missing weapon verification '+needle)

PLAYER.write_text(p,encoding='utf-8')
WEAPON.write_text(w,encoding='utf-8')
print('V19Z patch PASS')
