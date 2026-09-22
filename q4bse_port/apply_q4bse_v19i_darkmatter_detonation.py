#!/usr/bin/env python3
'''V19I / user-facing V39: Q4 Dark Matter detonation lifecycle parity.

Runs after V19H.

The generic Doom 3 projectile bridge already plays Raven fx_impact during
Collide(), but Doom 3's stock idProjectile::Explode() has no concept of Raven's
separate fx_detonate spawnarg. Quake 4's DMG uses both:
    fx_impact   -> contact / surface impact
    fx_detonate -> actual explosion / detonation

This patch restores the missing detonation hook ONLY for the ported Dark Matter
projectile. It deliberately leaves all other projectiles untouched.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PROJECTILE = ROOT / 'neo' / 'game' / 'Projectile.cpp'
if not PROJECTILE.exists():
    raise SystemExit(f'ERROR: missing Projectile.cpp: {PROJECTILE}')

text = PROJECTILE.read_text(encoding='utf-8-sig')

old = '''	GetPhysics()->SetOrigin( collision.endpos + 2.0f * collision.c.normal );

	// default remove time
'''
new = '''	GetPhysics()->SetOrigin( collision.endpos + 2.0f * collision.c.normal );

	// Q4 Dark Matter detonation parity. Raven separates the ordinary contact
	// fx_impact from the actual fx_detonate explosion. Doom 3's stock projectile
	// lifecycle has no fx_detonate hook, so explicitly fire it here for the
	// ported DMG after the fly effect has been stopped and the impact point is
	// final.
	if ( spawnArgs.GetBool( "q4_darkmatter_projectile" ) ) {
		const char *q4DetonateFx = spawnArgs.GetString( "fx_detonate" );
		if ( q4DetonateFx && q4DetonateFx[0] ) {
			Q4BSE_PlayEffect(
				q4DetonateFx,
				collision.endpos + collision.c.normal * 0.15f,
				collision.c.normal );
		}
	}

	// default remove time
'''

hits = text.count(old)
if hits != 1:
    raise SystemExit(f'ERROR: V19I expected exactly one Explode origin anchor, found {hits}')
text = text.replace(old, new, 1)

for required in (
    'q4_darkmatter_projectile',
    'spawnArgs.GetString( "fx_detonate" )',
    'Q4BSE_PlayEffect(',
    'collision.endpos + collision.c.normal * 0.15f',
):
    if required not in text:
        raise SystemExit(f'ERROR: V19I verification missing: {required}')

PROJECTILE.write_text(text, encoding='utf-8')

print('Q4BSE V19I DARK MATTER DETONATION LIFECYCLE PARITY.')
print('  - fx_impact remains the contact/surface hook')
print('  - fx_detonate now fires from Explode() for q4_darkmatter_projectile')
print('  - fly effect is already stopped before detonation')
print('  - all unrelated projectile classes remain unchanged')
