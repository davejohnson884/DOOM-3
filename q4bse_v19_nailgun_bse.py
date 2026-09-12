#!/usr/bin/env python3
"""V19: full Raven Nailgun BSE pass on top of cumulative V18.

Adds only generic semantics required by the retail Nailgun FX:
  * particle motion trails (trailType/trailTime/trailCount/trailMaterial)
  * Raven electricity primitive metadata parsing with a compatible line renderer
  * local acceleration sampling
  * persistent projectile trail particles that remain in world space after emission
  * collision detach semantics: kill attached core, let persist trail particles expire
  * per-shot weapon fx_exhaust playback from the two declared steam joints

Existing HyperBlaster and Grenade Launcher behavior is intentionally untouched.
"""
from pathlib import Path
import re, sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PARSER_H = ROOT / "neo" / "game" / "q4bse" / "Q4FxParser.h"
PARSER_CPP = ROOT / "neo" / "game" / "q4bse" / "Q4FxParser.cpp"
IMPACT = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"
WEAPON = ROOT / "neo" / "game" / "Weapon.cpp"

for p in (PARSER_H, PARSER_CPP, IMPACT, WEAPON):
    if not p.exists():
        raise SystemExit(f"ERROR: V19 prerequisite missing: {p}")

def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f"ERROR: V19 expected exactly one {label}, found {hits}")
    return text.replace(old, new, 1)

def replace_regex_once(text, pattern, repl, label, flags=0):
    hits = list(re.finditer(pattern, text, flags))
    if len(hits) != 1:
        raise SystemExit(f"ERROR: V19 expected exactly one regex {label}, found {len(hits)}")
    return re.sub(pattern, repl, text, count=1, flags=flags)

ph = PARSER_H.read_text(encoding="utf-8-sig")
pc = PARSER_CPP.read_text(encoding="utf-8-sig")
impact = IMPACT.read_text(encoding="utf-8-sig")
weapon = WEAPON.read_text(encoding="utf-8-sig")

# -----------------------------------------------------------------------------
# Parser: Nailgun fragment trails + electronics electricity metadata.
# -----------------------------------------------------------------------------
ph = replace_once(
    ph,
    '''    bool generatedLine;\n    bool persist;\n    bool flipNormal;''',
    '''    bool generatedLine;\n    bool persist;\n    bool flipNormal;\n    std::string trailType;\n    Range trailTime;\n    Range trailCount;\n    std::string trailMaterial;\n    int fork;\n    Range jitterRate;\n    std::vector<float> jitterSize;\n    std::string jitterTable;''',
    "Nailgun particle metadata fields")
ph = replace_once(
    ph,
    '''    ParticleTemplate() : generatedNormal(false), generatedOriginNormal(false), generatedLine(false), persist(false), flipNormal(false) {}''',
    '''    ParticleTemplate() : generatedNormal(false), generatedOriginNormal(false), generatedLine(false), persist(false), flipNormal(false), fork(0) {}''',
    "ParticleTemplate V19 constructor")

# Helper to consume Raven nested particle blocks we do not need for rendering (impact bounce metadata).
helper_anchor = '''static ParticleTemplate ParseParticle(TokenStream& ts, const std::string& primitive) {'''
helper_new = '''static void SkipNestedBlock(TokenStream& ts) {
    ts.expect("{");
    int depth = 1;
    while (!ts.eof() && depth > 0) {
        const std::string token = ts.get();
        if (token == "{") ++depth;
        else if (token == "}") --depth;
    }
    if (depth != 0) throw std::runtime_error("unterminated nested block");
}

static ParticleTemplate ParseParticle(TokenStream& ts, const std::string& primitive) {'''
pc = replace_once(pc, helper_anchor, helper_new, "SkipNestedBlock insertion")

pc = replace_once(
    pc,
    '''        else if (k == "generatedLine") p.generatedLine = true;\n        else if (k == "persist") p.persist = true;\n        else if (k == "flipNormal") p.flipNormal = true;\n        else if (k == "start") ParseDomainBlock(ts, p.start);''',
    '''        else if (k == "generatedLine") p.generatedLine = true;\n        else if (k == "persist") p.persist = true;\n        else if (k == "flipNormal") p.flipNormal = true;\n        else if (k == "trailType") p.trailType = ts.get();\n        else if (k == "trailTime") p.trailTime = ParseRange(ts);\n        else if (k == "trailCount") p.trailCount = ParseRange(ts);\n        else if (k == "trailMaterial") p.trailMaterial = ts.get();\n        else if (k == "fork") p.fork = (int)ToFloat(ts.get());\n        else if (k == "jitterRate") p.jitterRate = ParseRange(ts);\n        else if (k == "jitterSize") {\n            p.jitterSize.push_back(ToFloat(ts.get()));\n            while (ts.accept(",")) p.jitterSize.push_back(ToFloat(ts.get()));\n        }\n        else if (k == "jitterTable") p.jitterTable = ts.get();\n        else if (k == "impact") SkipNestedBlock(ts);\n        else if (k == "start") ParseDomainBlock(ts, p.start);''',
    "Nailgun particle keyword parsing")

pc = replace_once(
    pc,
    '''    return s == "sprite" || s == "line" || s == "oriented" || s == "decal" || s == "model" || s == "trail";''',
    '''    return s == "sprite" || s == "line" || s == "oriented" || s == "electricity" || s == "decal" || s == "model" || s == "trail";''',
    "electricity primitive recognition")

# -----------------------------------------------------------------------------
# Runtime particle state: acceleration, per-spawn world frame for persist trails,
# and motion-trail timing/count.
# -----------------------------------------------------------------------------
impact = replace_once(
    impact,
    '''    idVec3 localPosition;\n    idVec3 localOffset;\n    idVec3 localVelocity;\n    idVec3 worldGravityAcceleration;''',
    '''    idVec3 localPosition;\n    idVec3 localOffset;\n    idVec3 localVelocity;\n    idVec3 localAcceleration;\n    idVec3 worldGravityAcceleration;\n    bool worldFrameLocked;\n    idVec3 frameOrigin;\n    idMat3 frameAxis;\n    float trailTimeSec;\n    int trailCount;''',
    "M3Particle Nailgun fields")
impact = replace_once(
    impact,
    '''          localPosition(vec3_origin), localOffset(vec3_origin), localVelocity(vec3_origin), worldGravityAcceleration(vec3_origin),''',
    '''          localPosition(vec3_origin), localOffset(vec3_origin), localVelocity(vec3_origin), localAcceleration(vec3_origin), worldGravityAcceleration(vec3_origin),\n          worldFrameLocked(false), frameOrigin(vec3_origin), frameAxis(mat3_identity), trailTimeSec(0.0f), trailCount(0),''',
    "M3Particle Nailgun constructor")

impact = replace_once(
    impact,
    '''    if (pt.primitive != "sprite" && pt.primitive != "line" && pt.primitive != "oriented") return false;''',
    '''    if (pt.primitive != "sprite" && pt.primitive != "line" && pt.primitive != "oriented" && pt.primitive != "electricity") return false;''',
    "electricity runtime primitive gate")

impact = replace_once(
    impact,
    '''    SampleVec3Domain(FindDomain(pt.start, "offset"), p.localOffset, g_m3Impact.random, NULL);\n    SampleVec3Domain(FindDomain(pt.start, "velocity"), p.localVelocity, g_m3Impact.random, NULL);\n    const bool transformByNormal = pt.generatedOriginNormal || pt.generatedNormal;\n    if (transformByNormal) p.localVelocity = generatedNormal.ToMat3() * p.localVelocity;\n    if (pt.flipNormal) p.localVelocity = -p.localVelocity;''',
    '''    SampleVec3Domain(FindDomain(pt.start, "offset"), p.localOffset, g_m3Impact.random, NULL);\n    SampleVec3Domain(FindDomain(pt.start, "velocity"), p.localVelocity, g_m3Impact.random, NULL);\n    SampleVec3Domain(FindDomain(pt.start, "acceleration"), p.localAcceleration, g_m3Impact.random, NULL);\n    const bool transformByNormal = pt.generatedOriginNormal || pt.generatedNormal;\n    if (transformByNormal) {\n        const idMat3 normalAxis = generatedNormal.ToMat3();\n        p.localVelocity = normalAxis * p.localVelocity;\n        p.localAcceleration = normalAxis * p.localAcceleration;\n    }\n    if (pt.flipNormal) {\n        p.localVelocity = -p.localVelocity;\n        p.localAcceleration = -p.localAcceleration;\n    }\n\n    // Raven persist particles emitted by an attached projectile are born into\n    // world space. The core remains attached; the smoke wake does not get dragged\n    // forward with the moving nail.\n    p.worldFrameLocked = g_m3Impact.attachedPersistent && pt.persist;\n    if (p.worldFrameLocked) {\n        p.frameOrigin = g_m3Impact.origin;\n        p.frameAxis = g_m3Impact.axis;\n    }\n    p.trailTimeSec = SampleRange(pt.trailTime, 0.0f, g_m3Impact.random);\n    p.trailCount = idMath::FtoiFast(idMath::Ceil(SampleRange(pt.trailCount, 0.0f, g_m3Impact.random)));\n    if (p.trailCount < 0) p.trailCount = 0;''',
    "Nailgun acceleration/persist/trail sampling")

impact = replace_once(
    impact,
    '''    if (pt.primitive == "line") {\n        float a = p.sizeStart.x, b = p.sizeEnd.x;''',
    '''    if (pt.primitive == "line" || pt.primitive == "electricity") {\n        float a = p.sizeStart.x, b = p.sizeEnd.x;''',
    "line/electricity scalar size sampling")

# Replace world-position helper and add frame helpers.
impact = replace_regex_once(
    impact,
    r'''static idVec3 ParticleWorldPosition\(const M3Particle& p, float ageSec\) \{.*?\n\}''',
    r'''static const idMat3& ParticleFrameAxis(const M3Particle& p) {
    return p.worldFrameLocked ? p.frameAxis : g_m3Impact.axis;
}

static idVec3 ParticleFrameOrigin(const M3Particle& p) {
    return p.worldFrameLocked ? p.frameOrigin : g_m3Impact.origin;
}

static idVec3 ParticleWorldPosition(const M3Particle& p, float ageSec) {
    const idVec3 local = p.localPosition + p.localOffset + p.localVelocity * ageSec +
                         p.localAcceleration * (0.5f * ageSec * ageSec);
    idVec3 world = ParticleFrameOrigin(p) + ParticleFrameAxis(p) * local;
    world += p.worldGravityAcceleration * (0.5f * ageSec * ageSec);
    return world;
}''',
    "ParticleWorldPosition V19",
    re.S)

# Add material-override helper used by Raven motion trails.
add_surface_anchor = '''static bool RenderParticle(idRenderModel* model, const M3Particle& p, float elapsedSec,'''
add_surface_helper = '''static bool AddSurfaceMaterial(idRenderModel* model, const q4bse::ParticleTemplate& original,
                               const char* materialName, bool additive,
                               const idVec3* points, const float* st, int pointCount,
                               const int* indexes, int indexCount, const idVec4& color) {
    if (!materialName || !materialName[0]) return false;
    q4bse::ParticleTemplate temp = original;
    temp.material = materialName;
    if (additive) temp.blend = "add";
    return AddSurface(model, temp, points, st, pointCount, indexes, indexCount, color);
}

static bool RenderParticle(idRenderModel* model, const M3Particle& p, float elapsedSec,'''
impact = replace_once(impact, add_surface_anchor, add_surface_helper, "trail AddSurface helper")

# Replace line renderer with frame-aware line/electricity + motion trail.
line_pattern = r'''    if \(pt\.primitive == "line"\) \{.*?\n    \}\n    if \(pt\.primitive == "oriented"\) \{'''
line_repl = r'''    if (pt.primitive == "line" || pt.primitive == "electricity") {
        const float width = EvalFloat(p.sizeStart.x, p.sizeEnd.x, FindDomain(pt.motion, "size"), life);
        const idVec3 localLength = EvalVec3(p.lengthStart, p.lengthEnd, FindDomain(pt.motion, "length"), life);
        const idVec3 length = ParticleFrameAxis(p) * localLength;
        const idVec3 end = worldPos + length;
        const idVec3 toView = viewOrigin - (worldPos + length * 0.5f);
        idVec3 side = length.Cross(toView);
        if (side.LengthSqr() > M3_EPSILON) side.NormalizeFast(); else side = viewAxis[1];
        side *= idMath::Fabs(width);
        idVec3 points[4] = { worldPos + side, worldPos - side, end - side, end + side };
        bool rendered = AddSurface(model, pt, points, st, 4, idx, 6, color);

        // Q4 motion trails used by Nailgun fragments/glass sparks. Draw a camera-facing
        // ribbon between the current particle position and its authored trail-time history.
        if (!pt.trailMaterial.empty() && !idStr::Icmp(pt.trailType.c_str(), "motion") && p.trailTimeSec > M3_EPSILON) {
            float oldAge = age - p.trailTimeSec;
            if (oldAge < 0.0f) oldAge = 0.0f;
            const idVec3 oldPos = ParticleWorldPosition(p, oldAge);
            idVec3 motion = worldPos - oldPos;
            if (motion.LengthSqr() > M3_EPSILON) {
                const idVec3 mid = (worldPos + oldPos) * 0.5f;
                idVec3 trailSide = motion.Cross(viewOrigin - mid);
                if (trailSide.LengthSqr() > M3_EPSILON) trailSide.NormalizeFast();
                else trailSide = viewAxis[1];
                const float trailWidth = idMath::Fabs(width) * 0.65f;
                trailSide *= trailWidth > 0.08f ? trailWidth : 0.08f;
                idVec3 trailPoints[4] = { oldPos + trailSide, oldPos - trailSide,
                                          worldPos - trailSide, worldPos + trailSide };
                rendered = AddSurfaceMaterial(model, pt, pt.trailMaterial.c_str(), true,
                                              trailPoints, st, 4, idx, 6, color) || rendered;
            }
        }
        return rendered;
    }
    if (pt.primitive == "oriented") {'''
impact = replace_regex_once(impact, line_pattern, line_repl, "frame-aware Nailgun line renderer", re.S)
impact = replace_once(
    impact,
    '''        const idVec3 right = g_m3Impact.axis * (localRotation[1] * -size.x);\n        const idVec3 up = g_m3Impact.axis * (localRotation[2] * size.y);''',
    '''        const idVec3 right = ParticleFrameAxis(p) * (localRotation[1] * -size.x);\n        const idVec3 up = ParticleFrameAxis(p) * (localRotation[2] * size.y);''',
    "frame-aware oriented renderer")

# Collision cleanup: detach and preserve only Raven persist particles (Nailgun smoke wake).
stop_pattern = r'''void Q4BSE_StopEntityEffects\(idEntity\* entity\) \{.*?\n\}\n\nint Q4BSE_ActiveEffectCount'''
stop_repl = r'''void Q4BSE_StopEntityEffects(idEntity* entity) {
    if (!entity) return;
    for (size_t i = 0; i < g_m3Impacts.size();) {
        M3ImpactInstance* instance = g_m3Impacts[i];
        if (instance->attached && instance->attachedEntity.GetEntity() == entity) {
            g_m3CurrentImpact = instance;

            std::vector<M3Particle> survivors;
            for (size_t p = 0; p < instance->particles.size(); ++p) {
                const M3Particle& particle = instance->particles[p];
                if (particle.segment && particle.segment->hasParticle && particle.segment->particle.persist) {
                    survivors.push_back(particle);
                }
            }

            if (!survivors.empty()) {
                instance->particles.swap(survivors);
                for (size_t e = 0; e < instance->emitters.size(); ++e) instance->emitters[e].active = false;
                instance->attached = false;
                instance->attachedPersistent = false;
                instance->attachedLocalTransform = false;
                instance->attachedEntity = NULL;
                ++i;
                continue;
            }

            FreeImpact();
            delete instance;
            g_m3Impacts.erase(g_m3Impacts.begin() + i);
            continue;
        }
        ++i;
    }
    g_m3CurrentImpact = NULL;
}

int Q4BSE_ActiveEffectCount'''
impact = replace_regex_once(impact, stop_pattern, stop_repl, "persist-aware StopEntityEffects", re.S)

# -----------------------------------------------------------------------------
# Weapon exhaust: play the exact Raven exhaust.fx from both Q4 steam joints each shot.
# Generic and key-driven; weapons without fx_exhaust remain untouched.
# -----------------------------------------------------------------------------
kick_anchor = '''\n\t// add some to the kick time, incrementally moving repeat firing weapons back\n\tif ( kick_endtime < gameLocal.realClientTime ) {'''
exhaust_hook = '''
	// Raven BSE auxiliary muzzle exhaust. Nailgun declares two steam joints; the
	// content DEF chooses those joints, so this remains generic and opt-in.
	if ( weaponDef ) {
		const char *q4ExhaustFx = weaponDef->dict.GetString( "fx_exhaust" );
		if ( q4ExhaustFx && *q4ExhaustFx ) {
			const char *q4SteamKeys[2] = { "joint_view_steamRight", "joint_view_steamLeft" };
			for ( int q4SteamIndex = 0; q4SteamIndex < 2; ++q4SteamIndex ) {
				const char *q4SteamJointName = weaponDef->dict.GetString( q4SteamKeys[q4SteamIndex] );
				if ( !q4SteamJointName || !q4SteamJointName[0] ) continue;
				const jointHandle_t q4SteamJoint = animator.GetJointHandle( q4SteamJointName );
				if ( q4SteamJoint == INVALID_JOINT ) continue;

				idVec3 q4LocalJointOrigin;
				idMat3 q4LocalJointAxis;
				if ( !animator.GetJointTransform( q4SteamJoint, gameLocal.time, q4LocalJointOrigin, q4LocalJointAxis ) ) continue;

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
				const idVec3 q4FxOrigin = q4LocalJointOrigin * q4PresentedAxis + q4PresentedOrigin;
				const idMat3 q4FxAxis = q4LocalJointAxis * q4FxBaseAxis;
				Q4BSE_AttachEffectToEntityTransform( q4ExhaustFx, this, q4FxOrigin, q4FxAxis );
			}
		}
	}

	// add some to the kick time, incrementally moving repeat firing weapons back
	if ( kick_endtime < gameLocal.realClientTime ) {'''
weapon = replace_once(weapon, kick_anchor, "\n" + exhaust_hook, "Nailgun dual exhaust hook")

# Hard gates.
for needle in (
    "trailType", "trailMaterial", "worldFrameLocked", "localAcceleration",
    'pt.primitive == "electricity"', "ParticleFrameAxis", "survivors",
):
    if needle not in impact and needle not in pc and needle not in ph:
        raise SystemExit(f"ERROR: V19 verification missing: {needle}")
for needle in (
    'weaponDef->dict.GetString( "fx_exhaust" )',
    '"joint_view_steamRight"', '"joint_view_steamLeft"',
    "Q4BSE_AttachEffectToEntityTransform( q4ExhaustFx",
):
    if needle not in weapon:
        raise SystemExit(f"ERROR: V19 weapon verification missing: {needle}")

PARSER_H.write_text(ph, encoding="utf-8")
PARSER_CPP.write_text(pc, encoding="utf-8")
IMPACT.write_text(impact, encoding="utf-8")
WEAPON.write_text(weapon, encoding="utf-8")

print("Q4BSE V19 NAILGUN BSE PASS.")
print("  - Raven Nailgun motion-trail metadata parsed/rendered")
print("  - Raven electricity primitive accepted")
print("  - start acceleration sampled")
print("  - projectile persist smoke born into world space")
print("  - collision preserves trail tail while removing attached core")
print("  - dual steam-nozzle fx_exhaust playback enabled")
