#!/usr/bin/env python3
"""Wire stock Doom 3 plasma impacts to the proven Raven HyperBlaster impact for gameplay testing.

This is intentionally a narrow test override:
  * projectile_plasmablast (and the MP variant) always plays
    effects/weapons/hyperblaster/impact_default.fx through Q4BSE.
  * Doom 3's native non-bleeding impact decal/damage effect is suppressed for those bolts.
  * Doom 3's native model_detonate/fallback impact particle is suppressed for those bolts.
  * damage, actor blood effects, projectile physics, and snd_explode remain Doom 3-owned.

Run after promote_q4bse_gameplay.py and fix_q4bse_gameplay_compile.py.
"""
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PROJECTILE = ROOT / "neo" / "game" / "Projectile.cpp"

if not PROJECTILE.exists():
    raise SystemExit(f"ERROR: missing generated Projectile.cpp: {PROJECTILE}")

text = PROJECTILE.read_text(encoding="utf-8-sig")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f"ERROR: plasma test expected one {label}, found {hits}")
    text = text.replace(old, new, 1)


# 1) Force the stock plasma projectile through the exact Raven HyperBlaster impact FX.
# Other projectiles continue using normal fx_impact* spawnarg selection.
old_select = '''\tconst char* q4bseImpactFx = Q4BSE_SelectProjectileImpactFx( projectileDef, collision, gameLocal.entities[collision.c.entityNum] );
\tif ( q4bseImpactFx && *q4bseImpactFx ) {
\t\tQ4BSE_PlayEffect( q4bseImpactFx, collision.endpos + collision.c.normal * 0.15f, collision.c.normal );
\t}
'''
new_select = '''\tconst bool q4bsePlasmaImpactTest =
\t\t!idStr::Icmp( GetEntityDefName(), "projectile_plasmablast" ) ||
\t\t!idStr::Icmp( GetEntityDefName(), "projectile_plasmablast_mp" );
\tconst char* q4bseImpactFx = q4bsePlasmaImpactTest
\t\t? "effects/weapons/hyperblaster/impact_default.fx"
\t\t: Q4BSE_SelectProjectileImpactFx( projectileDef, collision, gameLocal.entities[collision.c.entityNum] );
\tif ( q4bseImpactFx && *q4bseImpactFx ) {
\t\tQ4BSE_PlayEffect( q4bseImpactFx, collision.endpos + collision.c.normal * 0.15f, collision.c.normal );
\t}
'''
replace_once(old_select, new_select, "Q4BSE projectile playback block")

# 2) Suppress Doom 3's normal world-impact decal/effect for plasma so the Raven effect is
# visually isolated. Keep actor-specific bleeding/blood effects intact.
old_damage_fx = '''\t// if the projectile causes a damage effect
\tif ( spawnArgs.GetBool( "impact_damage_effect" ) ) {
\t\t// if the hit entity has a special damage effect
\t\tif ( ent->spawnArgs.GetBool( "bleed" ) ) {
\t\t\tent->AddDamageEffect( collision, velocity, damageDefName );
\t\t} else {
\t\t\tAddDefaultDamageEffect( collision, velocity );
\t\t}
\t}
'''
new_damage_fx = '''\t// if the projectile causes a damage effect
\tif ( spawnArgs.GetBool( "impact_damage_effect" ) ) {
\t\t// Preserve actor blood/wound effects. For the plasma test, suppress Doom 3's
\t\t// ordinary world-impact decal so only the Raven BSE visual remains.
\t\tif ( ent->spawnArgs.GetBool( "bleed" ) ) {
\t\t\tent->AddDamageEffect( collision, velocity, damageDefName );
\t\t} else if ( !q4bsePlasmaImpactTest ) {
\t\t\tAddDefaultDamageEffect( collision, velocity );
\t\t}
\t}
'''
replace_once(old_damage_fx, new_damage_fx, "native impact damage-effect block")

# 3) Explode() normally swaps the hidden projectile to model_detonate (plasmaimpact.prt)
# or a surface fallback model. Disable that visual only for the stock plasma projectile.
old_model_select = '''\t// change the model, usually to a PRT
\tfxname = NULL;
\tif ( g_testParticle.GetInteger() == TEST_PARTICLE_IMPACT ) {
\t\tfxname = g_testParticleName.GetString();
\t} else {
\t\tfxname = spawnArgs.GetString( "model_detonate" );
\t}
'''
new_model_select = '''\t// change the model, usually to a PRT
\tconst bool q4bsePlasmaImpactTest =
\t\t!idStr::Icmp( GetEntityDefName(), "projectile_plasmablast" ) ||
\t\t!idStr::Icmp( GetEntityDefName(), "projectile_plasmablast_mp" );
\tfxname = NULL;
\tif ( q4bsePlasmaImpactTest ) {
\t\t// Q4BSE owns the plasma impact visual during this gameplay validation build.
\t\tfxname = NULL;
\t} else if ( g_testParticle.GetInteger() == TEST_PARTICLE_IMPACT ) {
\t\tfxname = g_testParticleName.GetString();
\t} else {
\t\tfxname = spawnArgs.GetString( "model_detonate" );
\t}
'''
replace_once(old_model_select, new_model_select, "Explode model_detonate selection")

old_fallback = '''\tif ( !( fxname && *fxname ) ) {
\t\tif ( ( surfaceType == SURFTYPE_NONE ) || ( surfaceType == SURFTYPE_METAL ) || ( surfaceType == SURFTYPE_STONE ) ) {
'''
new_fallback = '''\tif ( !q4bsePlasmaImpactTest && !( fxname && *fxname ) ) {
\t\tif ( ( surfaceType == SURFTYPE_NONE ) || ( surfaceType == SURFTYPE_METAL ) || ( surfaceType == SURFTYPE_STONE ) ) {
'''
replace_once(old_fallback, new_fallback, "Explode fallback impact-model gate")

# Hard gates: verify the test override and the real gameplay API are both present.
for required in (
    '"projectile_plasmablast"',
    '"effects/weapons/hyperblaster/impact_default.fx"',
    'Q4BSE_PlayEffect( q4bseImpactFx',
    'else if ( !q4bsePlasmaImpactTest )',
    '!q4bsePlasmaImpactTest && !( fxname && *fxname )',
):
    if required not in text:
        raise SystemExit(f"ERROR: plasma test verification missing: {required}")

PROJECTILE.write_text(text, encoding="utf-8")

print("Q4BSE V11 PLASMA GAMEPLAY TEST wiring PASS.")
print("  - projectile_plasmablast -> effects/weapons/hyperblaster/impact_default.fx")
print("  - native Doom 3 non-bleeding impact decal suppressed for plasma")
print("  - native Doom 3 plasmaimpact.prt/model_detonate suppressed for plasma")
print("  - damage, actor blood effects, physics, and snd_explode remain Doom 3-owned")
