#!/usr/bin/env python3
'''V19G / user-facing V29: Dark Matter travelling projectile parity foundation.

Runs after V19F.

Adds the two runtime behaviors that the Raven DMG projectile depends on:
  1) the proven native Dark Matter electricity renderer is also used by
     effects/weapons/dmg/fly.fx, with proper world-axis length transform;
  2) opt-in travelling radius damage / suction every damageRate seconds using
     def_radius_damage, matching rvDarkMatterProjectile::Think semantics.

Everything is spawnarg/path scoped so other Doom 3 / Q4 projectiles remain
untouched.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
PROJECTILE = ROOT / 'neo' / 'game' / 'Projectile.cpp'

for p in (IMPACT, PROJECTILE):
    if not p.exists():
        raise SystemExit(f'ERROR: V19G prerequisite missing: {p}')

impact = IMPACT.read_text(encoding='utf-8-sig')
projectile = PROJECTILE.read_text(encoding='utf-8-sig')

def replace_once(s, old, new, label):
    hits = s.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V19G expected exactly one {label}, found {hits}')
    return s.replace(old, new, 1)

# ---------------------------------------------------------------------------
# Native Raven-shaped electricity for the travelling Dark Matter projectile.
# V19C deliberately scoped the exact renderer to view-local core geometry and
# left projectile electricity on the old generic six-step ribbon.
#
# For fly.fx we need the same shape logic, but its authored length is effect-
# local and must be transformed into world space.
# ---------------------------------------------------------------------------
old_len = '''    const idVec3 length = EvalVec3(p.lengthStart, p.lengthEnd,
                                   FindDomain(pt.motion, "length"), life);
    const float mainLength = length.Length();'''
new_len = '''    const idVec3 localLength = EvalVec3(p.lengthStart, p.lengthEnd,
                                        FindDomain(pt.motion, "length"), life);
    const idVec3 length = g_m3Impact.q4ViewLocalGeometry
        ? localLength
        : (g_m3Impact.axis * localLength);
    const float mainLength = length.Length();'''
impact = replace_once(impact, old_len, new_len, 'native electricity world-length transform')

old_side = '''    idVec3 side = length.Cross(viewOrigin);
    if (side.LengthSqr() > M3_EPSILON) side.NormalizeFast();
    else side = viewAxis[1];
    side *= width;'''
new_side = '''    idVec3 q4ViewVector = viewOrigin;
    if (!g_m3Impact.q4ViewLocalGeometry) {
        q4ViewVector = viewOrigin - (worldPos + length * 0.5f);
    }
    idVec3 side = length.Cross(q4ViewVector);
    if (side.LengthSqr() > M3_EPSILON) side.NormalizeFast();
    else side = viewAxis[1];
    side *= width;'''
impact = replace_once(impact, old_side, new_side, 'native electricity world view vector')

old_dispatch = '''    if (pt.primitive == "electricity") {
        if (g_m3Impact.q4ViewLocalGeometry) {
            return RenderQ4DarkMatterElectricity(model, p, pt, elapsedSec, age, life,
                                                 worldPos, viewOrigin, viewAxis, color);
        }

        // Keep the already-accepted generic/projectile bridge unchanged.'''
new_dispatch = '''    if (pt.primitive == "electricity") {
        const bool q4DarkMatterFly =
            !idStr::Icmp(g_m3Impact.effectPath.c_str(), "effects/weapons/dmg/fly.fx");
        if (g_m3Impact.q4ViewLocalGeometry || q4DarkMatterFly) {
            return RenderQ4DarkMatterElectricity(model, p, pt, elapsedSec, age, life,
                                                 worldPos, viewOrigin, viewAxis, color);
        }

        // Keep all unrelated generic/projectile electricity unchanged.'''
impact = replace_once(impact, old_dispatch, new_dispatch, 'Dark Matter fly native electricity dispatch')

# ---------------------------------------------------------------------------
# Raven rvDarkMatterProjectile::Think parity.
#
# Q4 does:
#   idProjectile::Think();
#   every damageRate (.05 sec):
#       RadiusDamage(origin, ..., def_radius_damage)
#
# Avoid class layout changes by storing the next tick in private spawnargs.
# Server/single-player owns damage; clients only render/predict.
# ---------------------------------------------------------------------------
think_anchor = '''	// run physics
	RunPhysics();

	Present();'''

think_new = '''	// run physics
	RunPhysics();

	// Q4 Dark Matter travelling suction/damage field. Raven's
	// rvDarkMatterProjectile applies def_radius_damage every damageRate seconds
	// while the projectile is live. Keep this opt-in to the DMG port.
	if ( state == LAUNCHED && spawnArgs.GetBool( "q4_darkmatter_projectile" ) && !gameLocal.isClient ) {
		int q4NextDamageTime = spawnArgs.GetInt( "_q4_dmg_next_damage_time", "0" );
		if ( gameLocal.time > q4NextDamageTime ) {
			const char *q4RadiusDamage = spawnArgs.GetString( "def_radius_damage" );
			if ( q4RadiusDamage && q4RadiusDamage[0] ) {
				gameLocal.RadiusDamage(
					GetPhysics()->GetOrigin(),
					this,
					owner.GetEntity(),
					owner.GetEntity(),
					owner.GetEntity(),
					q4RadiusDamage,
					1.0f );
			}
			float q4DamageRate = spawnArgs.GetFloat( "damageRate", ".05" );
			if ( q4DamageRate < 0.001f ) q4DamageRate = 0.001f;
			spawnArgs.Set( "_q4_dmg_next_damage_time",
				va( "%d", gameLocal.time + SEC2MS( q4DamageRate ) ) );
		}
	}

	Present();'''
projectile = replace_once(projectile, think_anchor, think_new, 'projectile travelling radius-damage hook')

for required in (
    'q4DarkMatterFly',
    'effects/weapons/dmg/fly.fx',
    'q4_darkmatter_projectile',
    'def_radius_damage',
    '_q4_dmg_next_damage_time',
    'gameLocal.RadiusDamage(',
):
    if required not in impact + projectile:
        raise SystemExit(f'ERROR: V19G verification missing: {required}')

IMPACT.write_text(impact, encoding='utf-8')
PROJECTILE.write_text(projectile, encoding='utf-8')

print('Q4BSE V19G DARK MATTER PROJECTILE PARITY FOUNDATION.')
print('  - fly.fx electricity now uses the native Raven-shaped Dark Matter renderer')
print('  - fly electricity authored local length is transformed into world space')
print('  - travelling 50 ms def_radius_damage / suction loop restored via spawnarg opt-in')
print('  - unrelated projectile paths remain unchanged')
