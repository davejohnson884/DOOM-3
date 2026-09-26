#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
weapon_h = root / "neo" / "game" / "Weapon.h"
weapon_cpp = root / "neo" / "game" / "Weapon.cpp"


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"V19Q: {label} anchor not found")
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# Weapon.h: transient renderer lights for the three ammo tubes, firing spires,
# and a short chain of point lights sampled along the live lightning beam.
# ---------------------------------------------------------------------------
text = weapon_h.read_text(encoding="utf-8")
anchor = '''\trenderEntity_t\t\t\t\tq4GuideBeam;\n\tint\t\t\t\t\t\tq4GuideBeamHandle;\n\trenderEntity_t\t\t\t\tq4GuideMarker;\n\tint\t\t\t\t\t\tq4GuideMarkerHandle;\n\n\t// muzzle flash\n'''
replacement = '''\trenderEntity_t\t\t\t\tq4GuideBeam;\n\tint\t\t\t\t\t\tq4GuideBeamHandle;\n\trenderEntity_t\t\t\t\tq4GuideMarker;\n\tint\t\t\t\t\t\tq4GuideMarkerHandle;\n\n\t// Q4 V19Q: local blue illumination for Lightning Gun electricity.\n\t// 0..2 = ammo tubes, 3 = firing-spire cluster, 4..9 = beam samples.\n\tenum { Q4_LG_COIL_LIGHT_COUNT = 3, Q4_LG_SPIRE_LIGHT = 3,\n\t\tQ4_LG_BEAM_LIGHT_FIRST = 4, Q4_LG_BEAM_LIGHT_COUNT = 6, Q4_LG_LIGHT_COUNT = 10 };\n\trenderLight_t\t\t\tq4LGLights[ Q4_LG_LIGHT_COUNT ];\n\tint\t\t\t\t\t\tq4LGLightHandles[ Q4_LG_LIGHT_COUNT ];\n\n\t// muzzle flash\n'''
text = replace_once(text, anchor, replacement, "Lightning Gun light fields")

anchor = '''\tvoid\t\t\t\t\t\tUpdateQ4LightningGun( void );\n\tvoid\t\t\t\t\t\tStopQ4LightningGunEffects( void );\n\tbool\t\t\t\t\t\tGetQ4PresentedJointTransform( jointHandle_t joint, idVec3 &origin, idMat3 &axis );\n'''
replacement = '''\tvoid\t\t\t\t\t\tUpdateQ4LightningGun( void );\n\tvoid\t\t\t\t\t\tStopQ4LightningGunEffects( void );\n\tvoid\t\t\t\t\t\tUpdateQ4LightningGunLight( int index, const idVec3 &origin, float radius, const idVec3 &color );\n\tvoid\t\t\t\t\t\tFreeQ4LightningGunLight( int index );\n\tvoid\t\t\t\t\t\tFreeQ4LightningGunLights( void );\n\tbool\t\t\t\t\t\tGetQ4PresentedJointTransform( jointHandle_t joint, idVec3 &origin, idMat3 &axis );\n'''
text = replace_once(text, anchor, replacement, "Lightning Gun light helper declarations")
weapon_h.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Weapon.cpp: initialize/free lights, sustain/stop Q4 view shake with trigger,
# and update the three requested lighting zones every render frame.
# ---------------------------------------------------------------------------
text = weapon_cpp.read_text(encoding="utf-8")
anchor = '''\tmemset( &q4GuideBeam, 0, sizeof( q4GuideBeam ) );\n\tmemset( &q4GuideMarker, 0, sizeof( q4GuideMarker ) );\n\n\tmuzzleFlashEnd'''
replacement = '''\tmemset( &q4GuideBeam, 0, sizeof( q4GuideBeam ) );\n\tmemset( &q4GuideMarker, 0, sizeof( q4GuideMarker ) );\n\tmemset( q4LGLights, 0, sizeof( q4LGLights ) );\n\tfor ( int i = 0; i < Q4_LG_LIGHT_COUNT; ++i ) {\n\t\tq4LGLightHandles[i] = -1;\n\t}\n\n\tmuzzleFlashEnd'''
text = replace_once(text, anchor, replacement, "constructor light initialization")

anchor = '''/*\n================\nidWeapon::StopQ4LightningGunEffects\n================\n*/\nvoid idWeapon::StopQ4LightningGunEffects( void ) {\n\tif ( !weaponDef || !weaponDef->dict.GetBool( "q4_lightning_runtime" ) ) return;\n'''
replacement = '''/*\n================\nidWeapon::UpdateQ4LightningGunLight\n\nSmall no-shadow point lights used only by the source-driven Lightning Gun.\nThey are view-local like Doom 3's view muzzle flash, so they light the gun and\nvisible world without leaking a first-person-only light into other player views.\n================\n*/\nvoid idWeapon::UpdateQ4LightningGunLight( int index, const idVec3 &origin, float radius, const idVec3 &color ) {\n\tif ( index < 0 || index >= Q4_LG_LIGHT_COUNT || !owner || radius <= 0.0f ) return;\n\n\trenderLight_t &light = q4LGLights[index];\n\tmemset( &light, 0, sizeof( light ) );\n\tlight.pointLight = true;\n\tlight.noShadows = true;\n\tlight.noSpecular = false;\n\tlight.allowLightInViewID = owner->entityNumber + 1;\n\tlight.origin = origin;\n\tlight.axis = mat3_identity;\n\tlight.lightRadius.Set( radius, radius, radius );\n\tlight.shader = muzzleFlash.shader ? muzzleFlash.shader : declManager->FindMaterial( "lights/muzzleflash", false );\n\tlight.shaderParms[ SHADERPARM_RED ] = color[0];\n\tlight.shaderParms[ SHADERPARM_GREEN ] = color[1];\n\tlight.shaderParms[ SHADERPARM_BLUE ] = color[2];\n\tlight.shaderParms[ SHADERPARM_TIMESCALE ] = 1.0f;\n\tlight.shaderParms[ SHADERPARM_TIMEOFFSET ] = -MS2SEC( gameLocal.time );\n\n\tif ( q4LGLightHandles[index] == -1 ) {\n\t\tq4LGLightHandles[index] = gameRenderWorld->AddLightDef( &light );\n\t} else {\n\t\tgameRenderWorld->UpdateLightDef( q4LGLightHandles[index], &light );\n\t}\n}\n\nvoid idWeapon::FreeQ4LightningGunLight( int index ) {\n\tif ( index < 0 || index >= Q4_LG_LIGHT_COUNT ) return;\n\tif ( q4LGLightHandles[index] != -1 ) {\n\t\tgameRenderWorld->FreeLightDef( q4LGLightHandles[index] );\n\t\tq4LGLightHandles[index] = -1;\n\t}\n}\n\nvoid idWeapon::FreeQ4LightningGunLights( void ) {\n\tfor ( int i = 0; i < Q4_LG_LIGHT_COUNT; ++i ) {\n\t\tFreeQ4LightningGunLight( i );\n\t}\n}\n\n/*\n================\nidWeapon::StopQ4LightningGunEffects\n================\n*/\nvoid idWeapon::StopQ4LightningGunEffects( void ) {\n\tFreeQ4LightningGunLights();\n\tif ( owner && !gameLocal.isMultiplayer && owner == gameLocal.GetLocalPlayer() ) {\n\t\towner->playerView.SetShakeParms( MS2SEC( gameLocal.time ), 0.0f );\n\t}\n\tif ( !weaponDef || !weaponDef->dict.GetBool( "q4_lightning_runtime" ) ) return;\n'''
text = replace_once(text, anchor, replacement, "light helpers before StopQ4LightningGunEffects")

anchor = '''\t\t\t\tfloat attenuation = ( ammo - tubeThreshold * (float)i ) / tubeThreshold;\n\t\t\t\tattenuation = idMath::ClampFloat( 0.0f, 1.0f, attenuation );\n\t\t\t\tQ4BSE_SetEntityEffectAttenuation( this, tubeFx, attenuation );\n\t\t\t}\n\t\t} else if ( wasOn ) {\n'''
replacement = '''\t\t\t\tfloat attenuation = ( ammo - tubeThreshold * (float)i ) / tubeThreshold;\n\t\t\t\tattenuation = idMath::ClampFloat( 0.0f, 1.0f, attenuation );\n\t\t\t\tQ4BSE_SetEntityEffectAttenuation( this, tubeFx, attenuation );\n\n\t\t\t\t// The authored tube bolt is emissive; give it a small real blue light\n\t\t\t\t// so nearby gun metal and the immediate surroundings receive the glow.\n\t\t\t\tconst idVec3 coilColor = weaponDef->dict.GetVector( "q4_lg_coil_light_color", "0.10 0.25 0.70" );\n\t\t\t\tconst float coilRadius = weaponDef->dict.GetFloat( "q4_lg_coil_light_radius", "42" );\n\t\t\t\tUpdateQ4LightningGunLight( i, tubeOrigin + tubeAxis[0] * 0.5f, coilRadius, coilColor * attenuation );\n\t\t\t}\n\t\t} else if ( wasOn ) {\n'''
text = replace_once(text, anchor, replacement, "ammo-tube glow")

anchor = '''\t\t\tStartSound( "snd_tube", SND_CHANNEL_ITEM, 0, false, NULL );\n\t\t\tspawnArgs.Set( onKey, "0" );\n\t\t}\n\t}\n\n\tconst bool firing'''
replacement = '''\t\t\tStartSound( "snd_tube", SND_CHANNEL_ITEM, 0, false, NULL );\n\t\t\tspawnArgs.Set( onKey, "0" );\n\t\t}\n\t\tif ( !shouldBeOn ) {\n\t\t\tFreeQ4LightningGunLight( i );\n\t\t}\n\t}\n\n\tconst bool firing'''
text = replace_once(text, anchor, replacement, "ammo-tube light shutdown")

anchor = '''\tif ( !firing ) {\n\t\tif ( spawnArgs.GetBool( "_q4_lg_firing", "0" ) ) {\n'''
replacement = '''\tif ( !firing ) {\n\t\t// Q4 stops the sustained screen shake with the trigger, not 500ms later.\n\t\tif ( !gameLocal.isMultiplayer && owner == gameLocal.GetLocalPlayer() ) {\n\t\t\towner->playerView.SetShakeParms( MS2SEC( gameLocal.time ), 0.0f );\n\t\t}\n\t\t// Tubes stay lit while charged; firing-spire and beam illumination do not.\n\t\tfor ( int i = Q4_LG_SPIRE_LIGHT; i < Q4_LG_LIGHT_COUNT; ++i ) {\n\t\t\tFreeQ4LightningGunLight( i );\n\t\t}\n\t\tif ( spawnArgs.GetBool( "_q4_lg_firing", "0" ) ) {\n'''
text = replace_once(text, anchor, replacement, "instant transient light/shake release")

anchor = '''\tconst bool wasFiring = spawnArgs.GetBool( "_q4_lg_firing", "0" );\n\tif ( !wasFiring ) {\n\t\t// Raven WeaponLightningGun.cpp: entering the continuous firing loop gives\n\t\t// the local player a 500ms, scale-2 view shake instead of model recoil.\n\t\tif ( !gameLocal.isMultiplayer && owner == gameLocal.GetLocalPlayer() ) {\n\t\t\towner->playerView.SetShakeParms( MS2SEC( gameLocal.time + 500 ), 2.0f );\n\t\t}\n\n\t\t// Raven State_Fire starts fx_spire only while firing.\n'''
replacement = '''\tconst bool wasFiring = spawnArgs.GetBool( "_q4_lg_firing", "0" );\n\n\t// Raven's LG shake is part of the continuous-fire loop. Refresh the original\n\t// 500ms/scale-2 envelope every frame so it persists for exactly as long as\n\t// the trigger is held; the !firing path above cancels it immediately.\n\tif ( !gameLocal.isMultiplayer && owner == gameLocal.GetLocalPlayer() ) {\n\t\towner->playerView.SetShakeParms( MS2SEC( gameLocal.time + 500 ), 2.0f );\n\t}\n\n\tif ( !wasFiring ) {\n\t\t// Raven State_Fire starts fx_spire only while firing.\n'''
text = replace_once(text, anchor, replacement, "continuous screen-shake refresh")

anchor = '''\tif ( spireFx && spireFx[0] ) {\n\t\tconst jointHandle_t spireJoint = animator.GetJointHandle( "spire_1" );\n\t\tidVec3 spireOrigin; idMat3 spireAxis;\n\t\tif ( GetQ4PresentedJointTransform( spireJoint, spireOrigin, spireAxis ) ) {\n\t\t\tQ4BSE_UpdateEntityEffectTransform( this, spireFx, spireOrigin, spireAxis );\n\t\t}\n\t}\n\n\t// Raven keeps two versions'''
replacement = '''\tif ( spireFx && spireFx[0] ) {\n\t\tconst jointHandle_t spireJoint = animator.GetJointHandle( "spire_1" );\n\t\tidVec3 spireOrigin; idMat3 spireAxis;\n\t\tif ( GetQ4PresentedJointTransform( spireJoint, spireOrigin, spireAxis ) ) {\n\t\t\tQ4BSE_UpdateEntityEffectTransform( this, spireFx, spireOrigin, spireAxis );\n\t\t\tconst idVec3 spireColor = weaponDef->dict.GetVector( "q4_lg_spire_light_color", "0.14 0.32 0.85" );\n\t\t\tconst float spireRadius = weaponDef->dict.GetFloat( "q4_lg_spire_light_radius", "58" );\n\t\t\tUpdateQ4LightningGunLight( Q4_LG_SPIRE_LIGHT, spireOrigin + spireAxis[0] * 1.85f, spireRadius, spireColor );\n\t\t}\n\t}\n\n\t// Raven keeps two versions'''
text = replace_once(text, anchor, replacement, "firing-spire light")

anchor = '''\tidVec3 beamDir = tr.endpos - barrelOrigin;\n\tif ( beamDir.Normalize() < 0.001f ) beamDir = playerViewAxis[0];\n\tconst idMat3 beamAxis = beamDir.ToMat3();\n\n\tconst bool wasFiring'''
replacement = '''\tidVec3 beamDir = tr.endpos - barrelOrigin;\n\tif ( beamDir.Normalize() < 0.001f ) beamDir = playerViewAxis[0];\n\tconst idMat3 beamAxis = beamDir.ToMat3();\n\n\t// Cast blue light down the actual traced beam. Six no-shadow samples are\n\t// enough to read as continuous illumination while staying cheap in idTech 4.\n\tconst idVec3 beamDelta = tr.endpos - barrelOrigin;\n\tconst float beamLength = beamDelta.Length();\n\tconst idVec3 beamLightColor = weaponDef->dict.GetVector( "q4_lg_beam_light_color", "0.16 0.36 0.90" );\n\tfloat beamLightRadius = weaponDef->dict.GetFloat( "q4_lg_beam_light_radius", "105" );\n\tconst float coverageRadius = beamLength * ( 0.72f / (float)Q4_LG_BEAM_LIGHT_COUNT );\n\tif ( coverageRadius > beamLightRadius ) beamLightRadius = coverageRadius;\n\tif ( beamLightRadius > 220.0f ) beamLightRadius = 220.0f;\n\tfor ( int i = 0; i < Q4_LG_BEAM_LIGHT_COUNT; ++i ) {\n\t\tconst float t = ( (float)i + 0.5f ) / (float)Q4_LG_BEAM_LIGHT_COUNT;\n\t\tUpdateQ4LightningGunLight( Q4_LG_BEAM_LIGHT_FIRST + i, barrelOrigin + beamDelta * t, beamLightRadius, beamLightColor );\n\t}\n\n\tconst bool wasFiring'''
text = replace_once(text, anchor, replacement, "beam light chain")

weapon_cpp.write_text(text, encoding="utf-8")

print("V19Q Lightning Gun sustained shake + authored dynamic lighting overlay applied")
print(" - shake refreshes continuously while attack is held and cancels on release")
print(" - six no-shadow point lights illuminate the live beam path")
print(" - three charged tube lights illuminate the gun even when not firing")
print(" - firing-spire cluster gets a compact local blue light")
