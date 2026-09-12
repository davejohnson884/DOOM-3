#!/usr/bin/env python3
"""V18C: opt-in Quake 4 Machinegun flashlight + brass fidelity.

Runs after the validated V18B chain. This patch is deliberately narrow and is
only enabled by weapon/entity-def keys supplied by the Machinegun content PK4.

Adds:
  * q4UseFlashlightJoint: place Doom 3's shared projected weapon light at the
    declared Q4 joint_view_flashlight in the same presentation space as the gun.
  * q4ExactBrass: Raven-style ejection from the real Q4 eject joint with
    ejectOffset, proportional linear/angular random ranges, player velocity,
    and player-view-space casing axis.
  * q4ScaleVisual: Raven rvClientMoveable-style visual scale interpolation for
    idDebris casings (e.g. Machinegun scale .3 -> 1 over .2 seconds).

Weapons/entities without these opt-in keys retain stock cumulative behavior.
"""

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
WEAPON = ROOT / "neo" / "game" / "Weapon.cpp"
PROJECTILE = ROOT / "neo" / "game" / "Projectile.cpp"

for p in (WEAPON, PROJECTILE):
    if not p.exists():
        raise SystemExit(f"ERROR: V18C prerequisite missing: {p}")


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f"ERROR: V18C expected exactly one {label}, found {hits}")
    return text.replace(old, new, 1)


weapon = WEAPON.read_text(encoding="utf-8-sig")
projectile = PROJECTILE.read_text(encoding="utf-8-sig")

# -----------------------------------------------------------------------------
# Machinegun flashlight: Doom 3 normally locates its shared weapon light from
# flashJointView. The Q4 MG has a dedicated 'flashlight' joint, so the old port
# was visibly off-center. Keep stock behavior for every other weapon.
# -----------------------------------------------------------------------------
flash_anchor = '''\t// the flash has an explicit joint for locating it\n\tGetGlobalJointTransform( true, flashJointView, muzzleFlash.origin, muzzleFlash.axis );'''

flash_new = '''\t// Q4 Machinegun dedicated flashlight joint. Doom 3 normally uses the muzzle\n\t// flash joint for this shared light, which puts the persistent Q4 MG beam off\n\t// center. This path is opt-in and reconstructs the joint in the same\n\t// source-integrated Q4 presentation space as the rendered first-person gun.\n\tif ( weaponDef && weaponDef->dict.GetBool( "q4UseFlashlightJoint" ) ) {\n\t\tconst char *q4FlashlightJointName = weaponDef->dict.GetString( "joint_view_flashlight", "flashlight" );\n\t\tconst jointHandle_t q4FlashlightJoint = animator.GetJointHandle( q4FlashlightJointName );\n\t\tidVec3 q4LocalOrigin;\n\t\tidMat3 q4LocalAxis;\n\n\t\tif ( q4FlashlightJoint != INVALID_JOINT && animator.GetJointTransform( q4FlashlightJoint, gameLocal.time, q4LocalOrigin, q4LocalAxis ) ) {\n\t\t\tconst idVec3 q4FlashlightOffset = weaponDef->dict.GetVector( "flashlightViewOffset", "0 0 0" );\n\t\t\tq4LocalOrigin = q4FlashlightOffset * q4LocalAxis + q4LocalOrigin;\n\n\t\t\tidVec3 q4PresentedOrigin = viewWeaponOrigin;\n\t\t\tidMat3 q4PresentedAxis = viewWeaponAxis;\n\t\t\tidMat3 q4BaseAxis = viewWeaponAxis;\n\n\t\t\tconst char *q4ViewStyleName = weaponDef->dict.GetString( "def_viewStyle" );\n\t\t\tif ( q4ViewStyleName && q4ViewStyleName[0] ) {\n\t\t\t\tconst idDeclEntityDef *q4ViewStyleDef = gameLocal.FindEntityDef( q4ViewStyleName, false );\n\t\t\t\tif ( q4ViewStyleDef ) {\n\t\t\t\t\tconst idVec3 q4ViewOffset = q4ViewStyleDef->dict.GetVector( "viewoffset", "0 0 0" );\n\t\t\t\t\tconst idAngles q4ViewAngles = q4ViewStyleDef->dict.GetAngles( "viewangles", "0 0 0" );\n\t\t\t\t\tconst float q4Foreshorten = weaponDef->dict.GetFloat( "foreshorten", "1" );\n\n\t\t\t\t\tq4PresentedOrigin += q4ViewOffset * viewWeaponAxis;\n\t\t\t\t\tq4BaseAxis = q4ViewAngles.ToMat3() * viewWeaponAxis;\n\t\t\t\t\tq4PresentedAxis = q4BaseAxis;\n\t\t\t\t\tq4PresentedAxis[0] *= q4Foreshorten;\n\t\t\t\t}\n\t\t\t}\n\n\t\t\tmuzzleFlash.origin = q4LocalOrigin * q4PresentedAxis + q4PresentedOrigin;\n\t\t\tmuzzleFlash.axis = q4LocalAxis * q4BaseAxis;\n\t\t} else {\n\t\t\tGetGlobalJointTransform( true, flashJointView, muzzleFlash.origin, muzzleFlash.axis );\n\t\t}\n\t} else {\n\t\t// Stock Doom 3 / previously validated weapon behavior.\n\t\tGetGlobalJointTransform( true, flashJointView, muzzleFlash.origin, muzzleFlash.axis );\n\t}'''

weapon = replace_once(weapon, flash_anchor, flash_new, "UpdateFlashPosition flashlight locator")

# -----------------------------------------------------------------------------
# Exact Raven-style Machinegun casing launch, opt-in only. Q4 spawns at the
# actual eject joint, adds ejectOffset in the PLAYER view basis, then orients the
# casing to playerViewAxis before applying local brass velocity/spin. Crucially,
# Q4 random ranges are proportional to each authored component, not Doom 3's
# generic random direction.
# -----------------------------------------------------------------------------
brass_anchor = '''\tif ( gameLocal.isClient ) {\n\t\treturn;\n\t}\n\n\tidMat3 axis;'''

brass_new = '''\tif ( gameLocal.isClient ) {\n\t\treturn;\n\t}\n\n\tif ( weaponDef && weaponDef->dict.GetBool( "q4ExactBrass" ) ) {\n\t\tidVec3 q4LocalOrigin;\n\t\tidMat3 q4LocalAxis;\n\t\tif ( !animator.GetJointTransform( ejectJointView, gameLocal.time, q4LocalOrigin, q4LocalAxis ) ) {\n\t\t\treturn;\n\t\t}\n\n\t\t// Reconstruct the rendered Q4 joint position. Orientation of the spawned\n\t\t// casing itself intentionally does NOT use the joint axis; Raven sets it to\n\t\t// playerViewAxis below.\n\t\tidVec3 q4PresentedOrigin = viewWeaponOrigin;\n\t\tidMat3 q4PresentedAxis = viewWeaponAxis;\n\t\tconst char *q4ViewStyleName = weaponDef->dict.GetString( "def_viewStyle" );\n\t\tif ( q4ViewStyleName && q4ViewStyleName[0] ) {\n\t\t\tconst idDeclEntityDef *q4ViewStyleDef = gameLocal.FindEntityDef( q4ViewStyleName, false );\n\t\t\tif ( q4ViewStyleDef ) {\n\t\t\t\tconst idVec3 q4ViewOffset = q4ViewStyleDef->dict.GetVector( "viewoffset", "0 0 0" );\n\t\t\t\tconst idAngles q4ViewAngles = q4ViewStyleDef->dict.GetAngles( "viewangles", "0 0 0" );\n\t\t\t\tconst float q4Foreshorten = weaponDef->dict.GetFloat( "foreshorten", "1" );\n\t\t\t\tq4PresentedOrigin += q4ViewOffset * viewWeaponAxis;\n\t\t\t\tq4PresentedAxis = q4ViewAngles.ToMat3() * viewWeaponAxis;\n\t\t\t\tq4PresentedAxis[0] *= q4Foreshorten;\n\t\t\t}\n\t\t}\n\n\t\tidVec3 q4SpawnOrigin = q4LocalOrigin * q4PresentedAxis + q4PresentedOrigin;\n\t\tconst idVec3 q4EjectOffset = weaponDef->dict.GetVector( "ejectOffset", "0 0 0" );\n\t\tq4SpawnOrigin += q4EjectOffset * playerViewAxis;\n\n\t\tidEntity *q4Ent = NULL;\n\t\tgameLocal.SpawnEntityDef( brassDict, &q4Ent, false );\n\t\tif ( !q4Ent || !q4Ent->IsType( idDebris::Type ) ) {\n\t\t\tgameLocal.Error( "'%s' is not an idDebris", weaponDef->dict.GetString( "def_ejectBrass" ) );\n\t\t\treturn;\n\t\t}\n\n\t\tidDebris *q4Debris = static_cast<idDebris *>( q4Ent );\n\t\tq4Debris->Create( owner, q4SpawnOrigin, playerViewAxis );\n\t\tq4Debris->Launch();\n\n\t\tidVec3 q4LinearVelocity = brassDict.GetVector( "linear_velocity", "0 0 0" );\n\t\tconst idVec3 q4LinearRange = brassDict.GetVector( "linear_velocity_range", "0 0 0" );\n\t\tq4LinearVelocity.x += q4LinearVelocity.x * q4LinearRange.x * gameLocal.random.CRandomFloat();\n\t\tq4LinearVelocity.y += q4LinearVelocity.y * q4LinearRange.y * gameLocal.random.CRandomFloat();\n\t\tq4LinearVelocity.z += q4LinearVelocity.z * q4LinearRange.z * gameLocal.random.CRandomFloat();\n\n\t\tidAngles q4AngularVelocity = brassDict.GetAngles( "angular_velocity", "0 0 0" );\n\t\tconst idVec3 q4AngularRange = brassDict.GetVector( "angular_velocity_range", "0 0 0" );\n\t\tq4AngularVelocity.pitch += q4AngularVelocity.pitch * q4AngularRange.x * gameLocal.random.CRandomFloat();\n\t\tq4AngularVelocity.yaw += q4AngularVelocity.yaw * q4AngularRange.y * gameLocal.random.CRandomFloat();\n\t\tq4AngularVelocity.roll += q4AngularVelocity.roll * q4AngularRange.z * gameLocal.random.CRandomFloat();\n\n\t\tidVec3 q4OwnerVelocity = vec3_origin;\n\t\tif ( owner && owner->GetPhysics() ) {\n\t\t\tq4OwnerVelocity = owner->GetPhysics()->GetLinearVelocity();\n\t\t}\n\n\t\tq4Debris->GetPhysics()->SetLinearVelocity( q4OwnerVelocity + q4LinearVelocity * q4Debris->GetPhysics()->GetAxis() );\n\t\tq4Debris->GetPhysics()->SetAngularVelocity( q4AngularVelocity.ToAngularVelocity() * q4Debris->GetPhysics()->GetAxis() );\n\t\treturn;\n\t}\n\n\tidMat3 axis;'''

weapon = replace_once(weapon, brass_anchor, brass_new, "Event_EjectBrass exact Q4 branch")

# -----------------------------------------------------------------------------
# Q4 rvClientMoveable visually interpolates casing scale from the entity-def
# 'scale' value back to 1.0 over scale_reset_duration (default .2 s). Doom 3's
# idDebris has no equivalent. Apply it after normal Present() so physics stays
# unscaled and only the rendered casing grows exactly like Raven's path.
# -----------------------------------------------------------------------------
thinking_anchor = '''\t// run physics\n\tRunPhysics();\n\tPresent();\n\n\tif ( smokeFly && smokeFlyTime ) {'''

thinking_new = '''\t// run physics\n\tRunPhysics();\n\tPresent();\n\n\tif ( spawnArgs.GetBool( "q4ScaleVisual" ) && modelDefHandle >= 0 ) {\n\t\tconst float q4StartScale = Max( VECTOR_EPSILON, spawnArgs.GetFloat( "scale", "1" ) );\n\t\tconst float q4ScaleDuration = spawnArgs.GetFloat( "scale_reset_duration", "0.2" );\n\t\tconst float q4Elapsed = MS2SEC( gameLocal.time ) + renderEntity.shaderParms[ SHADERPARM_TIMEOFFSET ];\n\t\tconst float q4Frac = ( q4ScaleDuration > 0.0f ) ? idMath::ClampFloat( 0.0f, 1.0f, q4Elapsed / q4ScaleDuration ) : 1.0f;\n\t\tconst float q4VisualScale = q4StartScale + ( 1.0f - q4StartScale ) * q4Frac;\n\t\trenderEntity.axis *= q4VisualScale;\n\t\tgameRenderWorld->UpdateEntityDef( modelDefHandle, &renderEntity );\n\t}\n\n\tif ( smokeFly && smokeFlyTime ) {'''

projectile = replace_once(projectile, thinking_anchor, thinking_new, "idDebris Q4 visual scale")

# Hard verification. These gates also protect Nailgun/HyperBlaster/GL by making
# sure every new path remains explicitly opt-in.
for needle in (
    'GetBool( "q4UseFlashlightJoint" )',
    'GetString( "joint_view_flashlight", "flashlight" )',
    'GetBool( "q4ExactBrass" )',
    'GetVector( "ejectOffset", "0 0 0" )',
    'GetVector( "linear_velocity_range", "0 0 0" )',
    'q4OwnerVelocity + q4LinearVelocity * q4Debris->GetPhysics()->GetAxis()',
):
    if needle not in weapon:
        raise SystemExit(f"ERROR: V18C Weapon.cpp verification missing: {needle}")

for needle in (
    'GetBool( "q4ScaleVisual" )',
    'GetFloat( "scale_reset_duration", "0.2" )',
    'renderEntity.axis *= q4VisualScale',
):
    if needle not in projectile:
        raise SystemExit(f"ERROR: V18C Projectile.cpp verification missing: {needle}")

WEAPON.write_text(weapon, encoding="utf-8")
PROJECTILE.write_text(projectile, encoding="utf-8")

print("Q4BSE V18C MACHINEGUN EXACT PASS.")
print("  - opt-in dedicated Q4 flashlight joint presentation")
print("  - opt-in Raven Machinegun eject joint/ejectOffset brass path")
print("  - proportional Q4 linear/angular velocity randomization")
print("  - player movement velocity inherited by casing")
print("  - opt-in Raven .3 -> 1 casing visual scale interpolation")
print("  - all non-opt-in weapons/entities untouched")
