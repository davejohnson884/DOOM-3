#!/usr/bin/env python3
'''V19C / user-facing V21: Dark Matter in-gun core renderer parity.

Runs after V19B but deliberately restores the accepted V14 core lifecycle.
FX declarations are untouched.  The main change is a Q4/OpenQ4-style
Electricity renderer for the in-gun core/core_start effects.
'''
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PARSER_H = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4FxParser.h'
PARSER_CPP = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4FxParser.cpp'
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
WEAPON = ROOT / 'neo' / 'game' / 'Weapon.cpp'

for p in (PARSER_H, PARSER_CPP, IMPACT, WEAPON):
    if not p.exists():
        raise SystemExit(f'ERROR: V19C prerequisite missing: {p}')

ph = PARSER_H.read_text(encoding='utf-8-sig')
pc = PARSER_CPP.read_text(encoding='utf-8-sig')
impact = IMPACT.read_text(encoding='utf-8-sig')
weapon = WEAPON.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V19C expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# PARSER: retain Raven electricity metadata instead of discarding it.
# ---------------------------------------------------------------------------
ph = replace_once(
    ph,
    '''    std::vector<float> jitterSize;
    std::string jitterTable;
    bool generatedNormal;''',
    '''    std::vector<float> jitterSize;
    std::string jitterTable;
    int forkCount;
    float jitterRate;
    bool generatedNormal;''',
    'electricity parser fields')

ph = replace_once(
    ph,
    '''    ParticleTemplate() : generatedNormal(false), generatedOriginNormal(false), generatedLine(false), persist(false), flipNormal(false) {}''',
    '''    ParticleTemplate() : forkCount(0), jitterRate(0.0f), generatedNormal(false), generatedOriginNormal(false), generatedLine(false), persist(false), flipNormal(false) {}''',
    'electricity parser defaults')

pc = replace_once(
    pc,
    '''        else if (k == "fork") { (void)ToFloat(ts.get()); }
        else if (k == "jitterRate") { (void)ToFloat(ts.get()); }''',
    '''        else if (k == "fork") {
            p.forkCount = (int)ToFloat(ts.get());
            if (p.forkCount < 0) p.forkCount = 0;
            if (p.forkCount > 16) p.forkCount = 16;
        }
        else if (k == "jitterRate") {
            p.jitterRate = ToFloat(ts.get());
            if (p.jitterRate < 0.0f) p.jitterRate = 0.0f;
        }''',
    'electricity metadata parsing')

# ---------------------------------------------------------------------------
# PARTICLE STATE: each bolt gets a stable base seed; jitterRate decides when
# that seed is advanced.  Core jitterRate=0 therefore re-seeds every frame,
# which is a key Raven behavior missing from the old approximation.
# ---------------------------------------------------------------------------
impact = replace_once(
    impact,
    '''    idVec3 lengthStart;
    idVec3 lengthEnd;
    M3Particle()''',
    '''    idVec3 lengthStart;
    idVec3 lengthEnd;
    unsigned int q4ElectricitySeed;
    M3Particle()''',
    'electricity particle seed field')

impact = replace_once(
    impact,
    '''          fadeStart(1.0f), fadeEnd(0.0f), rotateStart(vec3_origin), rotateEnd(vec3_origin),
          lengthStart(vec3_origin), lengthEnd(vec3_origin) {}''',
    '''          fadeStart(1.0f), fadeEnd(0.0f), rotateStart(vec3_origin), rotateEnd(vec3_origin),
          lengthStart(vec3_origin), lengthEnd(vec3_origin), q4ElectricitySeed(0u) {}''',
    'electricity particle seed constructor')

impact = replace_once(
    impact,
    '''    p.durationSec = SampleRange(pt.duration, 0.1f, g_m3Impact.random);
    if (p.durationSec < 0.002f) p.durationSec = 0.002f;''',
    '''    p.durationSec = SampleRange(pt.duration, 0.1f, g_m3Impact.random);
    if (p.durationSec < 0.002f) p.durationSec = 0.002f;
    p.q4ElectricitySeed = g_m3Impact.random.NextU32();''',
    'electricity particle base seed')

# ---------------------------------------------------------------------------
# Raven/OpenQ4 electricity construction, scoped only to the Dark Matter
# view-local core path so other accepted weapon/projectile effects are untouched.
# ---------------------------------------------------------------------------
render_anchor = '''static bool RenderParticle(idRenderModel* model, const M3Particle& p, float elapsedSec,
                           const idVec3& viewOrigin, const idMat3& viewAxis) {'''

helpers = r'''struct M3Q4ElectricityPoint {
    idVec3 position;
    float s;
    M3Q4ElectricityPoint(const idVec3& p, float tc) : position(p), s(tc) {}
};

static int Q4ElectricityBoltCount(float length) {
    int count = (int)ceilf(length * 0.0625f);
    if (count < 3) count = 3;
    if (count > 200) count = 200;
    return count;
}

static float Q4ElectricityJitterWeight(const q4bse::ParticleTemplate& pt, float fraction) {
    fraction = Clamp01(fraction);
    if (!pt.jitterTable.empty()) {
        std::string error;
        M3EnvelopeTable* table = FindEnvelopeTable(pt.jitterTable.c_str(), error);
        if (table) return TableLookup(*table, fraction);

        // Raven defaults electricity to halfsintable. Quake 4 ships that table,
        // while Doom 3 content may not, so preserve the curve in runtime.
        if (!idStr::Icmp(pt.jitterTable.c_str(), "halfsintable")) {
            return idMath::Sin(0.5f * M3_TWO_PI * fraction);
        }
    }
    return idMath::Sin(0.5f * M3_TWO_PI * fraction);
}

static void Q4ElectricityApplyShape(M3Random& random,
                                    idVec3 start, idVec3 end, int count,
                                    float startFraction, float endFraction,
                                    float branchBase, float branchStep,
                                    std::vector<M3Q4ElectricityPoint>& points) {
    // Same tail-recursive subdivision as Raven rvElectricityParticle::ApplyShape.
    while (count >= 1) {
        const float bendA = random.Range(0.05f, 0.09f);
        const float bendB = random.Range(0.05f, 0.09f);
        const float shape = random.Range(0.56f, 0.76f);

        idVec3 forward = end - start;
        const float length = forward.Length() * 0.70f;
        if (length <= M3_EPSILON) break;
        forward.NormalizeFast();

        idVec3 left;
        const float planarLenSqr = forward.x * forward.x + forward.y * forward.y;
        if (planarLenSqr <= M3_EPSILON) {
            left.Set(1.0f, 0.0f, 0.0f);
        } else {
            const float invPlanarLen = idMath::InvSqrt(planarLenSqr);
            left.Set(-forward.y * invPlanarLen, forward.x * invPlanarLen, 0.0f);
        }
        const idVec3 down = left.Cross(forward);

        const float leftOffset1 = random.Range(-bendB - 0.02f, 0.02f - bendB) * length;
        const idVec3 point1 = start * shape + end * (1.0f - shape) +
            left * leftOffset1 + down * random.Range(0.23f, 0.43f) * length;

        const float t2 = random.Range(0.23f, 0.43f);
        const float leftOffset2 = random.Range(-bendA - 0.02f, 0.02f - bendA) * length;
        const idVec3 point2 = start * t2 + end * (1.0f - t2) +
            left * leftOffset2 + down * random.Range(-0.02f, 0.02f) * length;

        const float mid0 = startFraction * 0.6666667f + endFraction * 0.3333333f;
        const float mid1 = startFraction * 0.3333333f + endFraction * 0.6666667f;

        Q4ElectricityApplyShape(random, start, point1, count - 1,
                                startFraction, mid0, branchBase, branchStep, points);
        Q4ElectricityApplyShape(random, point1, point2, count - 1,
                                mid0, mid1, branchBase, branchStep, points);

        --count;
        start = point2;
        startFraction = mid1;
    }

    points.push_back(M3Q4ElectricityPoint(start, branchBase + startFraction * branchStep));
}

static bool RenderQ4DarkMatterElectricity(idRenderModel* model,
                                          const M3Particle& p,
                                          const q4bse::ParticleTemplate& pt,
                                          float elapsedSec, float age, float life,
                                          const idVec3& worldPos,
                                          const idVec3& viewOrigin,
                                          const idMat3& viewAxis,
                                          const idVec4& color) {
    const float width = idMath::Fabs(EvalFloat(p.sizeStart.x, p.sizeEnd.x,
                                      FindDomain(pt.motion, "size"), life));
    const idVec3 length = EvalVec3(p.lengthStart, p.lengthEnd,
                                   FindDomain(pt.motion, "length"), life);
    const float mainLength = length.Length();
    if (mainLength < 0.1f || width <= M3_EPSILON) return false;

    // jitterRate=0 on the Dark Matter core means a new shape every frame.
    unsigned int jitterEpoch = 0u;
    if (pt.jitterRate <= M3_EPSILON) {
        jitterEpoch = (unsigned int)gameLocal.time;
    } else {
        jitterEpoch = (unsigned int)floorf(age / pt.jitterRate);
    }
    M3Random random(p.q4ElectricitySeed ^ (jitterEpoch * 0x9e3779b9u) ^ 0x85ebca6bu);

    const int boltCount = Q4ElectricityBoltCount(mainLength);
    const float step = 1.0f / (float)boltCount;

    idVec3 forward = length;
    forward.NormalizeFast();
    idVec3 left;
    const float planarLenSqr = forward.x * forward.x + forward.y * forward.y;
    if (planarLenSqr <= M3_EPSILON) {
        left.Set(1.0f, 0.0f, 0.0f);
    } else {
        const float invPlanarLen = idMath::InvSqrt(planarLenSqr);
        left.Set(-forward.y * invPlanarLen, forward.x * invPlanarLen, 0.0f);
    }
    const idVec3 down = left.Cross(forward);

    float jitterX = 0.0f, jitterY = 0.0f, jitterZ = 0.0f;
    if (!pt.jitterSize.empty()) {
        jitterX = idMath::Fabs(pt.jitterSize[0]);
        jitterY = idMath::Fabs(pt.jitterSize.size() > 1 ? pt.jitterSize[1] : pt.jitterSize[0]);
        jitterZ = idMath::Fabs(pt.jitterSize.size() > 2 ? pt.jitterSize[2] : pt.jitterSize[0]);
    }

    const idVec3 endPos = worldPos + length;
    std::vector<M3Q4ElectricityPoint> centers;
    centers.reserve((size_t)boltCount * 10u + 1u);

    float fraction = step;
    idVec3 old = worldPos;
    idVec3 current = worldPos;
    idVec3 accumulatedOffset(vec3_origin);

    while (true) {
        bool finalStep = false;
        if (1.0f - step * 0.5f <= fraction) {
            fraction = 1.0f;
            finalStep = true;
        }

        accumulatedOffset += forward * random.Range(-jitterX, jitterX);
        accumulatedOffset += left * random.Range(-jitterY, jitterY);
        accumulatedOffset += down * random.Range(-jitterZ, jitterZ);

        const float noise = Q4ElectricityJitterWeight(pt, fraction);
        current = worldPos + (endPos - worldPos) * fraction + accumulatedOffset * noise;

        const float branchBase = fraction - step;
        Q4ElectricityApplyShape(random, old, current, 2, 0.0f, 1.0f,
                                branchBase, step, centers);

        old = current;
        if (finalStep) break;
        fraction += step;
    }
    centers.push_back(M3Q4ElectricityPoint(current, 1.0f));

    if (centers.size() < 2) return false;

    // Raven uses one ribbon offset from the full bolt length. The old bridge
    // re-oriented every tiny bend and produced the angular "scribble/greeble".
    idVec3 side = length.Cross(viewOrigin);
    if (side.LengthSqr() > M3_EPSILON) side.NormalizeFast();
    else side = viewAxis[1];
    side *= width;

    const int centerCount = (int)centers.size();
    const int pointCount = centerCount * 2;
    const int indexCount = (centerCount - 1) * 6;
    std::vector<idVec3> points((size_t)pointCount);
    std::vector<float> uv((size_t)pointCount * 2u);
    std::vector<int> indexes((size_t)indexCount);

    for (int i = 0; i < centerCount; ++i) {
        points[i * 2 + 0] = centers[i].position + side;
        points[i * 2 + 1] = centers[i].position - side;
        uv[(i * 2 + 0) * 2 + 0] = centers[i].s;
        uv[(i * 2 + 0) * 2 + 1] = 0.0f;
        uv[(i * 2 + 1) * 2 + 0] = centers[i].s;
        uv[(i * 2 + 1) * 2 + 1] = 1.0f;
    }
    for (int i = 0; i < centerCount - 1; ++i) {
        const int v = i * 2;
        const int k = i * 6;
        indexes[k + 0] = v + 0;
        indexes[k + 1] = v + 1;
        indexes[k + 2] = v + 2;
        indexes[k + 3] = v + 1;
        indexes[k + 4] = v + 3;
        indexes[k + 5] = v + 2;
    }

    return AddSurface(model, pt, &points[0], &uv[0], pointCount,
                      &indexes[0], indexCount, color);
}

'''

impact = replace_once(impact, render_anchor, helpers + render_anchor, 'electricity parity helper insertion')

old_electricity = r'''    if (pt.primitive == "electricity") {
        const float width = idMath::Fabs(EvalFloat(p.sizeStart.x, p.sizeEnd.x, FindDomain(pt.motion, "size"), life));
        const idVec3 localLength = EvalVec3(p.lengthStart, p.lengthEnd, FindDomain(pt.motion, "length"), life);
        const idVec3 worldLength = g_m3Impact.q4ViewLocalGeometry ? localLength : (g_m3Impact.axis * localLength);
        const idVec3 end = worldPos + worldLength;
        idVec3 boltDir = end - worldPos;
        const float boltLen = boltDir.Normalize();
        if (boltLen <= M3_EPSILON) return false;

        idVec3 jitterA, jitterB;
        boltDir.NormalVectors(jitterA, jitterB);
        float jitterAmpA = 0.0f;
        float jitterAmpB = 0.0f;
        if (!pt.jitterSize.empty()) {
            jitterAmpA = idMath::Fabs(pt.jitterSize.size() > 1 ? pt.jitterSize[1] : pt.jitterSize[0]);
            jitterAmpB = idMath::Fabs(pt.jitterSize.size() > 2 ? pt.jitterSize[2] : pt.jitterSize[0]);
        }

        enum { Q4_ELEC_STEPS = 6, Q4_ELEC_VERTS = (Q4_ELEC_STEPS + 1) * 2, Q4_ELEC_INDEXES = Q4_ELEC_STEPS * 6 };
        idVec3 centers[Q4_ELEC_STEPS + 1];
        idVec3 points[Q4_ELEC_VERTS];
        float uv[Q4_ELEC_VERTS * 2];
        int indexes[Q4_ELEC_INDEXES];

        const float seed = (float)(p.segmentIndex * 17 + idMath::FtoiFast(p.birthSec * 1000.0f) * 3);
        for (int i = 0; i <= Q4_ELEC_STEPS; ++i) {
            const float t = (float)i / (float)Q4_ELEC_STEPS;
            centers[i] = worldPos + (end - worldPos) * t;
            if (i > 0 && i < Q4_ELEC_STEPS) {
                const float edge = idMath::Sin(idMath::PI * t);
                const float phase = seed * 0.173f + (float)i * 2.417f;
                centers[i] += jitterA * (idMath::Sin(phase) * jitterAmpA * 0.42f * edge);
                centers[i] += jitterB * (idMath::Cos(phase * 1.37f) * jitterAmpB * 0.42f * edge);
            }
        }
        for (int i = 0; i <= Q4_ELEC_STEPS; ++i) {
            idVec3 tangent;
            if (i == 0) tangent = centers[1] - centers[0];
            else if (i == Q4_ELEC_STEPS) tangent = centers[i] - centers[i - 1];
            else tangent = centers[i + 1] - centers[i - 1];
            if (tangent.LengthSqr() > M3_EPSILON) tangent.NormalizeFast(); else tangent = boltDir;
            idVec3 toView = viewOrigin - centers[i];
            idVec3 side = tangent.Cross(toView);
            if (side.LengthSqr() > M3_EPSILON) side.NormalizeFast(); else side = viewAxis[1];
            side *= width;
            points[i * 2 + 0] = centers[i] + side;
            points[i * 2 + 1] = centers[i] - side;
            const float u = (float)i / (float)Q4_ELEC_STEPS;
            uv[(i * 2 + 0) * 2 + 0] = u; uv[(i * 2 + 0) * 2 + 1] = 0.0f;
            uv[(i * 2 + 1) * 2 + 0] = u; uv[(i * 2 + 1) * 2 + 1] = 1.0f;
        }
        for (int i = 0; i < Q4_ELEC_STEPS; ++i) {
            const int v = i * 2;
            const int k = i * 6;
            indexes[k + 0] = v + 0; indexes[k + 1] = v + 1; indexes[k + 2] = v + 3;
            indexes[k + 3] = v + 0; indexes[k + 4] = v + 3; indexes[k + 5] = v + 2;
        }
        return AddSurface(model, pt, points, uv, Q4_ELEC_VERTS, indexes, Q4_ELEC_INDEXES, color);
    }'''

new_electricity = r'''    if (pt.primitive == "electricity") {
        if (g_m3Impact.q4ViewLocalGeometry) {
            return RenderQ4DarkMatterElectricity(model, p, pt, elapsedSec, age, life,
                                                 worldPos, viewOrigin, viewAxis, color);
        }

        // Keep the already-accepted generic/projectile bridge unchanged.
        const float width = idMath::Fabs(EvalFloat(p.sizeStart.x, p.sizeEnd.x, FindDomain(pt.motion, "size"), life));
        const idVec3 localLength = EvalVec3(p.lengthStart, p.lengthEnd, FindDomain(pt.motion, "length"), life);
        const idVec3 worldLength = g_m3Impact.axis * localLength;
        const idVec3 end = worldPos + worldLength;
        idVec3 boltDir = end - worldPos;
        const float boltLen = boltDir.Normalize();
        if (boltLen <= M3_EPSILON) return false;

        idVec3 jitterA, jitterB;
        boltDir.NormalVectors(jitterA, jitterB);
        float jitterAmpA = 0.0f;
        float jitterAmpB = 0.0f;
        if (!pt.jitterSize.empty()) {
            jitterAmpA = idMath::Fabs(pt.jitterSize.size() > 1 ? pt.jitterSize[1] : pt.jitterSize[0]);
            jitterAmpB = idMath::Fabs(pt.jitterSize.size() > 2 ? pt.jitterSize[2] : pt.jitterSize[0]);
        }

        enum { Q4_ELEC_STEPS = 6, Q4_ELEC_VERTS = (Q4_ELEC_STEPS + 1) * 2, Q4_ELEC_INDEXES = Q4_ELEC_STEPS * 6 };
        idVec3 centers[Q4_ELEC_STEPS + 1];
        idVec3 points[Q4_ELEC_VERTS];
        float uv[Q4_ELEC_VERTS * 2];
        int indexes[Q4_ELEC_INDEXES];

        const float seed = (float)(p.segmentIndex * 17 + idMath::FtoiFast(p.birthSec * 1000.0f) * 3);
        for (int i = 0; i <= Q4_ELEC_STEPS; ++i) {
            const float t = (float)i / (float)Q4_ELEC_STEPS;
            centers[i] = worldPos + (end - worldPos) * t;
            if (i > 0 && i < Q4_ELEC_STEPS) {
                const float edge = idMath::Sin(idMath::PI * t);
                const float phase = seed * 0.173f + (float)i * 2.417f;
                centers[i] += jitterA * (idMath::Sin(phase) * jitterAmpA * 0.42f * edge);
                centers[i] += jitterB * (idMath::Cos(phase * 1.37f) * jitterAmpB * 0.42f * edge);
            }
        }
        for (int i = 0; i <= Q4_ELEC_STEPS; ++i) {
            idVec3 tangent;
            if (i == 0) tangent = centers[1] - centers[0];
            else if (i == Q4_ELEC_STEPS) tangent = centers[i] - centers[i - 1];
            else tangent = centers[i + 1] - centers[i - 1];
            if (tangent.LengthSqr() > M3_EPSILON) tangent.NormalizeFast(); else tangent = boltDir;
            idVec3 toView = viewOrigin - centers[i];
            idVec3 side = tangent.Cross(toView);
            if (side.LengthSqr() > M3_EPSILON) side.NormalizeFast(); else side = viewAxis[1];
            side *= width;
            points[i * 2 + 0] = centers[i] + side;
            points[i * 2 + 1] = centers[i] - side;
            const float u = (float)i / (float)Q4_ELEC_STEPS;
            uv[(i * 2 + 0) * 2 + 0] = u; uv[(i * 2 + 0) * 2 + 1] = 0.0f;
            uv[(i * 2 + 1) * 2 + 0] = u; uv[(i * 2 + 1) * 2 + 1] = 1.0f;
        }
        for (int i = 0; i < Q4_ELEC_STEPS; ++i) {
            const int v = i * 2;
            const int k = i * 6;
            indexes[k + 0] = v + 0; indexes[k + 1] = v + 1; indexes[k + 2] = v + 3;
            indexes[k + 3] = v + 0; indexes[k + 4] = v + 3; indexes[k + 5] = v + 2;
        }
        return AddSurface(model, pt, points, uv, Q4_ELEC_VERTS, indexes, Q4_ELEC_INDEXES, color);
    }'''

impact = replace_once(impact, old_electricity, new_electricity, 'Dark Matter native electricity render block')

# ---------------------------------------------------------------------------
# LIFECYCLE: restore the accepted V14 presentation. core_start is lifetime-held
# through reload; on Idle it is cleaned up BEFORE looping core.fx starts.
# ---------------------------------------------------------------------------
weapon = replace_once(
    weapon,
    '''			if ( q4CoreStartFx && q4CoreStartFx[0] ) {
				Q4BSE_AttachEffectToEntityTransform( q4CoreStartFx, this, q4CoreWorldOrigin, q4CoreWorldAxis );
				Q4BSE_SetEntityEffectsViewWeaponMode( this, owner ? owner->entityNumber + 1 : 0 );
			}''',
    '''			if ( q4CoreStartFx && q4CoreStartFx[0] ) {
				// V14-compatible lifetime hold: keep delayed charge segments alive
				// for the full reload, then explicitly clear them at Idle.
				Q4BSE_AttachPersistentEffectToEntityTransform( q4CoreStartFx, this, q4CoreWorldOrigin, q4CoreWorldAxis );
				Q4BSE_SetEntityEffectsViewWeaponMode( this, owner ? owner->entityNumber + 1 : 0 );
			}''',
    'V14 core_start lifetime hold')

old_idle = '''		else if ( q4HaveCoreTransform && q4CoreRequest == 2 ) {
			// V19B presentation handoff: bring the looping idle core online FIRST,
			// then remove only the one-shot recharge effect. This preserves a
			// continuous energized frame-to-frame handoff without allowing the
			// long-lived core_start ring/growth tail to sit on top of idle.
			if ( q4CoreMode != 1 ) {
				Q4BSE_StopEntityEffects( this );
			}
			const char *q4CoreFx = weaponDef->dict.GetString( "fx_core" );
			if ( q4CoreFx && q4CoreFx[0] ) {
				Q4BSE_AttachPersistentEffectToEntityTransform( q4CoreFx, this, q4CoreWorldOrigin, q4CoreWorldAxis );
				Q4BSE_SetEntityEffectsViewWeaponMode( this, owner ? owner->entityNumber + 1 : 0 );
			}

			if ( q4CoreMode == 1 ) {
				const char *q4CoreStartFx = weaponDef->dict.GetString( "fx_core_start" );
				if ( q4CoreStartFx && q4CoreStartFx[0] ) {
					Q4BSE_StopEntityEffectPath( this, q4CoreStartFx );
				}
			}

			if ( q4CoreMode == 0 ) {
				StartSound( "snd_rings", SND_CHANNEL_VOICE, 0, false, NULL );
			}
			q4CoreMode = 2;
			spawnArgs.Set( "_q4_dmg_core_mode", "2" );
			spawnArgs.Set( "_q4_dmg_core_request", "-1" );
		}'''

new_idle = '''		else if ( q4HaveCoreTransform && q4CoreRequest == 2 ) {
			// V14 baseline handoff: charge/core_start owns the reload. Once Idle
			// begins, clear the charge effect first and create one clean looping
			// core.fx instance. Do not layer the two states.
			Q4BSE_StopEntityEffects( this );
			const char *q4CoreFx = weaponDef->dict.GetString( "fx_core" );
			if ( q4CoreFx && q4CoreFx[0] ) {
				Q4BSE_AttachPersistentEffectToEntityTransform( q4CoreFx, this, q4CoreWorldOrigin, q4CoreWorldAxis );
				Q4BSE_SetEntityEffectsViewWeaponMode( this, owner ? owner->entityNumber + 1 : 0 );
			}
			if ( q4CoreMode == 0 ) {
				StartSound( "snd_rings", SND_CHANNEL_VOICE, 0, false, NULL );
			}
			q4CoreMode = 2;
			spawnArgs.Set( "_q4_dmg_core_mode", "2" );
			spawnArgs.Set( "_q4_dmg_core_request", "-1" );
		}'''
weapon = replace_once(weapon, old_idle, new_idle, 'V14 reload-to-idle handoff')

combined = ph + pc + impact + weapon
for required in (
    'float jitterRate;',
    'p.jitterRate = ToFloat',
    'q4ElectricitySeed',
    'Q4ElectricityApplyShape',
    'RenderQ4DarkMatterElectricity',
    'Q4ElectricityJitterWeight',
    'Q4BSE_AttachPersistentEffectToEntityTransform( q4CoreStartFx',
    'V14 baseline handoff',
):
    if required not in combined:
        raise SystemExit(f'ERROR: V19C verification missing: {required}')

if 'V19B presentation handoff' in weapon:
    raise SystemExit('ERROR: V19C did not remove V19B handoff behavior')

PARSER_H.write_text(ph, encoding='utf-8')
PARSER_CPP.write_text(pc, encoding='utf-8')
IMPACT.write_text(impact, encoding='utf-8')
WEAPON.write_text(weapon, encoding='utf-8')

print('Q4BSE V19C / V21 DARK MATTER NATIVE ELECTRICITY PASS.')
print('  - V14 core/core_start content untouched')
print('  - V14 charge lifetime + cleanup-first idle handoff restored')
print('  - jitterRate retained; Dark Matter jitterRate=0 reseeds every frame')
print('  - halfsintable evaluated with runtime fallback')
print('  - dynamic Raven bolt count + accumulated jitter + recursive ApplyShape')
print('  - Raven-style constant camera-facing electricity ribbon')
print('  - generic/projectile electricity path unchanged')
print('  - line primitive left unchanged after exact OpenQ4 parity audit')
