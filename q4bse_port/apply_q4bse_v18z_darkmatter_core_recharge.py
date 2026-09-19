#!/usr/bin/env python3
'''V18Z: Dark Matter CORE-ONLY recharge lifecycle parity.

Runs after V18Y. No projectile/impact/collision/suction changes.

Fixes the missing Quake 4 "core grows back during reload" behavior:
  * reload state is driven by Doom 3's authoritative WP_RELOAD status, with the
    animation name retained only as a fallback;
  * entering reload stops the old idle core and starts fx_core_start once;
  * reload -> idle does NOT kill fx_core_start. Raven lets the charge effect
    finish naturally while the persistent idle core comes online;
  * ring/core loop sound is not needlessly stopped/restarted on reload -> idle;
  * fire/holster/non-core states still clear all attached core FX.

The existing V18X live inner_ring transform and V18Y weaponDepthHack projection
remain untouched.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
WEAPON = ROOT / 'neo' / 'game' / 'Weapon.cpp'

if not WEAPON.exists():
    raise SystemExit(f'ERROR: V18Z prerequisite missing: {WEAPON}')

weapon = WEAPON.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V18Z expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)


# Authoritative reload status. The anim name remains a fallback for unusual
# script timing, but WP_RELOAD is what weaponReloading() actually controls.
weapon = replace_once(
    weapon,
    '''		const bool q4DmgReloading = q4DmgAnimName && !idStr::Icmp( q4DmgAnimName, "reload" );
		const bool q4DmgIdle = q4DmgAnimName && !idStr::Icmp( q4DmgAnimName, "idle" );''',
    '''		const bool q4DmgReloadAnim = q4DmgAnimName && !idStr::Icmp( q4DmgAnimName, "reload" );
		const bool q4DmgReloading = ( status == WP_RELOAD ) || q4DmgReloadAnim;
		const bool q4DmgIdle = !q4DmgReloading && q4DmgAnimName && !idStr::Icmp( q4DmgAnimName, "idle" );''',
    'authoritative Dark Matter reload detection')


# V18X replaced path-specific cleanup with owner-wide cleanup. Keep that for
# entering reload / firing, but Raven does NOT stop coreStart when reload ends.
old_transition = '''		if ( q4DesiredCoreMode != q4CurrentCoreMode ) {
			const char *q4CoreStartFx = weaponDef->dict.GetString( "fx_core_start" );
			const char *q4CoreFx = weaponDef->dict.GetString( "fx_core" );
			// Core/core_start are the only persistent BSE effects attached to this
			// weapon. Avoid normalized-path mismatches by clearing them by owner.
			Q4BSE_StopEntityEffects( this );
			StopSound( SND_CHANNEL_VOICE, false );

			if ( q4DesiredCoreMode != 0 ) {'''

new_transition = '''		if ( q4DesiredCoreMode != q4CurrentCoreMode ) {
			const char *q4CoreStartFx = weaponDef->dict.GetString( "fx_core_start" );
			const char *q4CoreFx = weaponDef->dict.GetString( "fx_core" );
			const bool q4DmgReloadToIdle = ( q4CurrentCoreMode == 1 && q4DesiredCoreMode == 2 );

			// Raven's StartRings(false) does NOT stop coreStartEffect when reload
			// completes. Let the one-shot charge finish naturally and layer the
			// persistent idle core over its tail.
			if ( !q4DmgReloadToIdle ) {
				Q4BSE_StopEntityEffects( this );
			}

			// Keep the ring/core loop continuous through reload -> idle. It is
			// stopped only when the core/rings actually shut down.
			if ( q4DesiredCoreMode == 0 ) {
				StopSound( SND_CHANNEL_VOICE, false );
			}

			if ( q4DesiredCoreMode != 0 ) {'''

weapon = replace_once(weapon, old_transition, new_transition, 'Raven reload-to-idle core overlap')


# Current V18T starts the ring sound every time it creates either effect.
# Do that on charge entry or initial idle creation, but not on reload->idle
# where Raven's existing loop is already running.
old_sound = '''						StartSound( "snd_rings", SND_CHANNEL_VOICE, 0, false, NULL );'''
new_sound = '''						if ( !q4DmgReloadToIdle ) {
							StartSound( "snd_rings", SND_CHANNEL_VOICE, 0, false, NULL );
						}'''
weapon = replace_once(weapon, old_sound, new_sound, 'continuous ring sound across recharge')


# Track a timestamp for inspection/debugging and to make the charge edge explicit.
old_mode_set = '''			spawnArgs.Set( "_q4_dmg_core_mode", va( "%d", q4DesiredCoreMode ) );'''
new_mode_set = '''			if ( q4DesiredCoreMode == 1 ) {
				spawnArgs.Set( "_q4_dmg_charge_start_time", va( "%d", gameLocal.time ) );
			}
			spawnArgs.Set( "_q4_dmg_core_mode", va( "%d", q4DesiredCoreMode ) );'''
weapon = replace_once(weapon, old_mode_set, new_mode_set, 'charge start timestamp')


for required in (
    'status == WP_RELOAD',
    'q4DmgReloadToIdle',
    'Let the one-shot charge finish naturally',
    '_q4_dmg_charge_start_time',
):
    if required not in weapon:
        raise SystemExit(f'ERROR: V18Z verification missing: {required}')

WEAPON.write_text(weapon, encoding='utf-8')

print('Q4BSE V18Z DARK MATTER CORE RECHARGE PASS.')
print('  - WP_RELOAD is authoritative for core_start')
print('  - reload -> idle preserves one-shot core_start tail')
print('  - persistent idle core layers in without killing the recharge')
print('  - ring/core loop sound stays continuous through recharge')
print('  - projectile / impact / collision / suction untouched')
