#!/usr/bin/env python3
"""V14: complete the HyperBlaster BSE firing-chain bridge.

Runs after finalize_q4bse_projectile_visual_ownership.py.

Adds:
  * reliable Raven decal projection through Doom 3's public game decal helper
  * Raven particle start 'offset' domain support
  * axis-aware one-shot effects (for weapon muzzle FX)
  * entity-attached BSE effects (for projectile fx_fly)
  * constant attached-spawner looping semantics needed by HyperBlaster fly.fx
  * projectile launch/stop lifecycle integration for fx_fly
  * presentation-aware weapon joint playback for fx_muzzleflash
  * Q4 joint_view_flash key support

No Doom 3 particle replacement is introduced. The content package decides whether
fx_fly / fx_muzzleflash are present; weapons without those keys are untouched.
"""
from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"
HEADER = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.h"
PROJECTILE = ROOT / "neo" / "game" / "Projectile.cpp"
WEAPON = ROOT / "neo" / "game" / "Weapon.cpp"

for p in (IMPACT, HEADER, PROJECTILE, WEAPON):
    if not p.exists():
        raise SystemExit(f"ERROR: V14 prerequisite missing: {p}")

def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f"ERROR: V14 expected exactly one {label}, found {hits}")
    return text.replace(old, new, 1)

def replace_regex_once(text, pattern, repl, label, flags=0):
    matches = list(re.finditer(pattern, text, flags))
    if len(matches) != 1:
        raise SystemExit(f"ERROR: V14 expected exactly one regex {label}, found {len(matches)}")
    return re.sub(pattern, repl, text, count=1, flags=flags)

impact = IMPACT.read_text(encoding="utf-8-sig")
header = HEADER.read_text(encoding="utf-8-sig")
projectile = PROJECTILE.read_text(encoding="utf-8-sig")
weapon = WEAPON.read_text(encoding="utf-8-sig")

# Public API.
api_anchor = "bool Q4BSE_PlayEffect(const char* fxPath, const idVec3& origin, const idVec3& normal);\nint Q4BSE_ActiveEffectCount(void);"
api_new = '''bool Q4BSE_PlayEffect(const char* fxPath, const idVec3& origin, const idVec3& normal);
bool Q4BSE_PlayEffectAxis(const char* fxPath, const idVec3& origin, const idMat3& axis);
bool Q4BSE_AttachEffectToEntity(const char* fxPath, idEntity* entity);
void Q4BSE_StopEntityEffects(idEntity* entity);
int Q4BSE_ActiveEffectCount(void);'''
header = replace_once(header, api_anchor, api_new, "public BSE gameplay API block")
if "class idEntity;" not in header:
    header = replace_once(header, "#define __Q4BSE_IMPACT_M3_H__\n", "#define __Q4BSE_IMPACT_M3_H__\n\nclass idEntity;\n", "header guard")

# Runtime instance / particle state.
particle_anchor = '''    idVec3 localPosition;
    idVec3 localVelocity;'''
particle_new = '''    idVec3 localPosition;
    idVec3 localOffset;
    idVec3 localVelocity;'''
impact = replace_once(impact, particle_anchor, particle_new, "M3Particle local offset field")

ctor_anchor = ''': active(false), effect(NULL), serial(0), origin(vec3_origin), axis(mat3_identity), startTimeMS(0),'''
particle_ctor_anchor = '''          localPosition(vec3_origin), localVelocity(vec3_origin), worldGravityAcceleration(vec3_origin),'''
particle_ctor_new = '''          localPosition(vec3_origin), localOffset(vec3_origin), localVelocity(vec3_origin), worldGravityAcceleration(vec3_origin),'''
impact = replace_once(impact, particle_ctor_anchor, particle_ctor_new, "M3Particle local offset constructor")

inst_anchor = '''    unsigned int serial;
    idVec3 origin;
    idMat3 axis;'''
inst_new = '''    unsigned int serial;
    bool attached;
    idEntityPtr<idEntity> attachedEntity;
    idVec3 origin;
    idMat3 axis;'''
impact = replace_once(impact, inst_anchor, inst_new, "M3 instance attachment fields")

inst_ctor_new = ''': active(false), effect(NULL), serial(0), attached(false), origin(vec3_origin), axis(mat3_identity), startTimeMS(0),'''
impact = replace_once(impact, ctor_anchor, inst_ctor_new, "M3 instance attachment constructor")

# Raven start offset. Required by fly.fx and muzzleflash.fx.
offset_anchor = '''    const q4bse::Domain* startPosition = FindDomain(pt.start, "position");
    idVec3 generatedNormal(1.0f, 0.0f, 0.0f);
    SampleVec3Domain(startPosition, p.localPosition, g_m3Impact.random,
                     (pt.generatedOriginNormal || pt.generatedNormal) ? &generatedNormal : NULL);
    SampleVec3Domain(FindDomain(pt.start, "velocity"), p.localVelocity, g_m3Impact.random, NULL);'''
offset_new = '''    const q4bse::Domain* startPosition = FindDomain(pt.start, "position");
    idVec3 generatedNormal(1.0f, 0.0f, 0.0f);
    SampleVec3Domain(startPosition, p.localPosition, g_m3Impact.random,
                     (pt.generatedOriginNormal || pt.generatedNormal) ? &generatedNormal : NULL);
    SampleVec3Domain(FindDomain(pt.start, "offset"), p.localOffset, g_m3Impact.random, NULL);
    SampleVec3Domain(FindDomain(pt.start, "velocity"), p.localVelocity, g_m3Impact.random, NULL);'''
impact = replace_once(impact, offset_anchor, offset_new, "particle start offset sampling")
impact = replace_once(impact,
    "    const idVec3 local = p.localPosition + p.localVelocity * ageSec;",
    "    const idVec3 local = p.localPosition + p.localOffset + p.localVelocity * ageSec;",
    "particle world position offset")

# Reliable world decal projection.
decal_pattern = r'''static void ProjectDecalSegment\(const q4bse::Segment& segment\) \{.*?\n\}\n\nstatic int SampleSpawnerCount'''
decal_repl = r'''static void ProjectDecalSegment(const q4bse::Segment& segment) {
    if (!gameRenderWorld || !declManager || !segment.hasParticle) return;
    const q4bse::ParticleTemplate& pt = segment.particle;
    if (pt.material.empty()) return;

    const idMaterial* material = declManager->FindMaterial(pt.material.c_str(), false);
    if (!material) {
        common->Warning("Q4BSE: decal material not found: %s", pt.material.c_str());
        return;
    }

    idVec2 size(16.0f, 16.0f);
    SampleVec2Domain(FindDomain(pt.start, "size"), size, g_m3Impact.random);
    float decalSize = idMath::Fabs(size.x);
    if (idMath::Fabs(size.y) > decalSize) decalSize = idMath::Fabs(size.y);
    if (decalSize < 1.0f) decalSize = 1.0f;

    idVec3 normal = g_m3Impact.axis[0];
    if (normal.LengthSqr() <= M3_EPSILON) normal.Set(1.0f, 0.0f, 0.0f);
    normal.NormalizeFast();

    gameLocal.ProjectDecal(g_m3Impact.origin, -normal, 8.0f, true,
                           decalSize, pt.material.c_str());
}

static int SampleSpawnerCount'''
impact = replace_regex_once(impact, decal_pattern, decal_repl, "ProjectDecalSegment", re.S)

# Constant attached spawners loop their authored particle life.
render_age_old = '''    const float age = elapsedSec - p.birthSec;
    if (age < 0.0f || age >= p.durationSec) return false;
    const float life = Clamp01(age / p.durationSec);'''
render_age_new = '''    float age = elapsedSec - p.birthSec;
    if (age < 0.0f) return false;
    if (g_m3Impact.attached && p.segment->constant) {
        if (p.durationSec > M3_EPSILON) age = (float)fmod(age, p.durationSec);
    } else if (age >= p.durationSec) {
        return false;
    }
    const float life = Clamp01(age / p.durationSec);'''
impact = replace_once(impact, render_age_old, render_age_new, "constant particle age loop")

# Refactor effect start into an axis-aware internal helper.
start_pattern = r'''static bool StartEffectAt\(const q4bse::Effect\* effect, const char\* effectPath,\n\s+const idVec3& origin, const idVec3& normal\) \{.*?\n\}\n\nstatic bool AnyEmitterActive'''
start_repl = r'''static bool StartEffectAtAxis(const q4bse::Effect* effect, const char* effectPath,
                              const idVec3& origin, const idMat3& axis,
                              idEntity* attachedEntity) {
    if (!effect || !gameRenderWorld || !renderModelManager) return false;
    if ((int)g_m3Impacts.size() >= M3_MAX_ACTIVE_EFFECTS) {
        g_m3CurrentImpact = g_m3Impacts.front();
        FreeImpact();
        delete g_m3Impacts.front();
        g_m3Impacts.erase(g_m3Impacts.begin());
        g_m3CurrentImpact = NULL;
    }

    M3ImpactInstance* instance = new M3ImpactInstance();
    g_m3CurrentImpact = instance;
    g_m3Impact.active = true;
    g_m3Impact.effect = effect;
    g_m3Impact.effectPath = effectPath ? effectPath : "<unnamed>";
    g_m3Impact.serial = ++g_m3NextSerial;
    g_m3Impact.attached = attachedEntity != NULL;
    g_m3Impact.attachedEntity = attachedEntity;
    g_m3Impact.origin = origin;
    g_m3Impact.axis = axis;
    g_m3Impact.startTimeMS = gameLocal.time;
    g_m3Impact.random = M3Random(((unsigned int)gameLocal.time * 1664525u) ^
                                 g_m3Impact.serial ^ 0x51ed270bu);
    g_m3Impact.model = renderModelManager->AllocModel();
    if (!g_m3Impact.model) {
        delete instance;
        g_m3CurrentImpact = NULL;
        return false;
    }

    StartAllSegments();
    ServiceEmitters(0.0f);

    memset(&g_m3Impact.renderEntity, 0, sizeof(g_m3Impact.renderEntity));
    g_m3Impact.renderEntity.hModel = g_m3Impact.model;
    g_m3Impact.renderEntity.origin = vec3_origin;
    g_m3Impact.renderEntity.axis = mat3_identity;
    g_m3Impact.renderEntity.noShadow = true;
    g_m3Impact.renderEntity.noSelfShadow = true;
    g_m3Impact.renderEntity.forceUpdate = 1;
    g_m3Impact.renderEntity.shaderParms[SHADERPARM_RED] = 1.0f;
    g_m3Impact.renderEntity.shaderParms[SHADERPARM_GREEN] = 1.0f;
    g_m3Impact.renderEntity.shaderParms[SHADERPARM_BLUE] = 1.0f;
    g_m3Impact.renderEntity.shaderParms[SHADERPARM_ALPHA] = 1.0f;

    RebuildImpactModel(0.0f);
    g_m3Impact.entityHandle = gameRenderWorld->AddEntityDef(&g_m3Impact.renderEntity);
    if (g_m3Impact.entityHandle < 0) {
        FreeImpact();
        delete instance;
        g_m3CurrentImpact = NULL;
        return false;
    }

    g_m3Impacts.push_back(instance);
    g_m3CurrentImpact = NULL;
    return true;
}

static bool StartEffectAt(const q4bse::Effect* effect, const char* effectPath,
                          const idVec3& origin, const idVec3& normal) {
    idVec3 n = normal;
    if (n.LengthSqr() <= M3_EPSILON) n.Set(1.0f, 0.0f, 0.0f);
    n.NormalizeFast();
    return StartEffectAtAxis(effect, effectPath, origin, n.ToMat3(), NULL);
}

static bool AnyEmitterActive'''
impact = replace_regex_once(impact, start_pattern, start_repl, "StartEffectAt refactor", re.S)

impact = replace_once(impact,
    "        if (elapsedSec >= p.birthSec && elapsedSec < p.birthSec + p.durationSec) return true;",
    '''        if (g_m3Impact.attached && p.segment && p.segment->constant && elapsedSec >= p.birthSec) return true;
        if (elapsedSec >= p.birthSec && elapsedSec < p.birthSec + p.durationSec) return true;''',
    "AnyParticleAlive constant handling")

# Public axis/attachment API.
public_old = '''bool Q4BSE_PlayEffect(const char* fxPath, const idVec3& origin, const idVec3& normal) {
    if (!g_m3Initialized || !gameRenderWorld || !fxPath || !fxPath[0]) return false;
    M3CachedEffect* cached = GetOrLoadEffect(fxPath);
    if (!cached) return false;
    return StartEffectAt(&cached->effect, cached->path.c_str(), origin, normal);
}

int Q4BSE_ActiveEffectCount(void) {
    return (int)g_m3Impacts.size();
}'''
public_new = '''bool Q4BSE_PlayEffect(const char* fxPath, const idVec3& origin, const idVec3& normal) {
    if (!g_m3Initialized || !gameRenderWorld || !fxPath || !fxPath[0]) return false;
    M3CachedEffect* cached = GetOrLoadEffect(fxPath);
    if (!cached) return false;
    return StartEffectAt(&cached->effect, cached->path.c_str(), origin, normal);
}

bool Q4BSE_PlayEffectAxis(const char* fxPath, const idVec3& origin, const idMat3& axis) {
    if (!g_m3Initialized || !gameRenderWorld || !fxPath || !fxPath[0]) return false;
    M3CachedEffect* cached = GetOrLoadEffect(fxPath);
    if (!cached) return false;
    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), origin, axis, NULL);
}

bool Q4BSE_AttachEffectToEntity(const char* fxPath, idEntity* entity) {
    if (!g_m3Initialized || !gameRenderWorld || !fxPath || !fxPath[0] || !entity) return false;
    M3CachedEffect* cached = GetOrLoadEffect(fxPath);
    if (!cached) return false;

    const idVec3 origin = entity->GetPhysics()->GetOrigin();
    idVec3 forward = entity->GetPhysics()->GetLinearVelocity();
    idMat3 axis;
    if (forward.LengthSqr() > M3_EPSILON) {
        forward.NormalizeFast();
        axis = forward.ToMat3();
    } else {
        axis = entity->GetPhysics()->GetAxis();
    }
    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), origin, axis, entity);
}

void Q4BSE_StopEntityEffects(idEntity* entity) {
    if (!entity) return;
    for (size_t i = 0; i < g_m3Impacts.size();) {
        M3ImpactInstance* instance = g_m3Impacts[i];
        if (instance->attached && instance->attachedEntity.GetEntity() == entity) {
            g_m3CurrentImpact = instance;
            FreeImpact();
            delete instance;
            g_m3Impacts.erase(g_m3Impacts.begin() + i);
            continue;
        }
        ++i;
    }
    g_m3CurrentImpact = NULL;
}

int Q4BSE_ActiveEffectCount(void) {
    return (int)g_m3Impacts.size();
}'''
impact = replace_once(impact, public_old, public_new, "public gameplay API implementation")

# Frame service.
frame_pattern = r'''void Q4BSE_M3_Frame\(int gameTimeMS\) \{.*?\n\}'''
frame_new = r'''void Q4BSE_M3_Frame(int gameTimeMS) {
    (void)gameTimeMS;
    for (size_t i = 0; i < g_m3Impacts.size();) {
        g_m3CurrentImpact = g_m3Impacts[i];

        if (g_m3Impact.attached) {
            idEntity* attached = g_m3Impact.attachedEntity.GetEntity();
            if (!attached) {
                FreeImpact();
                delete g_m3Impacts[i];
                g_m3Impacts.erase(g_m3Impacts.begin() + i);
                continue;
            }

            g_m3Impact.origin = attached->GetPhysics()->GetOrigin();
            idVec3 forward = attached->GetPhysics()->GetLinearVelocity();
            if (forward.LengthSqr() > M3_EPSILON) {
                forward.NormalizeFast();
                g_m3Impact.axis = forward.ToMat3();
            }
        }

        const float elapsedSec = (gameLocal.time - g_m3Impact.startTimeMS) * 0.001f;
        ServiceEmitters(elapsedSec);
        RebuildImpactModel(elapsedSec);
        if (g_m3Impact.entityHandle >= 0) {
            gameRenderWorld->UpdateEntityDef(g_m3Impact.entityHandle, &g_m3Impact.renderEntity);
        }

        if (g_m3Impact.attached || AnyEmitterActive() || AnyParticleAlive(elapsedSec)) {
            ++i;
            continue;
        }

        FreeImpact();
        delete g_m3Impacts[i];
        g_m3Impacts.erase(g_m3Impacts.begin() + i);
    }
    g_m3CurrentImpact = NULL;
}'''
impact = replace_regex_once(impact, frame_pattern, frame_new, "Q4BSE_M3_Frame", re.S)

# Projectile lifecycle.
launch_anchor = '''\tUpdateVisuals();

\tstate = LAUNCHED;'''
launch_new = '''\tUpdateVisuals();

\tstate = LAUNCHED;

\tconst char *q4bseFlyFx = spawnArgs.GetString( "fx_fly" );
\tif ( q4bseFlyFx && *q4bseFlyFx ) {
\t\tQ4BSE_AttachEffectToEntity( q4bseFlyFx, this );
\t}'''
projectile = replace_once(projectile, launch_anchor, launch_new, "projectile fx_fly launch hook")

projectile = replace_once(projectile,
    '''idProjectile::~idProjectile() {
\tStopSound( SND_CHANNEL_ANY, false );''',
    '''idProjectile::~idProjectile() {
\tQ4BSE_StopEntityEffects( this );
\tStopSound( SND_CHANNEL_ANY, false );''',
    "projectile destructor FX cleanup")

projectile = replace_once(projectile,
    '''\tSetOrigin( collision.endpos );
\tSetAxis( collision.endAxis );''',
    '''\tQ4BSE_StopEntityEffects( this );

\tSetOrigin( collision.endpos );
\tSetAxis( collision.endAxis );''',
    "projectile collision FX stop")

projectile = replace_once(projectile,
    '''\tif ( state == EXPLODED || state == FIZZLED ) {
\t\treturn;
\t}

\tStopSound( SND_CHANNEL_BODY, false );''',
    '''\tif ( state == EXPLODED || state == FIZZLED ) {
\t\treturn;
\t}

\tQ4BSE_StopEntityEffects( this );
\tStopSound( SND_CHANNEL_BODY, false );''',
    "projectile Fizzle FX stop")

projectile = replace_once(projectile,
    '''\tif ( state == EXPLODED || state == FIZZLED ) {
\t\treturn;
\t}

\t// stop sound
\tStopSound( SND_CHANNEL_BODY2, false );''',
    '''\tif ( state == EXPLODED || state == FIZZLED ) {
\t\treturn;
\t}

\tQ4BSE_StopEntityEffects( this );

\t// stop sound
\tStopSound( SND_CHANNEL_BODY2, false );''',
    "projectile Explode FX stop")

# Weapon muzzle FX.
if '#include "q4bse/Q4BSEImpactM3.h"' not in weapon:
    weapon = replace_once(weapon, '#include "Weapon.h"\n',
                          '#include "Weapon.h"\n#include "q4bse/Q4BSEImpactM3.h"\n',
                          "Weapon BSE include")

flash_joint_old = '''\tbarrelJointView = animator.GetJointHandle( "barrel" );
\tflashJointView = animator.GetJointHandle( "flash" );'''
flash_joint_new = '''\tbarrelJointView = animator.GetJointHandle( "barrel" );
\tconst char *q4FlashJointName = weaponDef->dict.GetString( "joint_view_flash" );
\tflashJointView = animator.GetJointHandle( ( q4FlashJointName && q4FlashJointName[0] ) ? q4FlashJointName : "flash" );'''
weapon = replace_once(weapon, flash_joint_old, flash_joint_new, "Q4 joint_view_flash selection")

muzzle_hook_anchor = '''\t// add some to the kick time, incrementally moving repeat firing weapons back
\tif ( kick_endtime < gameLocal.realClientTime ) {'''
muzzle_hook = '''\t// Raven BSE muzzle FX: compute the declared view flash joint in the exact
\t// source-integrated Q4 presentation space. Position uses foreshortening because
\t// the joint belongs to the foreshortened view model; BSE effect orientation stays
\t// orthonormal so its own authored geometry is not scaled.
\tif ( weaponDef ) {
\t\tconst char *q4MuzzleFx = weaponDef->dict.GetString( "fx_muzzleflash" );
\t\tif ( q4MuzzleFx && *q4MuzzleFx && flashJointView != INVALID_JOINT ) {
\t\t\tidVec3 q4LocalJointOrigin;
\t\t\tidMat3 q4LocalJointAxis;
\t\t\tif ( animator.GetJointTransform( flashJointView, gameLocal.time, q4LocalJointOrigin, q4LocalJointAxis ) ) {
\t\t\t\tidVec3 q4PresentedOrigin = viewWeaponOrigin;
\t\t\t\tidMat3 q4PresentedAxis = viewWeaponAxis;
\t\t\t\tidMat3 q4FxBaseAxis = viewWeaponAxis;

\t\t\t\tconst char *q4ViewStyleName = weaponDef->dict.GetString( "def_viewStyle" );
\t\t\t\tif ( q4ViewStyleName && q4ViewStyleName[0] ) {
\t\t\t\t\tconst idDeclEntityDef *q4ViewStyleDef = gameLocal.FindEntityDef( q4ViewStyleName, false );
\t\t\t\t\tif ( q4ViewStyleDef ) {
\t\t\t\t\t\tconst idVec3 q4ViewOffset = q4ViewStyleDef->dict.GetVector( "viewoffset", "0 0 0" );
\t\t\t\t\t\tconst idAngles q4ViewAngles = q4ViewStyleDef->dict.GetAngles( "viewangles", "0 0 0" );
\t\t\t\t\t\tconst float q4Foreshorten = weaponDef->dict.GetFloat( "foreshorten", "1" );

\t\t\t\t\t\tq4PresentedOrigin += q4ViewOffset * viewWeaponAxis;
\t\t\t\t\t\tq4FxBaseAxis = q4ViewAngles.ToMat3() * viewWeaponAxis;
\t\t\t\t\t\tq4PresentedAxis = q4FxBaseAxis;
\t\t\t\t\t\tq4PresentedAxis[0] *= q4Foreshorten;
\t\t\t\t\t}
\t\t\t\t}

\t\t\t\tconst idVec3 q4FxOrigin = q4LocalJointOrigin * q4PresentedAxis + q4PresentedOrigin;
\t\t\t\tconst idMat3 q4FxAxis = q4LocalJointAxis * q4FxBaseAxis;
\t\t\t\tQ4BSE_PlayEffectAxis( q4MuzzleFx, q4FxOrigin, q4FxAxis );
\t\t\t}
\t\t}
\t}

\t// add some to the kick time, incrementally moving repeat firing weapons back
\tif ( kick_endtime < gameLocal.realClientTime ) {'''
weapon = replace_once(weapon, muzzle_hook_anchor, muzzle_hook, "BSE muzzleflash launch hook")

# Hard gates.
for needle in (
    "localOffset",
    "gameLocal.ProjectDecal(g_m3Impact.origin, -normal",
    "Q4BSE_PlayEffectAxis",
    "Q4BSE_AttachEffectToEntity",
    "Q4BSE_StopEntityEffects",
    "g_m3Impact.attached && p.segment->constant",
    "g_m3Impact.attachedEntity.GetEntity()",
):
    if needle not in impact:
        raise SystemExit(f"ERROR: V14 runtime verification missing: {needle}")

for needle in (
    'spawnArgs.GetString( "fx_fly" )',
    "Q4BSE_AttachEffectToEntity( q4bseFlyFx, this )",
    "Q4BSE_StopEntityEffects( this )",
):
    if needle not in projectile:
        raise SystemExit(f"ERROR: V14 projectile verification missing: {needle}")

for needle in (
    'weaponDef->dict.GetString( "joint_view_flash" )',
    'weaponDef->dict.GetString( "fx_muzzleflash" )',
    "Q4BSE_PlayEffectAxis( q4MuzzleFx",
    "q4PresentedAxis[0] *= q4Foreshorten",
):
    if needle not in weapon:
        raise SystemExit(f"ERROR: V14 weapon verification missing: {needle}")

IMPACT.write_text(impact, encoding="utf-8")
HEADER.write_text(header, encoding="utf-8")
PROJECTILE.write_text(projectile, encoding="utf-8")
WEAPON.write_text(weapon, encoding="utf-8")

print("Q4BSE V14 ATTACHED FX PASS.")
print("  - Raven decal primitive -> Doom 3 native world projection")
print("  - particle start offset domain enabled")
print("  - axis-aware one-shot BSE API enabled")
print("  - entity-attached constant BSE FX enabled")
print("  - projectile fx_fly launches/stops with projectile lifecycle")
print("  - weapon fx_muzzleflash plays from presentation-correct declared flash joint")
print("  - no Doom 3 replacement particle path added")
