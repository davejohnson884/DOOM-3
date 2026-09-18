#!/usr/bin/env python3
'''V18U: Dark Matter live core-joint attachment + Raven light primitive.

Runs after V18T.  This pass deliberately leaves travelling suction/radius damage
for later.  It fixes the visual/mechanical issues exposed by the V18T test:
  * live core/core_start effects are re-anchored to the CURRENT animated inner_ring
    joint every frame instead of following the weapon entity's coarse physics basis;
  * Raven BSE light segments are rendered as real dynamic Doom 3 point lights;
  * core_start is one-shot (matching Raven), while idle core remains persistent.
'''

from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
HEADER = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.h'
WEAPON = ROOT / 'neo' / 'game' / 'Weapon.cpp'

for p in (IMPACT, HEADER, WEAPON):
    if not p.exists():
        raise SystemExit(f'ERROR: V18U prerequisite missing: {p}')

impact = IMPACT.read_text(encoding='utf-8-sig')
header = HEADER.read_text(encoding='utf-8-sig')
weapon = WEAPON.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V18U expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)

header = replace_once(
    header,
    '''bool Q4BSE_AttachPersistentEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis);
void Q4BSE_StopEntityEffectPath(idEntity* entity, const char* fxPath);''',
    '''bool Q4BSE_AttachPersistentEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis);
bool Q4BSE_UpdateEntityEffectTransform(idEntity* entity, const char* fxPath, const idVec3& worldOrigin, const idMat3& worldAxis);
void Q4BSE_StopEntityEffectPath(idEntity* entity, const char* fxPath);''',
    'live effect transform API declaration')

api_anchor = '''void Q4BSE_StopEntityEffectPath(idEntity* entity, const char* fxPath) {'''
api_impl = r'''bool Q4BSE_UpdateEntityEffectTransform(idEntity* entity, const char* fxPath, const idVec3& worldOrigin, const idMat3& worldAxis) {
    if (!entity || !entity->GetPhysics() || !fxPath || !fxPath[0]) return false;
    const idVec3 attachedOrigin = entity->GetPhysics()->GetOrigin();
    const idMat3 attachedAxis = entity->GetPhysics()->GetAxis();
    const idMat3 attachedAxisTranspose = attachedAxis.Transpose();
    bool updated = false;
    for (size_t i = 0; i < g_m3Impacts.size(); ++i) {
        M3ImpactInstance* instance = g_m3Impacts[i];
        if (!instance->attached || instance->attachedEntity.GetEntity() != entity ||
            idStr::Icmp(instance->effectPath.c_str(), fxPath)) {
            continue;
        }
        instance->attachedLocalOrigin = (worldOrigin - attachedOrigin) * attachedAxisTranspose;
        instance->attachedLocalAxis = worldAxis * attachedAxisTranspose;
        instance->attachedLocalTransform = true;
        instance->origin = worldOrigin;
        instance->axis = worldAxis;
        updated = true;
    }
    return updated;
}

'''
if impact.count(api_anchor) != 1:
    raise SystemExit(f'ERROR: V18U transform implementation anchor count={impact.count(api_anchor)}')
impact = impact.replace(api_anchor, api_impl + api_anchor, 1)

impact = replace_once(
    impact,
    '''    renderEntity_t renderEntity;
    std::vector<M3Particle> particles;''',
    '''    renderEntity_t renderEntity;
    bool q4LightConfigured;
    int q4LightHandle;
    int q4LightSegmentIndex;
    float q4LightBirthSec;
    float q4LightDurationSec;
    idVec3 q4LightLocalPosition;
    idVec3 q4LightSizeStart;
    idVec3 q4LightSizeEnd;
    idVec3 q4LightTintStart;
    idVec3 q4LightTintEnd;
    float q4LightFadeStart;
    float q4LightFadeEnd;
    renderLight_t q4Light;
    std::vector<M3Particle> particles;''',
    'M3 light state fields')

impact = replace_once(
    impact,
    '''        memset(&renderEntity, 0, sizeof(renderEntity));''',
    '''        memset(&renderEntity, 0, sizeof(renderEntity));
        q4LightConfigured = false;
        q4LightHandle = -1;
        q4LightSegmentIndex = -1;
        q4LightBirthSec = 0.0f;
        q4LightDurationSec = 0.0f;
        q4LightLocalPosition = vec3_origin;
        q4LightSizeStart = vec3_origin;
        q4LightSizeEnd = vec3_origin;
        q4LightTintStart.Set(1.0f, 1.0f, 1.0f);
        q4LightTintEnd = q4LightTintStart;
        q4LightFadeStart = 1.0f;
        q4LightFadeEnd = 1.0f;
        memset(&q4Light, 0, sizeof(q4Light));''',
    'M3 light state constructor init')

impact = replace_once(
    impact,
    '''static void FreeImpact(void) {
    if (gameRenderWorld && g_m3Impact.entityHandle >= 0) gameRenderWorld->FreeEntityDef(g_m3Impact.entityHandle);''',
    '''static void FreeImpact(void) {
    if (gameRenderWorld && g_m3Impact.q4LightHandle >= 0) gameRenderWorld->FreeLightDef(g_m3Impact.q4LightHandle);
    g_m3Impact.q4LightHandle = -1;
    g_m3Impact.q4LightConfigured = false;
    if (gameRenderWorld && g_m3Impact.entityHandle >= 0) gameRenderWorld->FreeEntityDef(g_m3Impact.entityHandle);''',
    'M3 dynamic-light cleanup')

start_anchor = '''static void StartAllSegments(void) {'''
if impact.count(start_anchor) != 1:
    raise SystemExit(f'ERROR: V18U StartAllSegments anchor count={impact.count(start_anchor)}')
light_helpers = r'''static void ConfigureLightSegment(int segmentIndex, const q4bse::Segment& segment) {
    if (!segment.hasParticle || g_m3Impact.q4LightConfigured) return;
    const q4bse::ParticleTemplate& pt = segment.particle;
    if (pt.material.empty()) return;

    g_m3Impact.q4LightConfigured = true;
    g_m3Impact.q4LightSegmentIndex = segmentIndex;
    g_m3Impact.q4LightBirthSec = SampleRange(segment.start, 0.0f, g_m3Impact.random);
    g_m3Impact.q4LightDurationSec = SampleRange(pt.duration, 0.1f, g_m3Impact.random);
    if (g_m3Impact.q4LightDurationSec < 0.001f) g_m3Impact.q4LightDurationSec = 0.001f;

    g_m3Impact.q4LightLocalPosition = vec3_origin;
    SampleVec3Domain(FindDomain(pt.start, "position"), g_m3Impact.q4LightLocalPosition, g_m3Impact.random, NULL);

    g_m3Impact.q4LightSizeStart.Set(1.0f, 1.0f, 1.0f);
    SampleVec3Domain(FindDomain(pt.start, "size"), g_m3Impact.q4LightSizeStart, g_m3Impact.random, NULL);
    g_m3Impact.q4LightSizeEnd = g_m3Impact.q4LightSizeStart;
    SampleVec3Domain(FindDomain(pt.end, "size"), g_m3Impact.q4LightSizeEnd, g_m3Impact.random, NULL);
    ApplyRelative(FindDomain(pt.end, "size"), g_m3Impact.q4LightSizeStart, g_m3Impact.q4LightSizeEnd);

    g_m3Impact.q4LightTintStart.Set(1.0f, 1.0f, 1.0f);
    SampleVec3Domain(FindDomain(pt.start, "tint"), g_m3Impact.q4LightTintStart, g_m3Impact.random, NULL);
    g_m3Impact.q4LightTintEnd = g_m3Impact.q4LightTintStart;
    SampleVec3Domain(FindDomain(pt.end, "tint"), g_m3Impact.q4LightTintEnd, g_m3Impact.random, NULL);
    ApplyRelative(FindDomain(pt.end, "tint"), g_m3Impact.q4LightTintStart, g_m3Impact.q4LightTintEnd);

    g_m3Impact.q4LightFadeStart = 1.0f;
    SampleFloatDomain(FindDomain(pt.start, "fade"), g_m3Impact.q4LightFadeStart, g_m3Impact.random);
    g_m3Impact.q4LightFadeEnd = g_m3Impact.q4LightFadeStart;
    SampleFloatDomain(FindDomain(pt.end, "fade"), g_m3Impact.q4LightFadeEnd, g_m3Impact.random);
    ApplyRelative(FindDomain(pt.end, "fade"), g_m3Impact.q4LightFadeStart, g_m3Impact.q4LightFadeEnd);

    memset(&g_m3Impact.q4Light, 0, sizeof(g_m3Impact.q4Light));
    g_m3Impact.q4Light.shader = declManager->FindMaterial(pt.material.c_str(), false);
    g_m3Impact.q4Light.pointLight = true;
    g_m3Impact.q4Light.noShadows = true;
    g_m3Impact.q4Light.shaderParms[SHADERPARM_TIMESCALE] = 1.0f;
}

static bool ServiceLight(float elapsedSec) {
    if (!g_m3Impact.q4LightConfigured || !gameRenderWorld || !g_m3Impact.effect ||
        g_m3Impact.q4LightSegmentIndex < 0 ||
        g_m3Impact.q4LightSegmentIndex >= (int)g_m3Impact.effect->segments.size()) {
        return false;
    }

    float age = elapsedSec - g_m3Impact.q4LightBirthSec;
    if (age < 0.0f) return true;

    if (age >= g_m3Impact.q4LightDurationSec) {
        if (g_m3Impact.attachedPersistent) {
            age = (float)fmod(age, g_m3Impact.q4LightDurationSec);
        } else {
            if (g_m3Impact.q4LightHandle >= 0) {
                gameRenderWorld->FreeLightDef(g_m3Impact.q4LightHandle);
                g_m3Impact.q4LightHandle = -1;
            }
            return false;
        }
    }

    const q4bse::Segment& segment = g_m3Impact.effect->segments[g_m3Impact.q4LightSegmentIndex];
    const q4bse::ParticleTemplate& pt = segment.particle;
    const float life = Clamp01(age / g_m3Impact.q4LightDurationSec);
    idVec3 radius = EvalVec3(g_m3Impact.q4LightSizeStart, g_m3Impact.q4LightSizeEnd,
                             FindDomain(pt.motion, "size"), life);
    radius.x = idMath::Fabs(radius.x); radius.y = idMath::Fabs(radius.y); radius.z = idMath::Fabs(radius.z);
    const idVec3 tint = EvalVec3(g_m3Impact.q4LightTintStart, g_m3Impact.q4LightTintEnd,
                                 FindDomain(pt.motion, "tint"), life);
    const float fade = EvalFloat(g_m3Impact.q4LightFadeStart, g_m3Impact.q4LightFadeEnd,
                                 FindDomain(pt.motion, "fade"), life);

    g_m3Impact.q4Light.origin = g_m3Impact.origin + g_m3Impact.axis * g_m3Impact.q4LightLocalPosition;
    g_m3Impact.q4Light.axis = g_m3Impact.axis;
    g_m3Impact.q4Light.lightRadius = radius;
    g_m3Impact.q4Light.shaderParms[SHADERPARM_RED] = tint.x * fade;
    g_m3Impact.q4Light.shaderParms[SHADERPARM_GREEN] = tint.y * fade;
    g_m3Impact.q4Light.shaderParms[SHADERPARM_BLUE] = tint.z * fade;
    g_m3Impact.q4Light.shaderParms[SHADERPARM_ALPHA] = 1.0f;

    if (g_m3Impact.q4LightHandle >= 0) gameRenderWorld->UpdateLightDef(g_m3Impact.q4LightHandle, &g_m3Impact.q4Light);
    else g_m3Impact.q4LightHandle = gameRenderWorld->AddLightDef(&g_m3Impact.q4Light);
    return true;
}

'''
impact = impact.replace(start_anchor, light_helpers + start_anchor, 1)

segment_anchor = '''        if (segment.type == "sound") { PlaySoundSegment(segment); continue; }'''
segment_new = '''        if (segment.type == "sound") { PlaySoundSegment(segment); continue; }
        if (segment.type == "light") { ConfigureLightSegment(i, segment); continue; }'''
impact = replace_once(impact, segment_anchor, segment_new, 'light segment startup')

frame_anchor = '''        PruneExpiredParticles(elapsedSec);
        ServiceEmitters(elapsedSec);'''
frame_new = '''        PruneExpiredParticles(elapsedSec);
        ServiceEmitters(elapsedSec);
        ServiceLight(elapsedSec);'''
impact = replace_once(impact, frame_anchor, frame_new, 'light frame service')

expiry_anchor = '''        if ((g_m3Impact.attached && g_m3Impact.attachedPersistent) || AnyEmitterActive() || AnyParticleAlive(elapsedSec)) {'''
expiry_new = '''        if ((g_m3Impact.attached && g_m3Impact.attachedPersistent) || AnyEmitterActive() || AnyParticleAlive(elapsedSec) || ServiceLight(elapsedSec)) {'''
impact = replace_once(impact, expiry_anchor, expiry_new, 'light lifetime retention')

weapon = replace_once(
    weapon,
    '''						Q4BSE_AttachPersistentEffectToEntityTransform( q4ChosenCoreFx, this, q4CoreOrigin, q4CoreAxis );''',
    '''						if ( q4DesiredCoreMode == 1 ) {
							Q4BSE_AttachEffectToEntityTransform( q4ChosenCoreFx, this, q4CoreOrigin, q4CoreAxis );
						} else {
							Q4BSE_AttachPersistentEffectToEntityTransform( q4ChosenCoreFx, this, q4CoreOrigin, q4CoreAxis );
						}''',
    'Raven core_start one-shot attachment')

end_anchor = '''			spawnArgs.Set( "_q4_dmg_core_mode", va( "%d", q4DesiredCoreMode ) );
		}
	}

'''
if weapon.count(end_anchor) != 1:
    raise SystemExit(f'ERROR: V18U Dark Matter runtime tail anchor count={weapon.count(end_anchor)}')
update_block = r'''			spawnArgs.Set( "_q4_dmg_core_mode", va( "%d", q4DesiredCoreMode ) );
		}

		if ( q4DesiredCoreMode != 0 ) {
			const char *q4CoreStartFx = weaponDef->dict.GetString( "fx_core_start" );
			const char *q4CoreFx = weaponDef->dict.GetString( "fx_core" );
			const char *q4ChosenCoreFx = ( q4DesiredCoreMode == 1 ) ? q4CoreStartFx : q4CoreFx;
			const char *q4CoreJointName = weaponDef->dict.GetString( "joint_core" );
			const jointHandle_t q4CoreJoint = ( q4CoreJointName && q4CoreJointName[0] ) ? animator.GetJointHandle( q4CoreJointName ) : INVALID_JOINT;
			if ( q4CoreJoint != INVALID_JOINT && q4ChosenCoreFx && q4ChosenCoreFx[0] ) {
				idVec3 q4LocalCoreOrigin;
				idMat3 q4LocalCoreAxis;
				if ( animator.GetJointTransform( q4CoreJoint, gameLocal.time, q4LocalCoreOrigin, q4LocalCoreAxis ) ) {
					idVec3 q4PresentedOrigin = viewWeaponOrigin;
					idMat3 q4PresentedAxis = viewWeaponAxis;
					idMat3 q4FxBaseAxis = viewWeaponAxis;
					const char *q4ViewStyleName = weaponDef->dict.GetString( "def_viewStyle" );
					if ( q4ViewStyleName && q4ViewStyleName[0] ) {
						const idDeclEntityDef *q4ViewStyleDef = gameLocal.FindEntityDef( q4ViewStyleName, false );
						if ( q4ViewStyleDef ) {
							const idVec3 q4ViewOffset = q4ViewStyleDef->dict.GetVector( "viewoffset", "0 0 0" );
							const idAngles q4ViewAngles = q4ViewStyleDef->dict.GetAngles( "viewangles", "0 0 0" );
							const float q4Foreshorten = weaponDef->dict.GetFloat( "foreshorten", "1" );
							q4PresentedOrigin += q4ViewOffset * viewWeaponAxis;
							q4FxBaseAxis = q4ViewAngles.ToMat3() * viewWeaponAxis;
							q4PresentedAxis = q4FxBaseAxis;
							q4PresentedAxis[0] *= q4Foreshorten;
						}
					}
					const idVec3 q4CoreOrigin = q4LocalCoreOrigin * q4PresentedAxis + q4PresentedOrigin;
					const idMat3 q4CoreAxis = q4LocalCoreAxis * q4FxBaseAxis;
					Q4BSE_UpdateEntityEffectTransform( this, q4ChosenCoreFx, q4CoreOrigin, q4CoreAxis );
				}
			}
		}
	}

'''
weapon = weapon.replace(end_anchor, update_block, 1)

combined = impact + header + weapon
for required in (
    'Q4BSE_UpdateEntityEffectTransform', 'q4LightConfigured', 'ConfigureLightSegment',
    'ServiceLight', 'AddLightDef', 'q4DesiredCoreMode == 1',
    'animator.GetJointTransform( q4CoreJoint', 'Q4BSE_UpdateEntityEffectTransform( this, q4ChosenCoreFx',
):
    if required not in combined:
        raise SystemExit(f'ERROR: V18U verification missing: {required}')

IMPACT.write_text(impact, encoding='utf-8')
HEADER.write_text(header, encoding='utf-8')
WEAPON.write_text(weapon, encoding='utf-8')

print('Q4BSE V18U DARK MATTER LIVE CORE/LIGHT PASS.')
print('  - core/core_start transform refreshed from the animated inner_ring every frame')
print('  - core_start is one-shot; idle core remains persistent')
print('  - Raven BSE light segments now create/update/free real Doom 3 dynamic lights')
print('  - no Dark Matter travelling suction/radius damage added')
