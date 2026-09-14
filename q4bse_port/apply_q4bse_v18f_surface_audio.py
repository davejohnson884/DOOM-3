#!/usr/bin/env python3
"""V18F: Doom 3 surface/flesh impact audio for BSE-owned projectile visuals.

The Raven BSE renderer owns visuals for opt-in projectiles such as the Q4 nailgun,
so Doom 3's normal AddDefaultDamageEffect path is intentionally suppressed to avoid
stacking a second decal/particle effect.  That also suppressed Doom 3's material-
specific impact audio.  This pass restores AUDIO ONLY, behind an opt-in spawnarg:

    q4UseD3ImpactAudio 1

For an opted-in BSE projectile:
  * bleeding targets use projectile snd_flesh;
  * world/non-bleeding hits use snd_<surface type>;
  * missing surface keys fall back to snd_metal, then snd_impact.

No Doom 3 impact visuals are re-enabled.  Existing optional snd_q4bse_impact
behavior remains as the fallback for other BSE projectiles.
"""

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PROJECTILE = ROOT / "neo" / "game" / "Projectile.cpp"

if not PROJECTILE.exists():
    raise SystemExit(f"ERROR: V18F missing Projectile.cpp: {PROJECTILE}")

text = PROJECTILE.read_text(encoding="utf-8-sig")

old = '''\t\t// Raven's HyperBlaster flesh FX does not use the ordinary energy-hit sound.
\t\t// Keep impact audio in Doom 3 for now and only play the optional BSE-impact
\t\t// shader for non-bleeding targets/world geometry.
\t\tif ( !gameLocal.entities[collision.c.entityNum]->spawnArgs.GetBool( "bleed" ) &&
\t\t\tspawnArgs.GetString( "snd_q4bse_impact" )[0] ) {
\t\t\tStartSound( "snd_q4bse_impact", SND_CHANNEL_ITEM, 0, true, NULL );
\t\t}
'''

new = '''\t\t// Q4 V18F: BSE may own the visible impact while Doom 3 still owns impact
\t\t// AUDIO.  Opted-in projectiles use the same stock surface-key lookup as
\t\t// idProjectile::DefaultDamageEffect, but without projecting another decal
\t\t// or spawning Doom 3's competing impact particle.
\t\tif ( spawnArgs.GetBool( "q4UseD3ImpactAudio" ) ) {
\t\t\tconst bool q4BleedImpact = gameLocal.entities[collision.c.entityNum]->spawnArgs.GetBool( "bleed" );
\t\t\tconst char *q4ImpactSound = NULL;

\t\t\tif ( q4BleedImpact ) {
\t\t\t\tq4ImpactSound = spawnArgs.GetString( "snd_flesh" );
\t\t\t} else {
\t\t\t\tconst surfTypes_t q4SurfaceType = collision.c.material ? collision.c.material->GetSurfaceType() : SURFTYPE_METAL;
\t\t\t\tconst char *q4SurfaceName = gameLocal.sufaceTypeNames[ q4SurfaceType ];
\t\t\t\tidStr q4SoundKey = va( "snd_%s", q4SurfaceName );
\t\t\t\tq4ImpactSound = spawnArgs.GetString( q4SoundKey.c_str() );
\t\t\t\tif ( !q4ImpactSound[0] ) {
\t\t\t\t\tq4ImpactSound = spawnArgs.GetString( "snd_metal" );
\t\t\t\t}
\t\t\t\tif ( !q4ImpactSound[0] ) {
\t\t\t\t\tq4ImpactSound = spawnArgs.GetString( "snd_impact" );
\t\t\t\t}
\t\t\t}

\t\t\tif ( q4ImpactSound && q4ImpactSound[0] ) {
\t\t\t\tStartSoundShader( declManager->FindSound( q4ImpactSound ), SND_CHANNEL_BODY, 0, false, NULL );
\t\t\t}
\t\t} else if ( !gameLocal.entities[collision.c.entityNum]->spawnArgs.GetBool( "bleed" ) &&
\t\t\tspawnArgs.GetString( "snd_q4bse_impact" )[0] ) {
\t\t\t// Preserve the previously-proven one-shader override for older BSE content.
\t\t\tStartSound( "snd_q4bse_impact", SND_CHANNEL_ITEM, 0, true, NULL );
\t\t}
'''

hits = text.count(old)
if hits != 1:
    raise SystemExit(f"ERROR: V18F expected one BSE impact-audio block, found {hits}")
text = text.replace(old, new, 1)

for needle in (
    'GetBool( "q4UseD3ImpactAudio" )',
    'GetString( "snd_flesh" )',
    'va( "snd_%s", q4SurfaceName )',
    'GetString( "snd_metal" )',
    'GetString( "snd_impact" )',
    'StartSoundShader( declManager->FindSound( q4ImpactSound )',
    'StartSound( "snd_q4bse_impact", SND_CHANNEL_ITEM',
):
    if needle not in text:
        raise SystemExit(f"ERROR: V18F verification missing: {needle}")

PROJECTILE.write_text(text, encoding="utf-8")

print("Q4BSE V18F SURFACE IMPACT AUDIO PASS.")
print("  - opt-in BSE visuals can use stock Doom 3 material-specific impact sounds")
print("  - bleeding targets use projectile snd_flesh")
print("  - world hits use snd_<surface>, then snd_metal / snd_impact fallback")
print("  - no Doom 3 impact visuals are re-enabled")
print("  - legacy snd_q4bse_impact fallback remains intact")
