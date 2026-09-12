#!/usr/bin/env python3
"""V16: lock short-lived Raven muzzle FX to the moving view weapon and restore Q4 GUI light semantics.

Runs after q4bse_port/extend_q4bse_attached_fx.py.

This deliberately leaves the now-validated HyperBlaster BSE visuals untouched.  It only:
  * adds a non-persistent entity-local BSE attachment mode for one-shot muzzle FX
  * makes those one-shot FX follow the weapon's authoritative bob/recoil transform for their lifetime
  * keeps projectile fx_fly's existing persistent attachment behavior unchanged
  * restores Q4 joint_view_guiLight, glightRadius and glightOffset support
  * places the GUI light in the same Q4 viewStyle/foreshortened presentation space as the rendered gun
"""

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"
HEADER = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.h"
WEAPON = ROOT / "neo" / "game" / "Weapon.cpp"

for p in (IMPACT, HEADER, WEAPON):
    if not p.exists():
        raise SystemExit(f"ERROR: V16 prerequisite missing: {p}")


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f"ERROR: V16 expected exactly one {label}, found {hits}")
    return text.replace(old, new, 1)


impact = IMPACT.read_text(encoding="utf-8-sig")
header = HEADER.read_text(encoding="utf-8-sig")
weapon = WEAPON.read_text(encoding="utf-8-sig")

# -----------------------------------------------------------------------------
# Public API: a one-shot BSE effect can be attached to a moving entity while
# retaining the exact world transform at which it was authored/spawned.
# -----------------------------------------------------------------------------
header = replace_once(
    header,
    '''bool Q4BSE_PlayEffectAxis(const char* fxPath, const idVec3& origin, const idMat3& axis);\nbool Q4BSE_AttachEffectToEntity(const char* fxPath, idEntity* entity);\nvoid Q4BSE_StopEntityEffects(idEntity* entity);''',
    '''bool Q4BSE_PlayEffectAxis(const char* fxPath, const idVec3& origin, const idMat3& axis);\nbool Q4BSE_AttachEffectToEntity(const char* fxPath, idEntity* entity);\nbool Q4BSE_AttachEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis);\nvoid Q4BSE_StopEntityEffects(idEntity* entity);''',
    "BSE attachment API header")

# -----------------------------------------------------------------------------
# Runtime instance state. Projectile fly FX stay attached until explicitly
# stopped. Muzzle FX use a local transform attachment but expire naturally.
# -----------------------------------------------------------------------------
impact = replace_once(
    impact,
    '''    bool attached;\n    idEntityPtr<idEntity> attachedEntity;\n    idVec3 origin;\n    idMat3 axis;''',
    '''    bool attached;\n    bool attachedPersistent;\n    bool attachedLocalTransform;\n    idEntityPtr<idEntity> attachedEntity;\n    idVec3 attachedLocalOrigin;\n    idMat3 attachedLocalAxis;\n    idVec3 origin;\n    idMat3 axis;''',
    "M3 attachment state fields")

impact = replace_once(
    impact,
    ''': active(false), effect(NULL), serial(0), attached(false), origin(vec3_origin), axis(mat3_identity), startTimeMS(0),''',
    ''': active(false), effect(NULL), serial(0), attached(false), attachedPersistent(false), attachedLocalTransform(false), attachedLocalOrigin(vec3_origin), attachedLocalAxis(mat3_identity), origin(vec3_origin), axis(mat3_identity), startTimeMS(0),''',
    "M3 attachment constructor")

impact = replace_once(
    impact,
    '''static bool StartEffectAtAxis(const q4bse::Effect* effect, const char* effectPath,\n                              const idVec3& origin, const idMat3& axis,\n                              idEntity* attachedEntity) {''',
    '''static bool StartEffectAtAxis(const q4bse::Effect* effect, const char* effectPath,\n                              const idVec3& origin, const idMat3& axis,\n                              idEntity* attachedEntity, bool attachedPersistent,\n                              bool attachedLocalTransform) {''',
    "StartEffectAtAxis signature")

impact = replace_once(
    impact,
    '''    g_m3Impact.attached = attachedEntity != NULL;\n    g_m3Impact.attachedEntity = attachedEntity;\n    g_m3Impact.origin = origin;\n    g_m3Impact.axis = axis;''',
    '''    g_m3Impact.attached = attachedEntity != NULL;\n    g_m3Impact.attachedPersistent = attachedEntity != NULL && attachedPersistent;\n    g_m3Impact.attachedLocalTransform = false;\n    g_m3Impact.attachedEntity = attachedEntity;\n    g_m3Impact.origin = origin;\n    g_m3Impact.axis = axis;\n\n    if (attachedEntity && attachedLocalTransform && attachedEntity->GetPhysics()) {\n        const idVec3 attachedOrigin = attachedEntity->GetPhysics()->GetOrigin();\n        const idMat3 attachedAxis = attachedEntity->GetPhysics()->GetAxis();\n        const idMat3 attachedAxisTranspose = attachedAxis.Transpose();\n        g_m3Impact.attachedLocalOrigin = (origin - attachedOrigin) * attachedAxisTranspose;\n        g_m3Impact.attachedLocalAxis = axis * attachedAxisTranspose;\n        g_m3Impact.attachedLocalTransform = true;\n    }''',
    "StartEffectAtAxis attachment initialization")

impact = replace_once(
    impact,
    '''    return StartEffectAtAxis(effect, effectPath, origin, n.ToMat3(), NULL);''',
    '''    return StartEffectAtAxis(effect, effectPath, origin, n.ToMat3(), NULL, false, false);''',
    "normal-oriented one-shot caller")

impact = replace_once(
    impact,
    '''    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), origin, axis, NULL);''',
    '''    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), origin, axis, NULL, false, false);''',
    "axis one-shot caller")

impact = replace_once(
    impact,
    '''    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), origin, axis, entity);\n}\n\nvoid Q4BSE_StopEntityEffects''',
    '''    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), origin, axis, entity, true, false);\n}\n\nbool Q4BSE_AttachEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis) {\n    if (!g_m3Initialized || !gameRenderWorld || !fxPath || !fxPath[0] || !entity || !entity->GetPhysics()) return false;\n    M3CachedEffect* cached = GetOrLoadEffect(fxPath);\n    if (!cached) return false;\n\n    // The effect is authored in the already-presented weapon-joint transform.\n    // Store that transform relative to the weapon's authoritative physics basis\n    // so strafing, turning, bob and recoil move the live BSE instance with it.\n    // Unlike projectile fly FX this is still a one-shot: it dies when its Raven\n    // emitters/particles are finished.\n    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), worldOrigin, worldAxis, entity, false, true);\n}\n\nvoid Q4BSE_StopEntityEffects''',
    "entity attachment callers and transform API")

# Only projectile-style persistent attachments loop Raven constant particles.
impact = replace_once(
    impact,
    '''    if (g_m3Impact.attached && p.segment->constant) {''',
    '''    if (g_m3Impact.attachedPersistent && p.segment->constant) {''',
    "constant render lifetime scope")
impact = replace_once(
    impact,
    '''        if (g_m3Impact.attached && p.segment && p.segment->constant && elapsedSec >= p.birthSec) return true;''',
    '''        if (g_m3Impact.attachedPersistent && p.segment && p.segment->constant && elapsedSec >= p.birthSec) return true;''',
    "constant alive lifetime scope")

# Update attached transforms each service frame. For weapon muzzle FX, preserve the
# presented joint's local offset/orientation. Projectile fly FX retain velocity-axis behavior.
impact = replace_once(
    impact,
    '''            g_m3Impact.origin = attached->GetPhysics()->GetOrigin();\n            idVec3 forward = attached->GetPhysics()->GetLinearVelocity();\n            if (forward.LengthSqr() > M3_EPSILON) {\n                forward.NormalizeFast();\n                g_m3Impact.axis = forward.ToMat3();\n            }''',
    '''            if (!attached->GetPhysics()) {\n                FreeImpact();\n                delete g_m3Impacts[i];\n                g_m3Impacts.erase(g_m3Impacts.begin() + i);\n                continue;\n            }\n\n            if (g_m3Impact.attachedLocalTransform) {\n                const idVec3 attachedOrigin = attached->GetPhysics()->GetOrigin();\n                const idMat3 attachedAxis = attached->GetPhysics()->GetAxis();\n                g_m3Impact.origin = attachedOrigin + g_m3Impact.attachedLocalOrigin * attachedAxis;\n                g_m3Impact.axis = g_m3Impact.attachedLocalAxis * attachedAxis;\n            } else {\n                g_m3Impact.origin = attached->GetPhysics()->GetOrigin();\n                idVec3 forward = attached->GetPhysics()->GetLinearVelocity();\n                if (forward.LengthSqr() > M3_EPSILON) {\n                    forward.NormalizeFast();\n                    g_m3Impact.axis = forward.ToMat3();\n                }\n            }''',
    "attached transform frame update")

impact = replace_once(
    impact,
    '''        if (g_m3Impact.attached || AnyEmitterActive() || AnyParticleAlive(elapsedSec)) {''',
    '''        if ((g_m3Impact.attached && g_m3Impact.attachedPersistent) || AnyEmitterActive() || AnyParticleAlive(elapsedSec)) {''',
    "attached natural expiry")

# -----------------------------------------------------------------------------
# Weapon muzzle FX: same exact spawn transform as V15, but now bound back to the
# weapon's authoritative basis for the 0.05-0.25 s Raven particle lifetime.
# -----------------------------------------------------------------------------
weapon = replace_once(
    weapon,
    '''\t\t\t\tQ4BSE_PlayEffectAxis( q4MuzzleFx, q4FxOrigin, q4FxAxis );''',
    '''\t\t\t\tQ4BSE_AttachEffectToEntityTransform( q4MuzzleFx, this, q4FxOrigin, q4FxAxis );''',
    "muzzle BSE attachment call")

# Q4's weapon defs select the GUI-light joint by key; HyperBlaster uses body.
weapon = replace_once(
    weapon,
    '''\tejectJointView = animator.GetJointHandle( "eject" );\n\tguiLightJointView = animator.GetJointHandle( "guiLight" );''',
    '''\tejectJointView = animator.GetJointHandle( "eject" );\n\tconst char *q4GuiLightJointName = weaponDef->dict.GetString( "joint_view_guiLight" );\n\tguiLightJointView = animator.GetJointHandle( ( q4GuiLightJointName && q4GuiLightJointName[0] ) ? q4GuiLightJointName : "guiLight" );''',
    "Q4 GUI-light joint selection")

# Raven supports glightRadius; Doom 3 hardcodes 3. Preserve Doom 3 default for
# weapons without the Q4 key.
weapon = replace_once(
    weapon,
    '''\t\tguiLight.shader = declManager->FindMaterial( guiLightShader, false );\n\t\tguiLight.lightRadius[0] = guiLight.lightRadius[1] = guiLight.lightRadius[2] = 3;\n\t\tguiLight.pointLight = true;''',
    '''\t\tguiLight.shader = declManager->FindMaterial( guiLightShader, false );\n\t\tconst float q4GuiLightRadius = weaponDef->dict.GetFloat( "glightRadius", "3" );\n\t\tguiLight.lightRadius[0] = guiLight.lightRadius[1] = guiLight.lightRadius[2] = q4GuiLightRadius;\n\t\tguiLight.pointLight = true;''',
    "Q4 GUI-light radius")

# The stock Doom 3 GUI light uses the unpresented joint transform. Rebuild only
# this visual attachment in the same viewStyle/foreshortened coordinate system
# used by the rendered Q4 weapon. Raven's glightOffset is joint-local and is
# applied before the view-model presentation transform.
old_gui_update = '''\t// update the gui light\n\tif ( guiLight.lightRadius[0] && guiLightJointView != INVALID_JOINT ) {\n\t\tGetGlobalJointTransform( true, guiLightJointView, guiLight.origin, guiLight.axis );\n\n\t\tif ( ( guiLightHandle != -1 ) ) {\n\t\t\tgameRenderWorld->UpdateLightDef( guiLightHandle, &guiLight );\n\t\t} else {\n\t\t\tguiLightHandle = gameRenderWorld->AddLightDef( &guiLight );\n\t\t}\n\t}'''

new_gui_update = '''\t// update the gui light\n\tif ( guiLight.lightRadius[0] && guiLightJointView != INVALID_JOINT ) {\n\t\tidVec3 q4GuiLocalOrigin;\n\t\tidMat3 q4GuiLocalAxis;\n\t\tif ( animator.GetJointTransform( guiLightJointView, gameLocal.time, q4GuiLocalOrigin, q4GuiLocalAxis ) ) {\n\t\t\tconst idVec3 q4GuiOffset = weaponDef ? weaponDef->dict.GetVector( "glightOffset", "0 0 0" ) : vec3_origin;\n\t\t\tq4GuiLocalOrigin = q4GuiOffset * q4GuiLocalAxis + q4GuiLocalOrigin;\n\n\t\t\tidVec3 q4GuiPresentedOrigin = viewWeaponOrigin;\n\t\t\tidMat3 q4GuiPresentedAxis = viewWeaponAxis;\n\t\t\tidMat3 q4GuiBaseAxis = viewWeaponAxis;\n\n\t\t\tif ( weaponDef ) {\n\t\t\t\tconst char *q4ViewStyleName = weaponDef->dict.GetString( "def_viewStyle" );\n\t\t\t\tif ( q4ViewStyleName && q4ViewStyleName[0] ) {\n\t\t\t\t\tconst idDeclEntityDef *q4ViewStyleDef = gameLocal.FindEntityDef( q4ViewStyleName, false );\n\t\t\t\t\tif ( q4ViewStyleDef ) {\n\t\t\t\t\t\tconst idVec3 q4ViewOffset = q4ViewStyleDef->dict.GetVector( "viewoffset", "0 0 0" );\n\t\t\t\t\t\tconst idAngles q4ViewAngles = q4ViewStyleDef->dict.GetAngles( "viewangles", "0 0 0" );\n\t\t\t\t\t\tconst float q4Foreshorten = weaponDef->dict.GetFloat( "foreshorten", "1" );\n\n\t\t\t\t\t\tq4GuiPresentedOrigin += q4ViewOffset * viewWeaponAxis;\n\t\t\t\t\t\tq4GuiBaseAxis = q4ViewAngles.ToMat3() * viewWeaponAxis;\n\t\t\t\t\t\tq4GuiPresentedAxis = q4GuiBaseAxis;\n\t\t\t\t\t\tq4GuiPresentedAxis[0] *= q4Foreshorten;\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\n\t\t\tguiLight.origin = q4GuiLocalOrigin * q4GuiPresentedAxis + q4GuiPresentedOrigin;\n\t\t\tguiLight.axis = q4GuiLocalAxis * q4GuiBaseAxis;\n\t\t}\n\n\t\tif ( ( guiLightHandle != -1 ) ) {\n\t\t\tgameRenderWorld->UpdateLightDef( guiLightHandle, &guiLight );\n\t\t} else {\n\t\t\tguiLightHandle = gameRenderWorld->AddLightDef( &guiLight );\n\t\t}\n\t}'''
weapon = replace_once(weapon, old_gui_update, new_gui_update, "presentation-correct GUI light update")

# Hard gates: do not silently produce a DLL that regresses the validated V15 path.
for needle in (
    "attachedPersistent",
    "attachedLocalTransform",
    "attachedLocalOrigin",
    "Q4BSE_AttachEffectToEntityTransform",
    "g_m3Impact.attachedPersistent && p.segment->constant",
    "g_m3Impact.attachedLocalAxis * attachedAxis",
):
    if needle not in impact:
        raise SystemExit(f"ERROR: V16 runtime verification missing: {needle}")

for needle in (
    'weaponDef->dict.GetString( "joint_view_guiLight" )',
    'weaponDef->dict.GetFloat( "glightRadius", "3" )',
    'weaponDef->dict.GetVector( "glightOffset", "0 0 0" )',
    "Q4BSE_AttachEffectToEntityTransform( q4MuzzleFx, this, q4FxOrigin, q4FxAxis )",
    "q4GuiPresentedAxis[0] *= q4Foreshorten",
):
    if needle not in weapon:
        raise SystemExit(f"ERROR: V16 weapon verification missing: {needle}")

IMPACT.write_text(impact, encoding="utf-8")
HEADER.write_text(header, encoding="utf-8")
WEAPON.write_text(weapon, encoding="utf-8")

print("Q4BSE V16 MUZZLE LOCK + GUI LIGHT PASS.")
print("  - Raven muzzle FX remain visually identical to V15/V1.26")
print("  - one-shot muzzle FX now follow weapon translation/rotation/bob/recoil")
print("  - muzzle FX still expire on their authored Raven lifetime")
print("  - projectile fly FX retain persistent attachment semantics")
print("  - Q4 joint_view_guiLight / glightRadius / glightOffset restored")
print("  - GUI light is transformed through Q4 viewStyle + foreshorten")
