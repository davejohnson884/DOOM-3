#!/usr/bin/env python3
'''V18H: preserve Raven/BSE projectile ownership, add Doom 3 impact presentation on opt-in.

Opt-in spawnarg:
    q4UseD3ImpactPresentation 1

This deliberately DOES NOT change q4bseOwnsImpactVisual and DOES NOT suppress
Raven/BSE projectile ownership. The Nailgun can therefore keep the exact proven
BSE muzzle/fly/runtime path from the combined PK4.

For an opted-in BSE projectile:
  * BSE ownership remains true and Q4BSE playback remains wired normally;
  * Doom 3 AddDefaultDamageEffect is additionally allowed for non-bleeding hits;
  * Doom 3 Explode() impact-particle selection is additionally allowed;
  * the content layer can point fx_impact* at Raven's no-op impact_none.fx so the
    BSE collision hook remains structurally intact without drawing a second hit;
  * Doom 3 then owns the visible collision decal/smoke/spark/ricochet and sound.

This is intentionally different from V18G: V18G changed BSE ownership itself.
V18H leaves ownership untouched and only layers native Doom 3 impact presentation.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PROJECTILE = ROOT / 'neo' / 'game' / 'Projectile.cpp'

if not PROJECTILE.exists():
    raise SystemExit(f'ERROR: V18H missing Projectile.cpp: {PROJECTILE}')

text = PROJECTILE.read_text(encoding='utf-8-sig')

old_damage = '''\t// if the projectile causes a damage effect
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
new_damage = '''\t// if the projectile causes a damage effect
\tif ( spawnArgs.GetBool( "impact_damage_effect" ) ) {
\t\t// Keep Doom 3 actor blood/wound layering. Normal BSE projectiles still
\t\t// suppress Doom 3's duplicate world hit. V18H opt-in projectiles retain
\t\t// BSE ownership but explicitly layer Doom 3's native world impact path.
\t\tif ( ent->spawnArgs.GetBool( "bleed" ) ) {
\t\t\tent->AddDamageEffect( collision, velocity, damageDefName );
\t\t} else if ( !q4bseOwnsImpactVisual || spawnArgs.GetBool( "q4UseD3ImpactPresentation" ) ) {
\t\t\tAddDefaultDamageEffect( collision, velocity );
\t\t}
\t}
'''

hits = text.count(old_damage)
if hits != 1:
    raise SystemExit(f'ERROR: V18H expected one native damage-effect block, found {hits}')
text = text.replace(old_damage, new_damage, 1)

old_model_gate = '''\tfxname = NULL;
\tif ( !q4bseOwnsImpactVisual ) {
\t\tif ( g_testParticle.GetInteger() == TEST_PARTICLE_IMPACT ) {
\t\t\tfxname = g_testParticleName.GetString();
\t\t} else {
\t\t\tfxname = spawnArgs.GetString( "model_detonate" );
\t\t}
\t}
'''
new_model_gate = '''\tfxname = NULL;
\tif ( !q4bseOwnsImpactVisual || spawnArgs.GetBool( "q4UseD3ImpactPresentation" ) ) {
\t\tif ( g_testParticle.GetInteger() == TEST_PARTICLE_IMPACT ) {
\t\t\tfxname = g_testParticleName.GetString();
\t\t} else {
\t\t\tfxname = spawnArgs.GetString( "model_detonate" );
\t\t}
\t}
'''

hits = text.count(old_model_gate)
if hits != 1:
    raise SystemExit(f'ERROR: V18H expected one Explode model-selection gate, found {hits}')
text = text.replace(old_model_gate, new_model_gate, 1)

old_fallback = '''\tif ( !q4bseOwnsImpactVisual && !( fxname && *fxname ) ) {
'''
new_fallback = '''\tif ( ( !q4bseOwnsImpactVisual || spawnArgs.GetBool( "q4UseD3ImpactPresentation" ) ) && !( fxname && *fxname ) ) {
'''

hits = text.count(old_fallback)
if hits != 1:
    raise SystemExit(f'ERROR: V18H expected one Explode fallback gate, found {hits}')
text = text.replace(old_fallback, new_fallback, 1)

required = (
    'const bool q4bseOwnsImpactVisual = ( q4bseImpactFx && *q4bseImpactFx );',
    'Q4BSE_PlayEffect( q4bseImpactFx, collision.endpos + collision.c.normal * 0.15f, collision.c.normal );',
    'spawnArgs.GetBool( "q4UseD3ImpactPresentation" )',
    'else if ( !q4bseOwnsImpactVisual || spawnArgs.GetBool( "q4UseD3ImpactPresentation" ) )',
    'spawnArgs.GetBool( "q4UseD3ImpactAudio" )',
)
for needle in required:
    if needle not in text:
        raise SystemExit(f'ERROR: V18H verification missing: {needle}')

for forbidden in (
    '!q4UseD3ImpactVisuals && ( q4bseImpactFx && *q4bseImpactFx )',
    'const bool q4UseD3ImpactVisuals = spawnArgs.GetBool( "q4UseD3ImpactVisuals" );',
):
    if forbidden in text:
        raise SystemExit(f'ERROR: V18H found stale V18G ownership override: {forbidden}')

PROJECTILE.write_text(text, encoding='utf-8')

print('Q4BSE V18H NATIVE IMPACT OVERLAY PASS.')
print('  - BSE q4bseOwnsImpactVisual remains unchanged')
print('  - BSE impact hook/runtime remains structurally active')
print('  - opt-in adds Doom 3 world decal + surface sound via AddDefaultDamageEffect')
print('  - opt-in adds Doom 3 smoke/spark/ricochet model selection in Explode')
print('  - muzzle/fly/BSE parser/runtime ownership is not modified')
