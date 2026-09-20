#!/usr/bin/env python3
'''V19B: Dark Matter core_start -> idle core same-frame handoff.

Runs after V19A. Scoped ONLY to the in-gun Dark Matter core lifecycle.

Retail Quake 4 starts fx_core on Idle without explicitly stopping fx_core_start.
Our reconstructed BSE renderer does not yet present the long core_start tail with
retail fidelity, so preserving that full tail makes the grown ring/charge layers
remain visibly over the idle core and the recharged core no longer matches a
freshly-raised idle core.

This compatibility handoff keeps the important continuity:
  * core_start owns the entire recharge/generation sequence;
  * when Idle begins, fx_core is started FIRST at the exact live inner_ring
    transform;
  * only after fx_core exists, the old fx_core_start instance is stopped by path;
  * therefore there is no empty frame / lightning-off gap, but charge-only
    growth layers cannot spill into the idle state.

No FX declarations, projectile code, ring rotation, size tuning or render
primitive code are changed here.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
WEAPON = ROOT / 'neo' / 'game' / 'Weapon.cpp'

if not WEAPON.exists():
    raise SystemExit(f'ERROR: V19B prerequisite missing: {WEAPON}')

weapon = WEAPON.read_text(encoding='utf-8-sig')

old = '''		else if ( q4HaveCoreTransform && q4CoreRequest == 2 ) {
			// Raven StartRings(false): if we came from reload, preserve core_start's
			// natural tail and layer the looping idle core over it.
			if ( q4CoreMode != 1 ) {
				Q4BSE_StopEntityEffects( this );
			}
			const char *q4CoreFx = weaponDef->dict.GetString( "fx_core" );
			if ( q4CoreFx && q4CoreFx[0] ) {
				Q4BSE_AttachPersistentEffectToEntityTransform( q4CoreFx, this, q4CoreWorldOrigin, q4CoreWorldAxis );
				Q4BSE_SetEntityEffectsViewWeaponMode( this, owner ? owner->entityNumber + 1 : 0 );
			}
			if ( q4CoreMode == 0 ) {
				StartSound( "snd_rings", SND_CHANNEL_VOICE, 0, false, NULL );
			}
			q4CoreMode = 2;
			spawnArgs.Set( "_q4_dmg_core_mode", "2" );
			spawnArgs.Set( "_q4_dmg_core_request", "-1" );
		}'''

new = '''		else if ( q4HaveCoreTransform && q4CoreRequest == 2 ) {
			// V19B presentation handoff: bring the looping idle core online FIRST,
			// then remove only the one-shot recharge effect. This preserves a
			// continuous energized frame-to-frame handoff without allowing the
			// long-lived core_start ring/growth tail to sit on top of idle.
			if ( q4CoreMode != 1 ) {
				Q4BSE_StopEntityEffects( this );
			}
			const char *q4CoreFx = weaponDef->dict.GetString( "fx_core" );
			if ( q4CoreFx && q4CoreFx[0] ) {
				Q4BSE_AttachPersistentEffectToEntityTransform( q4CoreFx, this, q4CoreWorldOrigin, q4CoreWorldAxis );
				Q4BSE_SetEntityEffectsViewWeaponMode( this, owner ? owner->entityNumber + 1 : 0 );
			}

			if ( q4CoreMode == 1 ) {
				const char *q4CoreStartFx = weaponDef->dict.GetString( "fx_core_start" );
				if ( q4CoreStartFx && q4CoreStartFx[0] ) {
					Q4BSE_StopEntityEffectPath( this, q4CoreStartFx );
				}
			}

			if ( q4CoreMode == 0 ) {
				StartSound( "snd_rings", SND_CHANNEL_VOICE, 0, false, NULL );
			}
			q4CoreMode = 2;
			spawnArgs.Set( "_q4_dmg_core_mode", "2" );
			spawnArgs.Set( "_q4_dmg_core_request", "-1" );
		}'''

hits = weapon.count(old)
if hits != 1:
    raise SystemExit(f'ERROR: V19B expected exactly one V19A idle handoff block, found {hits}')

weapon = weapon.replace(old, new, 1)

for required in (
    'V19B presentation handoff',
    'Q4BSE_AttachPersistentEffectToEntityTransform( q4CoreFx',
    'Q4BSE_StopEntityEffectPath( this, q4CoreStartFx )',
):
    if required not in weapon:
        raise SystemExit(f'ERROR: V19B verification missing: {required}')

WEAPON.write_text(weapon, encoding='utf-8')

print('Q4BSE V19B DARK MATTER CORE HANDOFF PASS.')
print('  - idle core starts first at live inner_ring transform')
print('  - only core_start is stopped immediately afterward')
print('  - no empty/lightning-off transition frame')
print('  - no lingering recharge ring/growth tail over idle')
print('  - projectile / renderer / FX declarations untouched')
