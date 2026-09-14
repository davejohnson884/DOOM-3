#!/usr/bin/env python3
"""V18E: exact animated-joint muzzle follow + generic lowAmmo GUI color.

Runs after V18D.  This is deliberately generic and opt-in/content-driven:
  * one-shot BSE weapon muzzle FX already started by V16 can have their local
    transform refreshed every frame from the CURRENT animated flash joint;
  * joint_view_barrel can select the native Doom 3 muzzle-smoke source joint;
  * V18B GUI-light low-ammo state uses idWeapon::lowAmmo and reproduces the
    proven V58/MG binary transform exactly: (r,g,b) -> (g,2*r,b).

Weapons without fx_muzzleflash / joint_view_barrel / glightAmmoTrack keep their
existing behavior.
"""
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"
HEADER = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.h"
WEAPON = ROOT / "neo" / "game" / "Weapon.cpp"

for p in (IMPACT, HEADER, WEAPON):
    if not p.exists():
        raise SystemExit(f"ERROR: V18E prerequisite missing: {p}")


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f"ERROR: V18E expected exactly one {label}, found {hits}")
    return text.replace(old, new, 1)

impact = IMPACT.read_text(encoding="utf-8-sig")
header = HEADER.read_text(encoding="utf-8-sig")
weapon = WEAPON.read_text(encoding="utf-8-sig")

# -----------------------------------------------------------------------------
# Runtime API: refresh an already-live non-persistent local-transform effect.
# V16 attaches muzzle FX to the weapon entity, which follows player/bob motion,
# but a pump-action shotgun also moves the flash JOINT inside that entity.  This
# API updates the stored entity-local transform each frame without respawning FX.
# -----------------------------------------------------------------------------
header = replace_once(
    header,
    '''bool Q4BSE_AttachEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis);\nvoid Q4BSE_StopEntityEffects(idEntity* entity);''',
    '''bool Q4BSE_AttachEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis);\nbool Q4BSE_UpdateEntityEffectTransform(idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis);\nvoid Q4BSE_StopEntityEffects(idEntity* entity);''',
    "BSE animated-joint update API declaration")

api_anchor = '''bool Q4BSE_AttachEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis) {\n    if (!g_m3Initialized || !gameRenderWorld || !fxPath || !fxPath[0] || !entity || !entity->GetPhysics()) return false;\n    M3CachedEffect* cached = GetOrLoadEffect(fxPath);\n    if (!cached) return false;\n\n    // The effect is authored in the already-presented weapon-joint transform.\n    // Store that transform relative to the weapon's authoritative physics basis\n    // so strafing, turning, bob and recoil move the live BSE instance with it.\n    // Unlike projectile fly FX this is still a one-shot: it dies when its Raven\n    // emitters/particles are finished.\n    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), worldOrigin, worldAxis, entity, false, true);\n}\n\nvoid Q4BSE_StopEntityEffects'''

api_new = '''bool Q4BSE_AttachEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis) {\n    if (!g_m3Initialized || !gameRenderWorld || !fxPath || !fxPath[0] || !entity || !entity->GetPhysics()) return false;\n    M3CachedEffect* cached = GetOrLoadEffect(fxPath);\n    if (!cached) return false;\n\n    // The effect is authored in the already-presented weapon-joint transform.\n    // Store that transform relative to the weapon's authoritative physics basis\n    // so strafing, turning, bob and recoil move the live BSE instance with it.\n    // Unlike projectile fly FX this is still a one-shot: it dies when its Raven\n    // emitters/particles are finished.\n    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), worldOrigin, worldAxis, entity, false, true);\n}\n\nbool Q4BSE_UpdateEntityEffectTransform(idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis) {\n    if (!entity || !entity->GetPhysics()) return false;\n\n    const idVec3 entityOrigin = entity->GetPhysics()->GetOrigin();\n    const idMat3 entityAxis = entity->GetPhysics()->GetAxis();\n    const idMat3 entityAxisTranspose = entityAxis.Transpose();\n    bool updated = false;\n\n    for (size_t i = 0; i < g_m3Impacts.size(); ++i) {\n        M3ImpactInstance* instance = g_m3Impacts[i];\n        if (!instance || !instance->active || !instance->attached ||\n            instance->attachedPersistent || !instance->attachedLocalTransform ||\n            instance->attachedEntity.GetEntity() != entity) {\n            continue;\n        }\n\n        instance->attachedLocalOrigin = (worldOrigin - entityOrigin) * entityAxisTranspose;\n        instance->attachedLocalAxis = worldAxis * entityAxisTranspose;\n        instance->origin = worldOrigin;\n        instance->axis = worldAxis;\n        updated = true;\n    }\n\n    return updated;\n}\n\nvoid Q4BSE_StopEntityEffects'''
impact = replace_once(impact, api_anchor, api_new, "BSE animated-joint update API implementation")

# -----------------------------------------------------------------------------
# Native muzzle smoke: allow content to select an existing Q4 joint (shotgun
# uses its original animated flash joint) instead of requiring a synthetic
# Doom-3-named 'barrel' helper bone.
# -----------------------------------------------------------------------------
weapon = replace_once(
    weapon,
    '''\tbarrelJointView = animator.GetJointHandle( "barrel" );\n\tflashJointView = animator.GetJointHandle( "flash" );''',
    '''\tconst char *q4BarrelJointName = weaponDef->dict.GetString( "joint_view_barrel" );\n\tbarrelJointView = animator.GetJointHandle( ( q4BarrelJointName && q4BarrelJointName[0] ) ? q4BarrelJointName : "barrel" );\n\tflashJointView = animator.GetJointHandle( "flash" );''',
    "Q4 barrel-joint selection")

# -----------------------------------------------------------------------------
# Exact low-ammo color transform from the proven MG V4/V58 machine code.
# Existing V18B logic already loads glightColor and handles exact-zero red.
# For 0 < ammo <= lowAmmo, transform (r,g,b) -> (g,2*r,b).
# -----------------------------------------------------------------------------
low_old = '''\t\t\t\tidVec3 q4GuiColor = weaponDef->dict.GetVector( "glightColor", "1 1 1" );\n\t\t\t\tif ( q4AmmoInClip <= 0 ) {\n\t\t\t\t\tq4GuiColor = weaponDef->dict.GetVector( "glightEmptyColor", "1 0 0" );\n\t\t\t\t}\n\t\t\t\tguiLight.shaderParms[ SHADERPARM_RED ] = q4GuiColor.x;'''
low_new = '''\t\t\t\tidVec3 q4GuiColor = weaponDef->dict.GetVector( "glightColor", "1 1 1" );\n\t\t\t\tif ( q4AmmoInClip <= 0 ) {\n\t\t\t\t\tq4GuiColor = weaponDef->dict.GetVector( "glightEmptyColor", "1 0 0" );\n\t\t\t\t} else if ( q4AmmoInClip <= lowAmmo ) {\n\t\t\t\t\t// Exact proven V58/Machinegun transform: red <- green,\n\t\t\t\t\t// green <- 2*old red, blue unchanged.\n\t\t\t\t\tconst float q4BaseRed = q4GuiColor.x;\n\t\t\t\t\tq4GuiColor.x = q4GuiColor.y;\n\t\t\t\t\tq4GuiColor.y = q4BaseRed * 2.0f;\n\t\t\t\t}\n\t\t\t\tguiLight.shaderParms[ SHADERPARM_RED ] = q4GuiColor.x;'''
weapon = replace_once(weapon, low_old, low_new, "generic lowAmmo GUI-light color")

# -----------------------------------------------------------------------------
# Every PresentWeapon frame, recompute the CURRENT animated flash-joint transform
# in the same Q4 viewStyle/foreshortened presentation space used at spawn, then
# refresh any live one-shot muzzle BSE instance.  This is the missing shotgun
# behavior: the flash follows bone animation, not just the weapon entity basis.
# -----------------------------------------------------------------------------
present_anchor = '''\t// update the gui light\n\tif ( guiLight.lightRadius[0] && guiLightJointView != INVALID_JOINT ) {'''

present_new = r'''	// Q4 V18E: keep a live one-shot muzzle BSE effect locked to the CURRENT
	// animated flash joint. V16 already follows entity bob/turn/recoil; this adds
	// the joint-animation component needed by weapons such as the pump shotgun.
	if ( weaponDef && flashJointView != INVALID_JOINT ) {
		const char *q4LiveMuzzleFx = weaponDef->dict.GetString( "fx_muzzleflash" );
		if ( q4LiveMuzzleFx && q4LiveMuzzleFx[0] ) {
			idVec3 q4LiveLocalOrigin;
			idMat3 q4LiveLocalAxis;
			if ( animator.GetJointTransform( flashJointView, gameLocal.time, q4LiveLocalOrigin, q4LiveLocalAxis ) ) {
				idVec3 q4LivePresentedOrigin = viewWeaponOrigin;
				idMat3 q4LivePresentedAxis = viewWeaponAxis;
				idMat3 q4LiveFxBaseAxis = viewWeaponAxis;

				const char *q4ViewStyleName = weaponDef->dict.GetString( "def_viewStyle" );
				if ( q4ViewStyleName && q4ViewStyleName[0] ) {
					const idDeclEntityDef *q4ViewStyleDef = gameLocal.FindEntityDef( q4ViewStyleName, false );
					if ( q4ViewStyleDef ) {
						const idVec3 q4ViewOffset = q4ViewStyleDef->dict.GetVector( "viewoffset", "0 0 0" );
						const idAngles q4ViewAngles = q4ViewStyleDef->dict.GetAngles( "viewangles", "0 0 0" );
						const float q4Foreshorten = weaponDef->dict.GetFloat( "foreshorten", "1" );

						q4LivePresentedOrigin += q4ViewOffset * viewWeaponAxis;
						q4LiveFxBaseAxis = q4ViewAngles.ToMat3() * viewWeaponAxis;
						q4LivePresentedAxis = q4LiveFxBaseAxis;
						q4LivePresentedAxis[0] *= q4Foreshorten;
					}
				}

				const idVec3 q4LiveFxOrigin = q4LiveLocalOrigin * q4LivePresentedAxis + q4LivePresentedOrigin;
				const idMat3 q4LiveFxAxis = q4LiveLocalAxis * q4LiveFxBaseAxis;
				Q4BSE_UpdateEntityEffectTransform( this, q4LiveFxOrigin, q4LiveFxAxis );
			}
		}
	}

	// update the gui light
	if ( guiLight.lightRadius[0] && guiLightJointView != INVALID_JOINT ) {'''
weapon = replace_once(weapon, present_anchor, present_new, "PresentWeapon animated muzzle-joint refresh")

for needle in (
    "Q4BSE_UpdateEntityEffectTransform",
    'GetString( "joint_view_barrel" )',
    'q4AmmoInClip <= lowAmmo',
    'q4GuiColor.x = q4GuiColor.y',
    'q4GuiColor.y = q4BaseRed * 2.0f',
    'Q4BSE_UpdateEntityEffectTransform( this, q4LiveFxOrigin, q4LiveFxAxis )',
    'q4LivePresentedAxis[0] *= q4Foreshorten',
):
    if needle not in impact and needle not in header and needle not in weapon:
        raise SystemExit(f"ERROR: V18E verification missing: {needle}")

# Preserve all cumulative gates that the finished ports already rely on.
for preserved in (
    'GetBool( "q4ExactBrass" )',
    'GetBool( "q4UseFlashlightJoint" )',
    'GetBool( "glightAmmoTrack" )',
    'GetBool( "q4SecondGuiLight" )',
    'Q4BSE_AttachEffectToEntityTransform( q4MuzzleFx',
):
    if preserved not in weapon:
        raise SystemExit(f"ERROR: V18E cumulative-path regression: {preserved}")

IMPACT.write_text(impact, encoding="utf-8")
HEADER.write_text(header, encoding="utf-8")
WEAPON.write_text(weapon, encoding="utf-8")

print("Q4BSE V18E SHOTGUN JOINT-MUZZLE FOLLOW PASS.")
print("  - live one-shot muzzle BSE transform refreshed from current animated flash joint")
print("  - joint_view_barrel selects native muzzle-smoke source joint")
print("  - exact V58/MG lowAmmo amber transform source-integrated")
print("  - V18C exact brass and all prior cumulative paths preserved")
