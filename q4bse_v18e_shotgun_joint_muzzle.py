#!/usr/bin/env python3
"""V18E: animated-joint muzzle follow + native smoke joint + generic lowAmmo color.

Runs after V18D. It source-integrates the last two behaviors that had only been
proven through later weapon-specific binaries/content:
  * live one-shot BSE muzzle FX can refresh from the CURRENT animated flash joint;
  * the V58/Machinegun low-ammo color transform uses idWeapon::lowAmmo.
It also adds joint_view_barrel so native Doom 3 muzzle smoke can follow an
existing Q4 joint without adding a synthetic helper bone.
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

# Public API for refreshing an already-live V16 local-transform muzzle effect.
header = replace_once(
    header,
    'bool Q4BSE_AttachEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis);\nvoid Q4BSE_StopEntityEffects(idEntity* entity);',
    'bool Q4BSE_AttachEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis);\nbool Q4BSE_UpdateEntityEffectTransform(idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis);\nvoid Q4BSE_StopEntityEffects(idEntity* entity);',
    "animated-joint update declaration")

api_anchor = '''bool Q4BSE_AttachEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis) {
    if (!g_m3Initialized || !gameRenderWorld || !fxPath || !fxPath[0] || !entity || !entity->GetPhysics()) return false;
    M3CachedEffect* cached = GetOrLoadEffect(fxPath);
    if (!cached) return false;

    // The effect is authored in the already-presented weapon-joint transform.
    // Store that transform relative to the weapon's authoritative physics basis
    // so strafing, turning, bob and recoil move the live BSE instance with it.
    // Unlike projectile fly FX this is still a one-shot: it dies when its Raven
    // emitters/particles are finished.
    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), worldOrigin, worldAxis, entity, false, true);
}

void Q4BSE_StopEntityEffects'''
api_new = '''bool Q4BSE_AttachEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis) {
    if (!g_m3Initialized || !gameRenderWorld || !fxPath || !fxPath[0] || !entity || !entity->GetPhysics()) return false;
    M3CachedEffect* cached = GetOrLoadEffect(fxPath);
    if (!cached) return false;

    // The effect is authored in the already-presented weapon-joint transform.
    // Store that transform relative to the weapon's authoritative physics basis
    // so strafing, turning, bob and recoil move the live BSE instance with it.
    // Unlike projectile fly FX this is still a one-shot: it dies when its Raven
    // emitters/particles are finished.
    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), worldOrigin, worldAxis, entity, false, true);
}

bool Q4BSE_UpdateEntityEffectTransform(idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis) {
    if (!entity || !entity->GetPhysics()) return false;

    const idVec3 entityOrigin = entity->GetPhysics()->GetOrigin();
    const idMat3 entityAxis = entity->GetPhysics()->GetAxis();
    const idMat3 entityAxisTranspose = entityAxis.Transpose();
    bool updated = false;

    for (size_t i = 0; i < g_m3Impacts.size(); ++i) {
        M3ImpactInstance* instance = g_m3Impacts[i];
        if (!instance || !instance->active || !instance->attached ||
            instance->attachedPersistent || !instance->attachedLocalTransform ||
            instance->attachedEntity.GetEntity() != entity) {
            continue;
        }

        instance->attachedLocalOrigin = (worldOrigin - entityOrigin) * entityAxisTranspose;
        instance->attachedLocalAxis = worldAxis * entityAxisTranspose;
        instance->origin = worldOrigin;
        instance->axis = worldAxis;
        updated = true;
    }
    return updated;
}

void Q4BSE_StopEntityEffects'''
impact = replace_once(impact, api_anchor, api_new, "animated-joint update implementation")

# V14 already inserted Q4 joint_view_flash selection after this line, so replace
# ONLY the barrel line and leave that validated flash selection untouched.
weapon = replace_once(
    weapon,
    '\tbarrelJointView = animator.GetJointHandle( "barrel" );',
    '\tconst char *q4BarrelJointName = weaponDef->dict.GetString( "joint_view_barrel" );\n\tbarrelJointView = animator.GetJointHandle( ( q4BarrelJointName && q4BarrelJointName[0] ) ? q4BarrelJointName : "barrel" );',
    "Q4 barrel-joint selection")

# Exact V58/MG machine-code transform: for 0 < ammo <= lowAmmo,
# (r,g,b) -> (g, 2*r, b). Exact-zero remains glightEmptyColor.
low_old = '''\t\t\t\tidVec3 q4GuiColor = weaponDef->dict.GetVector( "glightColor", "1 1 1" );
\t\t\t\tif ( q4AmmoInClip <= 0 ) {
\t\t\t\t\tq4GuiColor = weaponDef->dict.GetVector( "glightEmptyColor", "1 0 0" );
\t\t\t\t}
\t\t\t\tguiLight.shaderParms[ SHADERPARM_RED ] = q4GuiColor.x;'''
low_new = '''\t\t\t\tidVec3 q4GuiColor = weaponDef->dict.GetVector( "glightColor", "1 1 1" );
\t\t\t\tif ( q4AmmoInClip <= 0 ) {
\t\t\t\t\tq4GuiColor = weaponDef->dict.GetVector( "glightEmptyColor", "1 0 0" );
\t\t\t\t} else if ( q4AmmoInClip <= lowAmmo ) {
\t\t\t\t\tconst float q4BaseRed = q4GuiColor.x;
\t\t\t\t\tq4GuiColor.x = q4GuiColor.y;
\t\t\t\t\tq4GuiColor.y = q4BaseRed * 2.0f;
\t\t\t\t}
\t\t\t\tguiLight.shaderParms[ SHADERPARM_RED ] = q4GuiColor.x;'''
weapon = replace_once(weapon, low_old, low_new, "generic lowAmmo GUI color")

# Refresh any live one-shot weapon muzzle BSE from the CURRENT animated flash
# joint every PresentWeapon frame. This adds the internal bone animation that
# V16's entity-basis attachment cannot know about by itself.
present_anchor = '''\t// update the gui light
\tif ( guiLight.lightRadius[0] && guiLightJointView != INVALID_JOINT ) {'''
present_new = r'''	// Q4 V18E: keep live one-shot muzzle BSE locked to the CURRENT animated
	// flash joint. V16 follows entity bob/turn/recoil; this adds bone animation.
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
weapon = replace_once(weapon, present_anchor, present_new, "PresentWeapon animated-joint refresh")

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
print("  - live one-shot muzzle BSE refreshes from current animated flash joint")
print("  - joint_view_barrel selects native muzzle-smoke source joint")
print("  - exact V58/MG lowAmmo amber transform source-integrated")
print("  - V18C exact brass and prior cumulative paths preserved")
