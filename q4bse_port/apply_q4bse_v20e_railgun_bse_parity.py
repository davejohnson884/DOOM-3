#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd()
H=ROOT/'neo/game/q4bse/Q4FxParser.h'
C=ROOT/'neo/game/q4bse/Q4FxParser.cpp'
M=ROOT/'neo/game/q4bse/Q4BSEImpactM3.cpp'
for p in (H,C,M):
    if not p.exists(): raise SystemExit(f'V20E prerequisite missing: {p}')

def repl(text, old, new, label, count=1):
    hits=text.count(old)
    if hits!=count:
        raise SystemExit(f'V20E {label}: expected {count}, got {hits}')
    return text.replace(old,new,count)

h=H.read_text(encoding='utf-8-sig'); c=C.read_text(encoding='utf-8-sig'); m=M.read_text(encoding='utf-8-sig')

# Raven BSE fields required by the stock Railgun trail and impact declarations.
h=repl(h,
'''    bool persist;\n    bool flipNormal;\n    std::vector< std::pair<std::string, Domain> > start;\n''',
'''    bool persist;\n    bool flipNormal;\n    bool hasImpactBounce;\n    float impactBounce;\n    std::vector< std::pair<std::string, Domain> > start;\n''','particle impact fields')
h=repl(h,
'''    ParticleTemplate() : forkCount(0), jitterRate(0.0f), tiling(0.0f), generatedNormal(false), generatedOriginNormal(false), generatedLine(false), persist(false), flipNormal(false) {}\n''',
'''    ParticleTemplate() : forkCount(0), jitterRate(0.0f), tiling(0.0f), generatedNormal(false), generatedOriginNormal(false), generatedLine(false), persist(false), flipNormal(false), hasImpactBounce(false), impactBounce(0.0f) {}\n''','particle ctor')
h=repl(h,
'''    Range count;\n    Range start;\n''',
'''    Range count;\n    Range density;\n    float particleCap;\n    Range start;\n''','segment density fields')
h=repl(h,
'''    Segment() : detail(1.0f), locked(false), constant(false), attenuateEmitter(false), hasParticle(false) {}\n''',
'''    Segment() : particleCap(0.0f), detail(1.0f), locked(false), constant(false), attenuateEmitter(false), hasParticle(false) {}\n''','segment ctor')

c=repl(c,
'''        else if (k == "flipNormal") p.flipNormal = true;\n        else if (k == "start") ParseDomainBlock(ts, p.start);\n''',
'''        else if (k == "flipNormal") p.flipNormal = true;\n        else if (k == "impact") {\n            ts.expect("{");\n            while (!ts.accept("}")) {\n                const std::string impactKey = ts.get();\n                if (impactKey == "bounce") {\n                    p.impactBounce = ToFloat(ts.get());\n                    p.hasImpactBounce = true;\n                } else {\n                    throw std::runtime_error("unsupported impact keyword '" + impactKey + "'");\n                }\n            }\n        }\n        else if (k == "start") ParseDomainBlock(ts, p.start);\n''','impact parser')
c=repl(c,
'''    return s == "sprite" || s == "line" || s == "oriented" || s == "decal" || s == "model" || s == "trail" || s == "light" || s == "electricity";\n''',
'''    return s == "sprite" || s == "line" || s == "oriented" || s == "decal" || s == "model" || s == "trail" || s == "light" || s == "electricity" || s == "linked";\n''','linked primitive')
c=repl(c,
'''        if (k == "count") s.count = ParseRange(ts);\n        else if (k == "start") s.start = ParseRange(ts);\n''',
'''        if (k == "count") s.count = ParseRange(ts);\n        else if (k == "density") s.density = ParseRange(ts);\n        else if (k == "particleCap") s.particleCap = ToFloat(ts.get());\n        else if (k == "start") s.start = ParseRange(ts);\n''','density parser')

# Railgun trail needs 512 linked particles plus its leftover spark segment.
m=repl(m,'static const int M3_MAX_PARTICLES = 512;','static const int M3_MAX_PARTICLES = 1024;','particle cap')
m=repl(m,
'''    float durationSec;\n    idVec3 localPosition;\n''',
'''    float durationSec;\n    float spawnFraction;\n    idVec3 localPosition;\n''','particle fraction member')
m=repl(m,
'''        : segment(NULL), segmentIndex(-1), birthSec(0.0f), durationSec(0.1f),\n          localPosition(vec3_origin),''',
'''        : segment(NULL), segmentIndex(-1), birthSec(0.0f), durationSec(0.1f), spawnFraction(0.0f),\n          localPosition(vec3_origin),''','particle fraction ctor')

# Raven spiral domain support. The seventh value is the authored spiral range.
m=repl(m,
'''    else if (domain->type == "cylinder" && dims >= 3) {\n        const float t = random.Unit();\n        const float phi = random.Range(0.0f, M3_TWO_PI);\n        const float radial = domain->surface ? 1.0f : random.Unit();\n        const float cy = 0.5f * (mins[1] + maxs[1]);\n        const float cz = 0.5f * (mins[2] + maxs[2]);\n        const float ry = 0.5f * (maxs[1] - mins[1]);\n        const float rz = 0.5f * (maxs[2] - mins[2]);\n        out[0] = mins[0] + (maxs[0] - mins[0]) * t;\n        out[1] = cy + idMath::Cos(phi) * ry * radial;\n        out[2] = cz + idMath::Sin(phi) * rz * radial;\n    }\n    else if (domain->type == "sphere"''',
'''    else if (domain->type == "cylinder" && dims >= 3) {\n        const float t = random.Unit();\n        const float phi = random.Range(0.0f, M3_TWO_PI);\n        const float radial = domain->surface ? 1.0f : random.Unit();\n        const float cy = 0.5f * (mins[1] + maxs[1]);\n        const float cz = 0.5f * (mins[2] + maxs[2]);\n        const float ry = 0.5f * (maxs[1] - mins[1]);\n        const float rz = 0.5f * (maxs[2] - mins[2]);\n        out[0] = mins[0] + (maxs[0] - mins[0]) * t;\n        out[1] = cy + idMath::Cos(phi) * ry * radial;\n        out[2] = cz + idMath::Sin(phi) * rz * radial;\n    }\n    else if (domain->type == "spiral" && dims >= 3) {\n        const float range = domain->values.size() > 6 ? idMath::Fabs(domain->values[6]) : 1.0f;\n        out[0] = random.Range(mins[0], maxs[0]);\n        const float theta = M3_TWO_PI * (out[0] / (range > M3_EPSILON ? range : 1.0f));\n        const float ry = random.Range(mins[1], maxs[1]);\n        const float rz = random.Range(mins[2], maxs[2]);\n        out[1] = idMath::Cos(theta) * ry - idMath::Sin(theta) * rz;\n        out[2] = idMath::Cos(theta) * rz + idMath::Sin(theta) * ry;\n    }\n    else if (domain->type == "sphere"''','spiral generic')

anchor='''static void SampleFloatDomain(const q4bse::Domain* domain, float& value, M3Random& random) {\n    float out[1] = { value };\n    SampleDomain(domain, 1, out, random, NULL);\n    value = out[0];\n}\n'''
helper=anchor+r'''static void SampleQ4PositionDomain(const q4bse::Domain* domain, float spawnFraction,
                                   idVec3& value, M3Random& random, idVec3* generatedNormal) {
    if (!domain) return;
    if (!domain->useEndOrigin || !g_m3UseEndOrigin) {
        SampleVec3Domain(domain, value, random, generatedNormal);
        return;
    }

    float mins[3] = { 0, 0, 0 };
    float maxs[3] = { 0, 0, 0 };
    DomainEndpoints(*domain, 3, mins, maxs);
    const float t = domain->linearSpacing ? Clamp01(spawnFraction) : random.Unit();

    idVec3 local;
    idVec3 localNormal(1.0f, 0.0f, 0.0f);
    if (domain->type == "spiral") {
        const float x = domain->linearSpacing
            ? (mins[0] + (maxs[0] - mins[0]) * t)
            : random.Range(mins[0], maxs[0]);
        const float range = domain->values.size() > 6 ? idMath::Fabs(domain->values[6]) : 1.0f;
        const float safeRange = range > M3_EPSILON ? range : 1.0f;
        const float theta = M3_TWO_PI * (x / safeRange);
        const float ry = random.Range(mins[1], maxs[1]);
        const float rz = random.Range(mins[2], maxs[2]);
        local.x = x;
        local.y = idMath::Cos(theta) * ry - idMath::Sin(theta) * rz;
        local.z = idMath::Cos(theta) * rz + idMath::Sin(theta) * ry;
        localNormal.Set(0.0f, local.y, local.z);
    } else if (domain->type == "line") {
        const float lineT = domain->linearSpacing ? t : random.Unit();
        local.Set(mins[0] + (maxs[0] - mins[0]) * lineT,
                  mins[1] + (maxs[1] - mins[1]) * lineT,
                  mins[2] + (maxs[2] - mins[2]) * lineT);
        localNormal = local;
    } else {
        SampleVec3Domain(domain, local, random, generatedNormal ? &localNormal : NULL);
    }

    const idVec3 endLocal = g_m3Impact.axis.Transpose() * (g_m3EndOrigin - g_m3Impact.origin);
    idVec3 forward = endLocal;
    if (forward.LengthSqr() <= M3_EPSILON) {
        value = local;
        if (generatedNormal) *generatedNormal = localNormal;
        return;
    }
    const float endLength = forward.Normalize();
    idVec3 right, up;
    forward.NormalVectors(right, up);

    if (domain->type == "spiral" && domain->linearSpacing && domain->values.size() > 6) {
        const float range = idMath::Fabs(domain->values[6]);
        if (range > M3_EPSILON) {
            float s = 0.0f, c = 1.0f;
            idMath::SinCos(M3_TWO_PI * ((t * endLength) / range), s, c);
            const float y = local.y * c - local.z * s;
            const float z = local.y * s + local.z * c;
            local.y = y;
            local.z = z;
            const float ny = localNormal.y * c - localNormal.z * s;
            const float nz = localNormal.y * s + localNormal.z * c;
            localNormal.y = ny;
            localNormal.z = nz;
        }
    }

    value = endLocal * t + forward * local.x + right * local.y + up * local.z;
    if (generatedNormal) {
        idVec3 n = forward * localNormal.x + right * localNormal.y + up * localNormal.z;
        if (n.LengthSqr() > M3_EPSILON) n.NormalizeFast(); else n = forward;
        *generatedNormal = n;
    }
}
'''
m=repl(m,anchor,helper,'end-origin position helper')

m=repl(m,'static bool SpawnParticleForSegment(int segmentIndex, float birthSec) {\n','static bool SpawnParticleForSegment(int segmentIndex, float birthSec, float spawnFraction = -1.0f) {\n','spawn signature')
m=repl(m,
'''    if (pt.primitive != "sprite" && pt.primitive != "line" && pt.primitive != "oriented" && pt.primitive != "electricity") return false;\n''',
'''    if (pt.primitive != "sprite" && pt.primitive != "line" && pt.primitive != "oriented" && pt.primitive != "electricity" && pt.primitive != "linked") return false;\n''','spawn linked')
m=repl(m,
'''    p.birthSec = birthSec;\n    p.durationSec = SampleRange(pt.duration, 0.1f, g_m3Impact.random);\n''',
'''    p.birthSec = birthSec;\n    p.spawnFraction = spawnFraction >= 0.0f ? Clamp01(spawnFraction) : g_m3Impact.random.Unit();\n    p.durationSec = SampleRange(pt.duration, 0.1f, g_m3Impact.random);\n''','spawn fraction')
m=repl(m,
'''    SampleVec3Domain(startPosition, p.localPosition, g_m3Impact.random,\n                     (pt.generatedOriginNormal || pt.generatedNormal) ? &generatedNormal : NULL);\n''',
'''    SampleQ4PositionDomain(startPosition, p.spawnFraction, p.localPosition, g_m3Impact.random,\n                           (pt.generatedOriginNormal || pt.generatedNormal) ? &generatedNormal : NULL);\n''','position sampling')
m=repl(m,
'''    if (pt.primitive == "line" || pt.primitive == "electricity") {\n''',
'''    if (pt.primitive == "line" || pt.primitive == "electricity" || pt.primitive == "linked") {\n''','linked scalar size')

old='''static int SampleSpawnerCount(const q4bse::Segment& segment) {\n    if (!segment.count.valid) return 1;\n    const float sampled = SampleRange(segment.count, 1.0f, g_m3Impact.random);\n    int count = idMath::FtoiFast(idMath::Ceil(sampled));\n    if (count < 0) count = 0;\n    if (count > M3_MAX_PARTICLES) count = M3_MAX_PARTICLES;\n    return count;\n}\n'''
new=r'''static float Q4SpawnVolume(const q4bse::Segment& segment) {
    if (!segment.hasParticle) return 1.0f;
    const q4bse::Domain* position = FindDomain(segment.particle.start, "position");
    if (!position) return 1.0f;
    float mins[3] = { 0, 0, 0 };
    float maxs[3] = { 0, 0, 0 };
    DomainEndpoints(*position, 3, mins, maxs);
    float xExtent = maxs[0] - mins[0];
    if (position->useEndOrigin && g_m3UseEndOrigin) {
        xExtent = (g_m3EndOrigin - g_m3Impact.origin).Length() - mins[0];
    }
    const float yExtent = maxs[1] - mins[1];
    const float zExtent = maxs[2] - mins[2];
    float volume = (idMath::Fabs(xExtent) + idMath::Fabs(yExtent) + idMath::Fabs(zExtent)) * 0.01f;
    return idMath::ClampFloat(M3_EPSILON, 1000.0f, volume);
}

static int SampleSpawnerCount(const q4bse::Segment& segment) {
    float sampled = 1.0f;
    if (segment.density.valid) {
        sampled = SampleRange(segment.density, 0.0f, g_m3Impact.random) * Q4SpawnVolume(segment);
    } else if (segment.count.valid) {
        sampled = SampleRange(segment.count, 1.0f, g_m3Impact.random);
    }
    int count = idMath::FtoiFast(idMath::Ceil(sampled));
    if (count < 0) count = 0;
    if (segment.particleCap > 0.0f) {
        const int authoredCap = idMath::FtoiFast(idMath::Ceil(segment.particleCap));
        if (count > authoredCap) count = authoredCap;
    }
    if (count > M3_MAX_PARTICLES) count = M3_MAX_PARTICLES;
    return count;
}
'''
m=repl(m,old,new,'density runtime')
m=repl(m,
'''            for (int p = 0; p < count; ++p) SpawnParticleForSegment(i, birthSec);\n''',
'''            for (int p = 0; p < count; ++p) {\n                const float fraction = count > 0 ? (float)p / (float)count : 0.0f;\n                SpawnParticleForSegment(i, birthSec, fraction);\n            }\n''','spawner fractions')

renderAnchor='''static bool RenderParticle(idRenderModel* model, const M3Particle& p, float elapsedSec,\n                           const idVec3& viewOrigin, const idMat3& viewAxis) {\n'''
linked=r'''static bool RenderQ4LinkedSegment(idRenderModel* model, int segmentIndex, float elapsedSec,
                                      const idVec3& viewOrigin, const idMat3& viewAxis) {
    if (!model || !declManager || !g_m3Impact.effect) return false;
    if (segmentIndex < 0 || segmentIndex >= (int)g_m3Impact.effect->segments.size()) return false;
    const q4bse::Segment& segment = g_m3Impact.effect->segments[segmentIndex];
    if (!segment.hasParticle || segment.particle.primitive != "linked") return false;
    const q4bse::ParticleTemplate& pt = segment.particle;
    const idMaterial* material = declManager->FindMaterial(pt.material.c_str(), false);
    if (!material) return false;

    std::vector<const M3Particle*> visible;
    for (size_t i = 0; i < g_m3Impact.particles.size(); ++i) {
        const M3Particle& p = g_m3Impact.particles[i];
        if (p.segmentIndex != segmentIndex) continue;
        const float age = elapsedSec - p.birthSec;
        if (age < 0.0f || age >= p.durationSec) continue;
        visible.push_back(&p);
    }
    if (visible.size() < 2) return false;

    const int pairCount = (int)visible.size();
    const int vertCount = pairCount * 2;
    const int indexCount = (pairCount - 1) * 6;
    srfTriangles_t* tri = model->AllocSurfaceTriangles(vertCount, indexCount);
    if (!tri || !tri->verts || !tri->indexes) return false;
    const bool additive = IsAdditive(pt);
    const float texScale = pt.tiling > M3_EPSILON ? pt.tiling : 1.0f;

    for (int i = 0; i < pairCount; ++i) {
        const M3Particle& p = *visible[(size_t)i];
        const float age = elapsedSec - p.birthSec;
        const float life = Clamp01(age / p.durationSec);
        const idVec3 tint = EvalVec3(p.tintStart, p.tintEnd, FindDomain(pt.motion, "tint"), life);
        const float fade = EvalFloat(p.fadeStart, p.fadeEnd, FindDomain(pt.motion, "fade"), life) *
                           Clamp01(g_m3Impact.externalAttenuation);
        const idVec4 color(tint.x, tint.y, tint.z, fade);
        const float size = idMath::Fabs(EvalFloat(p.sizeStart.x, p.sizeEnd.x,
                                                   FindDomain(pt.motion, "size"), life));
        const idVec3 position = ParticleWorldPosition(p, age);
        const idVec3 up = viewAxis[1] * size;
        const float u = p.spawnFraction * texScale;
        SetDrawVert(tri->verts[i * 2 + 0], position + up, u, 0.0f, color, additive);
        SetDrawVert(tri->verts[i * 2 + 1], position - up, u, 1.0f, color, additive);
    }
    for (int i = 0; i < pairCount - 1; ++i) {
        const int v = i * 2;
        const int k = i * 6;
        tri->indexes[k + 0] = v + 0;
        tri->indexes[k + 1] = v + 1;
        tri->indexes[k + 2] = v + 2;
        tri->indexes[k + 3] = v + 1;
        tri->indexes[k + 4] = v + 3;
        tri->indexes[k + 5] = v + 2;
    }
    tri->numVerts = vertCount;
    tri->numIndexes = indexCount;
    tri->generateNormals = false;
    modelSurface_t surface;
    surface.id = model->NumSurfaces();
    surface.shader = material;
    surface.geometry = tri;
    model->AddSurface(surface);
    return true;
}

'''+renderAnchor
m=repl(m,renderAnchor,linked,'linked renderer')

old='''    } else {\n        for (size_t i = 0; i < g_m3Impact.particles.size(); ++i) {\n            if (RenderParticle(g_m3Impact.model, g_m3Impact.particles[i], elapsedSec,\n                               q4RenderViewOrigin, q4RenderViewAxis)) {\n                ++rendered;\n            }\n        }\n    }\n'''
new=r'''    } else if (g_m3Impact.effect &&
               strstr(g_m3Impact.effectPath.c_str(), "effects/weapons/railgun/trail") != NULL) {
        for (int segmentIndex = 0; segmentIndex < (int)g_m3Impact.effect->segments.size(); ++segmentIndex) {
            const q4bse::Segment& segment = g_m3Impact.effect->segments[segmentIndex];
            if (segment.hasParticle && segment.particle.primitive == "linked") {
                if (RenderQ4LinkedSegment(g_m3Impact.model, segmentIndex, elapsedSec,
                                          q4RenderViewOrigin, q4RenderViewAxis)) ++rendered;
                continue;
            }
            for (size_t i = 0; i < g_m3Impact.particles.size(); ++i) {
                if (g_m3Impact.particles[i].segmentIndex != segmentIndex) continue;
                if (RenderParticle(g_m3Impact.model, g_m3Impact.particles[i], elapsedSec,
                                   q4RenderViewOrigin, q4RenderViewAxis)) ++rendered;
            }
        }
    } else {
        for (size_t i = 0; i < g_m3Impact.particles.size(); ++i) {
            if (RenderParticle(g_m3Impact.model, g_m3Impact.particles[i], elapsedSec,
                               q4RenderViewOrigin, q4RenderViewAxis)) {
                ++rendered;
            }
        }
    }
'''
m=repl(m,old,new,'Railgun authored segment render order')

for needle in ('Range density;', 'float particleCap;', 'hasImpactBounce', 's == "linked"'):
    if needle not in h+c: raise SystemExit('V20E parser verification missing '+needle)
for needle in ('M3_MAX_PARTICLES = 1024', 'SampleQ4PositionDomain', 'Q4SpawnVolume', 'RenderQ4LinkedSegment', 'spawnFraction'):
    if needle not in m: raise SystemExit('V20E runtime verification missing '+needle)

H.write_text(h,encoding='utf-8'); C.write_text(c,encoding='utf-8'); M.write_text(m,encoding='utf-8')
print('Q4BSE V20E Railgun BSE parity PASS')
print(' - Raven density / particleCap parsing and runtime count')
print(' - linked ribbon primitive')
print(' - spiral + useEndOrigin + linearSpacing path')
print(' - Railgun concrete/flesh impact bounce syntax accepted')
print(' - particle budget raised to 1024 for authored Railgun trail')
