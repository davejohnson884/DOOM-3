#!/usr/bin/env python3
'''V18R: Quake 4 Rocket Launcher guidance polish.

Runs AFTER V18P + V18Q.  This pass changes only the guided/designator layer:
  * preserve the authored Quake 4 normal rocket speed, but reproduce the Q4
    guided slowdown (default 25%) while BUTTON_5 is held;
  * accelerate smoothly back to authored speed after release (default .5 sec);
  * rotate the surface marker 180 degrees in-plane (live test showed it upside down);
  * add a soft red point light at the painted target so the glyph visibly lights
    nearby geometry without casting expensive shadows.

Beam/marker material halo artwork is packaged separately in the PK4 and remains
presentation-only.  All accepted Rocket BSE/trail/impact/shockwave/damage behavior
is untouched.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
WEAPON_H = ROOT / 'neo' / 'game' / 'Weapon.h'
WEAPON_CPP = ROOT / 'neo' / 'game' / 'Weapon.cpp'
PROJECTILE_CPP = ROOT / 'neo' / 'game' / 'Projectile.cpp'

for p in (WEAPON_H, WEAPON_CPP, PROJECTILE_CPP):
    if not p.exists():
        raise SystemExit(f'ERROR: V18R prerequisite missing: {p}')

weapon_h = WEAPON_H.read_text(encoding='utf-8-sig')
weapon = WEAPON_CPP.read_text(encoding='utf-8-sig')
projectile = PROJECTILE_CPP.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V18R expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Target-point dynamic light state.
# ---------------------------------------------------------------------------
weapon_h = replace_once(
    weapon_h,
    '''\trenderEntity_t\t\t\t\tq4GuideMarker;\n\tint\t\t\t\t\t\tq4GuideMarkerHandle;''',
    '''\trenderEntity_t\t\t\t\tq4GuideMarker;\n\tint\t\t\t\t\t\tq4GuideMarkerHandle;\n\trenderLight_t\t\t\t\tq4GuideLight;\n\tint\t\t\t\t\t\tq4GuideLightHandle;''',
    'Weapon.h guide light fields')

weapon = replace_once(
    weapon,
    '''\tmemset( &q4GuideBeam, 0, sizeof( q4GuideBeam ) );\n\tmemset( &q4GuideMarker, 0, sizeof( q4GuideMarker ) );''',
    '''\tmemset( &q4GuideBeam, 0, sizeof( q4GuideBeam ) );\n\tmemset( &q4GuideMarker, 0, sizeof( q4GuideMarker ) );\n\tmemset( &q4GuideLight, 0, sizeof( q4GuideLight ) );''',
    'weapon guide light memset')

weapon = replace_once(
    weapon,
    '''\tq4GuideBeamHandle\t\t= -1;\n\tq4GuideMarkerHandle\t= -1;\n\tmodelDefHandle\t\t\t= -1;''',
    '''\tq4GuideBeamHandle\t\t= -1;\n\tq4GuideMarkerHandle\t= -1;\n\tq4GuideLightHandle\t\t= -1;\n\tmodelDefHandle\t\t\t= -1;''',
    'weapon guide light handle init')

weapon = replace_once(
    weapon,
    '''\t\tif ( q4GuideMarkerHandle != -1 ) {\n\t\t\tgameRenderWorld->FreeEntityDef( q4GuideMarkerHandle );\n\t\t\tq4GuideMarkerHandle = -1;\n\t\t}\n\t} else {\n\t\tq4GuideBeamHandle = -1;\n\t\tq4GuideMarkerHandle = -1;\n\t}\n}''',
    '''\t\tif ( q4GuideMarkerHandle != -1 ) {\n\t\t\tgameRenderWorld->FreeEntityDef( q4GuideMarkerHandle );\n\t\t\tq4GuideMarkerHandle = -1;\n\t\t}\n\t\tif ( q4GuideLightHandle != -1 ) {\n\t\t\tgameRenderWorld->FreeLightDef( q4GuideLightHandle );\n\t\t\tq4GuideLightHandle = -1;\n\t\t}\n\t} else {\n\t\tq4GuideBeamHandle = -1;\n\t\tq4GuideMarkerHandle = -1;\n\t\tq4GuideLightHandle = -1;\n\t}\n}''',
    'FreeQ4GuideLaser light cleanup')

# If the trace no longer touches geometry, kill both marker and its illumination.
weapon = replace_once(
    weapon,
    '''\tif ( tr.fraction >= 1.0f ) {\n\t\tif ( q4GuideMarkerHandle != -1 ) {\n\t\t\tgameRenderWorld->FreeEntityDef( q4GuideMarkerHandle );\n\t\t\tq4GuideMarkerHandle = -1;\n\t\t}\n\t\treturn;\n\t}''',
    '''\tif ( tr.fraction >= 1.0f ) {\n\t\tif ( q4GuideMarkerHandle != -1 ) {\n\t\t\tgameRenderWorld->FreeEntityDef( q4GuideMarkerHandle );\n\t\t\tq4GuideMarkerHandle = -1;\n\t\t}\n\t\tif ( q4GuideLightHandle != -1 ) {\n\t\t\tgameRenderWorld->FreeLightDef( q4GuideLightHandle );\n\t\t\tq4GuideLightHandle = -1;\n\t\t}\n\t\treturn;\n\t}''',
    'guide no-hit light cleanup')

# Rotate the live projected marker 180 degrees around the surface normal.  This
# is an in-plane rotation, not a mirror, so the glyph keeps its handedness.
weapon = replace_once(
    weapon,
    '''\t\tmarkerAxis[1] = markerAxis[2].Cross( markerAxis[0] );\n\t\tmarkerAxis[1].Normalize();\n\t}\n\n\tif ( q4GuideMarkerHandle == -1 ) {''',
    '''\t\tmarkerAxis[1] = markerAxis[2].Cross( markerAxis[0] );\n\t\tmarkerAxis[1].Normalize();\n\t}\n\n\t// V18R: live test showed the authored glyph was upside down. Rotating both\n\t// tangent axes preserves the surface normal while turning the plane 180 deg.\n\tmarkerAxis[1] = -markerAxis[1];\n\tmarkerAxis[2] = -markerAxis[2];\n\n\tif ( q4GuideMarkerHandle == -1 ) {''',
    'guide marker 180 degree orientation fix')

# Add a deliberately soft, shadowless point light at the painted target.  A NULL
# shader is intentional: idTech 4 resolves point lights to lights/defaultPointLight.
weapon = replace_once(
    weapon,
    '''\tq4GuideMarker.origin = tr.endpos + normal * 0.35f;\n\tq4GuideMarker.axis = markerAxis;\n\tgameRenderWorld->UpdateEntityDef( q4GuideMarkerHandle, &q4GuideMarker );\n}''',
    '''\tq4GuideMarker.origin = tr.endpos + normal * 0.35f;\n\tq4GuideMarker.axis = markerAxis;\n\tgameRenderWorld->UpdateEntityDef( q4GuideMarkerHandle, &q4GuideMarker );\n\n\tconst float guideLightRadius = weaponDef->dict.GetFloat( "q4_guide_light_radius", "56" );\n\tconst float guideLightIntensity = weaponDef->dict.GetFloat( "q4_guide_light_intensity", "0.42" );\n\tif ( q4GuideLightHandle == -1 ) {\n\t\tmemset( &q4GuideLight, 0, sizeof( q4GuideLight ) );\n\t\tq4GuideLight.pointLight = true;\n\t\tq4GuideLight.noShadows = true;\n\t\tq4GuideLight.shader = NULL;\n\t\tq4GuideLight.shaderParms[ SHADERPARM_TIMESCALE ] = 1.0f;\n\t\tq4GuideLightHandle = gameRenderWorld->AddLightDef( &q4GuideLight );\n\t}\n\tq4GuideLight.origin = tr.endpos + normal * 3.0f;\n\tq4GuideLight.axis = mat3_identity;\n\tq4GuideLight.lightRadius.Set( guideLightRadius, guideLightRadius, guideLightRadius );\n\tq4GuideLight.shaderParms[ SHADERPARM_RED ] = guideLightIntensity;\n\tq4GuideLight.shaderParms[ SHADERPARM_GREEN ] = guideLightIntensity * 0.015f;\n\tq4GuideLight.shaderParms[ SHADERPARM_BLUE ] = 0.0f;\n\tgameRenderWorld->UpdateLightDef( q4GuideLightHandle, &q4GuideLight );\n}''',
    'guide marker soft point light')


# ---------------------------------------------------------------------------
# Quake 4 guided-speed parity.
# Stock Q4 projectile speed is 900; guidance applies lockSlowdown .25 and the
# released rocket accelerates back over lockAccelTime .5.  Keep the authored
# velocity spawnarg as the source of truth so this remains data-driven.
# ---------------------------------------------------------------------------
old_guide = '''\tif ( state == LAUNCHED && spawnArgs.GetBool( "q4_manual_guide" ) &&\n\t\t owner.GetEntity() && owner.GetEntity()->IsType( idPlayer::Type ) ) {\n\t\tidPlayer* guidePlayer = static_cast<idPlayer*>( owner.GetEntity() );\n\t\tif ( guidePlayer->usercmd.buttons & BUTTON_5 ) {\n\t\t\tconst float guideRange = spawnArgs.GetFloat( "q4_guide_range", "10000" );\n\t\t\tconst float turnRate = spawnArgs.GetFloat( "q4_guide_turn_rate", "260" );\n\t\t\ttrace_t guideTrace;\n\t\t\tconst idVec3 guideStart = guidePlayer->firstPersonViewOrigin;\n\t\t\tconst idVec3 guideEnd = guideStart + guidePlayer->firstPersonViewAxis[0] * guideRange;\n\t\t\tgameLocal.clip.TracePoint( guideTrace, guideStart, guideEnd, MASK_SHOT_RENDERMODEL, guidePlayer );\n\n\t\t\tidVec3 velocity = physicsObj.GetLinearVelocity();\n\t\t\tconst float projectileSpeed = velocity.Normalize();\n\t\t\tidVec3 desired = guideTrace.endpos - physicsObj.GetOrigin();\n\t\t\tif ( projectileSpeed > 1.0f && desired.Normalize() > 0.001f ) {\n\t\t\t\tconst float dot = idMath::ClampFloat( -1.0f, 1.0f, velocity * desired );\n\t\t\t\tconst float angleDeg = RAD2DEG( idMath::ACos( dot ) );\n\t\t\t\tconst float maxTurnDeg = turnRate * MS2SEC( gameLocal.GetMSec() );\n\t\t\t\tconst float frac = ( angleDeg > maxTurnDeg && angleDeg > 0.001f ) ? ( maxTurnDeg / angleDeg ) : 1.0f;\n\t\t\t\tidVec3 newDir = velocity * ( 1.0f - frac ) + desired * frac;\n\t\t\t\tif ( newDir.Normalize() > 0.001f ) {\n\t\t\t\t\tphysicsObj.SetLinearVelocity( newDir * projectileSpeed );\n\t\t\t\t\tidMat3 q4GuideAxis = newDir.ToMat3();\n\t\t\t\t\tif ( !spawnArgs.GetBool( "q4_projectile_forward_x" ) ) {\n\t\t\t\t\t\tidVec3 tmp = q4GuideAxis[2];\n\t\t\t\t\t\tq4GuideAxis[2] = q4GuideAxis[0];\n\t\t\t\t\t\tq4GuideAxis[0] = -tmp;\n\t\t\t\t\t}\n\t\t\t\t\tphysicsObj.SetAxis( q4GuideAxis );\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}'''

new_guide = '''\tif ( state == LAUNCHED && spawnArgs.GetBool( "q4_manual_guide" ) &&\n\t\t owner.GetEntity() && owner.GetEntity()->IsType( idPlayer::Type ) ) {\n\t\tidPlayer* guidePlayer = static_cast<idPlayer*>( owner.GetEntity() );\n\t\tidVec3 velocity = physicsObj.GetLinearVelocity();\n\t\tfloat projectileSpeed = velocity.Normalize();\n\t\tconst float baseSpeed = spawnArgs.GetVector( "velocity", "900 0 0" ).Length();\n\t\tconst float slowdown = idMath::ClampFloat( 0.0f, 0.95f, spawnArgs.GetFloat( "q4_guide_slowdown", "0.25" ) );\n\t\tconst float guidedSpeed = baseSpeed * ( 1.0f - slowdown );\n\t\tconst float accelTime = idMath::Fmax( 0.001f, spawnArgs.GetFloat( "q4_guide_accel_time", "0.5" ) );\n\t\tconst bool guiding = ( guidePlayer->usercmd.buttons & BUTTON_5 ) != 0;\n\n\t\tif ( guiding ) {\n\t\t\t// Raven's lockSlowdown makes the guided rocket deliberately easier to\n\t\t\t// steer.  Do not alter the authored normal-flight velocity spawnarg.\n\t\t\tif ( projectileSpeed > guidedSpeed ) {\n\t\t\t\tprojectileSpeed = guidedSpeed;\n\t\t\t}\n\n\t\t\tconst float guideRange = spawnArgs.GetFloat( "q4_guide_range", "10000" );\n\t\t\tconst float turnRate = spawnArgs.GetFloat( "q4_guide_turn_rate", "260" );\n\t\t\ttrace_t guideTrace;\n\t\t\tconst idVec3 guideStart = guidePlayer->firstPersonViewOrigin;\n\t\t\tconst idVec3 guideEnd = guideStart + guidePlayer->firstPersonViewAxis[0] * guideRange;\n\t\t\tgameLocal.clip.TracePoint( guideTrace, guideStart, guideEnd, MASK_SHOT_RENDERMODEL, guidePlayer );\n\n\t\t\tidVec3 desired = guideTrace.endpos - physicsObj.GetOrigin();\n\t\t\tif ( projectileSpeed > 1.0f && desired.Normalize() > 0.001f ) {\n\t\t\t\tconst float dot = idMath::ClampFloat( -1.0f, 1.0f, velocity * desired );\n\t\t\t\tconst float angleDeg = RAD2DEG( idMath::ACos( dot ) );\n\t\t\t\tconst float maxTurnDeg = turnRate * MS2SEC( gameLocal.GetMSec() );\n\t\t\t\tconst float frac = ( angleDeg > maxTurnDeg && angleDeg > 0.001f ) ? ( maxTurnDeg / angleDeg ) : 1.0f;\n\t\t\t\tidVec3 newDir = velocity * ( 1.0f - frac ) + desired * frac;\n\t\t\t\tif ( newDir.Normalize() > 0.001f ) {\n\t\t\t\t\tphysicsObj.SetLinearVelocity( newDir * projectileSpeed );\n\t\t\t\t\tidMat3 q4GuideAxis = newDir.ToMat3();\n\t\t\t\t\tif ( !spawnArgs.GetBool( "q4_projectile_forward_x" ) ) {\n\t\t\t\t\t\tidVec3 tmp = q4GuideAxis[2];\n\t\t\t\t\t\tq4GuideAxis[2] = q4GuideAxis[0];\n\t\t\t\t\t\tq4GuideAxis[0] = -tmp;\n\t\t\t\t\t}\n\t\t\t\t\tphysicsObj.SetAxis( q4GuideAxis );\n\t\t\t\t}\n\t\t\t}\n\t\t} else if ( projectileSpeed > 1.0f && baseSpeed > 1.0f && projectileSpeed < baseSpeed ) {\n\t\t\t// Q4 lockAccelTime: after releasing the designator, smoothly restore\n\t\t\t// the normal authored rocket speed instead of snapping immediately.\n\t\t\tconst float speedPerSecond = ( baseSpeed - guidedSpeed ) / accelTime;\n\t\t\tprojectileSpeed = idMath::Fmin( baseSpeed, projectileSpeed + speedPerSecond * MS2SEC( gameLocal.GetMSec() ) );\n\t\t\tphysicsObj.SetLinearVelocity( velocity * projectileSpeed );\n\t\t}\n\t}'''

projectile = replace_once(projectile, old_guide, new_guide, 'Q4 guided slowdown/accel parity block')

# Keep the V18P comment honest after adding real Q4 speed behavior.
projectile = projectile.replace(
    '// Q4 V18P: manual crosshair guidance. The rocket keeps its authored speed;\n\t// only its direction is progressively bent toward the designator endpoint.',
    '// Q4 V18P/V18R: manual crosshair guidance with Raven-style guided slowdown;\n\t// normal flight still uses the authored projectile speed unchanged.',
    1)

# Verification.
combined = weapon_h + weapon + projectile
for required in (
    'q4GuideLightHandle',
    'FreeLightDef',
    'q4_guide_light_radius',
    'markerAxis[1] = -markerAxis[1]',
    'q4_guide_slowdown',
    'q4_guide_accel_time',
    'BUTTON_5',
):
    if required not in combined:
        raise SystemExit(f'ERROR: V18R verification missing: {required}')

WEAPON_H.write_text(weapon_h, encoding='utf-8')
WEAPON_CPP.write_text(weapon, encoding='utf-8')
PROJECTILE_CPP.write_text(projectile, encoding='utf-8')

print('Q4BSE V18R ROCKET GUIDANCE POLISH PASS.')
print('  - normal rocket velocity remains authored Q4 speed')
print('  - guidance applies Q4-style 25% slowdown and .5s release acceleration')
print('  - target glyph rotated 180 degrees in-plane')
print('  - target point gains a soft shadowless red dynamic light')
print('  - accepted Rocket BSE/trail/impact/shockwave/damage behavior untouched')
