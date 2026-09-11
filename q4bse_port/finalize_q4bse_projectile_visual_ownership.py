#!/usr/bin/env python3
"""Finalize generic Raven fx_impact ownership for Doom 3 projectiles.

Run after promote_q4bse_gameplay.py and fix_q4bse_gameplay_compile.py.

This removes the old stock-plasma-only validation architecture. Any projectile
whose Raven fx_impact* spawnargs resolve to an effect gets BSE visual ownership:
  * the selected Raven effect is played at the real collision point/normal;
  * Doom 3 actor blood/wound effects are preserved;
  * Doom 3 non-bleeding AddDefaultDamageEffect is suppressed to avoid a second
    decal/impact visual and duplicate impact audio;
  * Doom 3 model_detonate / fallback particle presentation is suppressed when
    the projectile declares a generic Raven fx_impact/fx_impact_default fallback;
  * optional snd_q4bse_impact remains Doom 3-owned and is played only for
    non-bleeding impacts. BSE sound segments remain intentionally disabled.

Damage, physics, AI, projectile lifetime and explosion-light handling remain
Doom 3-owned.
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
        raise SystemExit(f"ERROR: Q4BSE visual ownership expected one {label}, found {hits}")
    text = text.replace(old, new, 1)


# 1) Generic gameplay playback: remember whether BSE actually owns this impact and
# optionally play a Doom 3 sound shader supplied by the projectile def.  We keep
# sound outside the BSE renderer until arbitrary Raven sound-segment semantics are
# implemented as a separate feature.
old_playback = '''\tconst char* q4bseImpactFx = Q4BSE_SelectProjectileImpactFx( projectileDef, collision, gameLocal.entities[collision.c.entityNum] );
\tif ( q4bseImpactFx && *q4bseImpactFx ) {
\t\tQ4BSE_PlayEffect( q4bseImpactFx, collision.endpos + collision.c.normal * 0.15f, collision.c.normal );
\t}
'''
new_playback = '''\tconst char* q4bseImpactFx = Q4BSE_SelectProjectileImpactFx( projectileDef, collision, gameLocal.entities[collision.c.entityNum] );
\tconst bool q4bseOwnsImpactVisual = ( q4bseImpactFx && *q4bseImpactFx );
\tif ( q4bseOwnsImpactVisual ) {
\t\tQ4BSE_PlayEffect( q4bseImpactFx, collision.endpos + collision.c.normal * 0.15f, collision.c.normal );

\t\t// Raven's HyperBlaster flesh FX does not use the ordinary energy-hit sound.
\t\t// Keep impact audio in Doom 3 for now and only play the optional BSE-impact
\t\t// shader for non-bleeding targets/world geometry.
\t\tif ( !gameLocal.entities[collision.c.entityNum]->spawnArgs.GetBool( "bleed" ) &&
\t\t\tspawnArgs.GetString( "snd_q4bse_impact" )[0] ) {
\t\t\tStartSound( "snd_q4bse_impact", SND_CHANNEL_ITEM, 0, true, NULL );
\t\t}
\t}
'''
replace_once(old_playback, new_playback, "generic Q4BSE projectile playback block")


# 2) BSE owns the visible world impact. Preserve Doom 3 actor blood/wounds, but do
# not also run AddDefaultDamageEffect for non-bleeding surfaces because it projects
# a second decal and can play a second impact sound.
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
\t\t// Keep Doom 3 actor blood/wound layering. If BSE owns the impact visual,
\t\t// suppress Doom 3's ordinary non-bleeding decal/impact effect.
\t\tif ( ent->spawnArgs.GetBool( "bleed" ) ) {
\t\t\tent->AddDamageEffect( collision, velocity, damageDefName );
\t\t} else if ( !q4bseOwnsImpactVisual ) {
\t\t\tAddDefaultDamageEffect( collision, velocity );
\t\t}
\t}
'''
replace_once(old_damage_fx, new_damage_fx, "native impact damage-effect block")


# 3) Explode() normally replaces the hidden projectile with model_detonate or a
# surface fallback particle. A projectile declaring a generic Raven fallback is a
# BSE visual projectile, so suppress those old converted Doom 3 impact particles.
old_model_select = '''\t// change the model, usually to a PRT
\tfxname = NULL;
\tif ( g_testParticle.GetInteger() == TEST_PARTICLE_IMPACT ) {
\t\tfxname = g_testParticleName.GetString();
\t} else {
\t\tfxname = spawnArgs.GetString( "model_detonate" );
\t}
'''
new_model_select = '''\t// change the model, usually to a PRT
\tconst bool q4bseOwnsImpactVisual =
\t\tspawnArgs.GetString( "fx_impact" )[0] ||
\t\tspawnArgs.GetString( "fx_impact_default" )[0];
\tfxname = NULL;
\tif ( !q4bseOwnsImpactVisual ) {
\t\tif ( g_testParticle.GetInteger() == TEST_PARTICLE_IMPACT ) {
\t\t\tfxname = g_testParticleName.GetString();
\t\t} else {
\t\t\tfxname = spawnArgs.GetString( "model_detonate" );
\t\t}
\t}
'''
replace_once(old_model_select, new_model_select, "Explode model_detonate selection")

old_fallback = '''\tif ( !( fxname && *fxname ) ) {
\t\tif ( ( surfaceType == SURFTYPE_NONE ) || ( surfaceType == SURFTYPE_METAL ) || ( surfaceType == SURFTYPE_STONE ) ) {
'''
new_fallback = '''\tif ( !q4bseOwnsImpactVisual && !( fxname && *fxname ) ) {
\t\tif ( ( surfaceType == SURFTYPE_NONE ) || ( surfaceType == SURFTYPE_METAL ) || ( surfaceType == SURFTYPE_STONE ) ) {
'''
replace_once(old_fallback, new_fallback, "Explode fallback impact-model gate")


# Hard gates. The old stock-plasma test must not survive this path.
for forbidden in (
    'q4bsePlasmaImpactTest',
    '!idStr::Icmp( GetEntityDefName(), "projectile_plasmablast" )',
):
    if forbidden in text:
        raise SystemExit(f"ERROR: stale stock-plasma validation wiring remains: {forbidden}")

for required in (
    'const bool q4bseOwnsImpactVisual = ( q4bseImpactFx && *q4bseImpactFx );',
    'StartSound( "snd_q4bse_impact", SND_CHANNEL_ITEM',
    'else if ( !q4bseOwnsImpactVisual )',
    'spawnArgs.GetString( "fx_impact" )[0]',
    '!q4bseOwnsImpactVisual && !( fxname && *fxname )',
):
    if required not in text:
        raise SystemExit(f"ERROR: Q4BSE visual ownership verification missing: {required}")

PROJECTILE.write_text(text, encoding="utf-8")

print("Q4BSE V13 PROJECTILE VISUAL OWNERSHIP PASS.")
print("  - generic Raven fx_impact* selection drives real projectile impacts")
print("  - BSE-owned impacts suppress Doom 3 world-impact decal/PRT duplication")
print("  - actor blood/wound layering remains enabled")
print("  - optional snd_q4bse_impact stays Doom 3-owned for non-bleeding impacts")
print("  - stock Doom 3 plasma is no longer hardwired to HyperBlaster BSE")
