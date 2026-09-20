#!/usr/bin/env python3
'''V19D / user-facing V24: native Raven line-segment presentation for idle DMG core.

Runs after V19C.  Scoped to effects/weapons/dmg/core.fx while it is rendered
as view-local Dark Matter geometry.

Quake 4 BSE does NOT submit one transparent render surface per line particle.
Each emitter/segment owns one surface, and every active rvLineParticle appends
its quad to that shared surface in stable segment order.

The Doom 3 M3 bridge was rebuilding one material surface per particle and
interleaving surfaces by particle birth order across all segments.  For the
idle Dark Matter blacklines/small-lines (alpha blended soft streak textures)
that makes many overlapping quads present like hard jittery pieces rather than
one coherent inward-collapse layer.

This patch restores Raven-style segment grouping/order for the idle core only.
No FX declarations, line dimensions, spawn domains, lifetime/envelopes,
electricity renderer, core lifecycle, or projectile behavior are changed.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
if not IMPACT.exists():
    raise SystemExit(f'ERROR: V19D prerequisite missing: {IMPACT}')

text = IMPACT.read_text(encoding='utf-8-sig')

def replace_once(s, old, new, label):
    hits = s.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V19D expected exactly one {label}, found {hits}')
    return s.replace(old, new, 1)

anchor = '''static bool RenderParticle(idRenderModel* model, const M3Particle& p, float elapsedSec,
                           const idVec3& viewOrigin, const idMat3& viewAxis) {'''

helper = r'''static bool Q4ParticleRenderState(const M3Particle& p, float elapsedSec,
                                  float& age, float& life, idVec4& color) {
    if (!p.segment) return false;
    const q4bse::ParticleTemplate& pt = p.segment->particle;
    age = elapsedSec - p.birthSec;
    if (age < 0.0f) return false;

    if (g_m3Impact.attachedPersistent && p.segment->constant) {
        if (p.durationSec > M3_EPSILON) age = (float)fmod(age, p.durationSec);
    } else if (age >= p.durationSec) {
        return false;
    }

    life = Clamp01(age / p.durationSec);
    const idVec3 tint = EvalVec3(p.tintStart, p.tintEnd, FindDomain(pt.motion, "tint"), life);
    const float fade = EvalFloat(p.fadeStart, p.fadeEnd, FindDomain(pt.motion, "fade"), life);
    if (fade <= 0.0f) return false;
    color.Set(tint.x, tint.y, tint.z, fade);
    return true;
}

static bool RenderQ4DarkMatterLineSegment(idRenderModel* model, int segmentIndex,
                                          float elapsedSec,
                                          const idVec3& viewOrigin,
                                          const idMat3& viewAxis) {
    if (!model || !declManager || !g_m3Impact.effect) return false;
    if (segmentIndex < 0 || segmentIndex >= (int)g_m3Impact.effect->segments.size()) return false;

    const q4bse::Segment& segment = g_m3Impact.effect->segments[segmentIndex];
    if (!segment.hasParticle || segment.particle.primitive != "line") return false;
    const q4bse::ParticleTemplate& pt = segment.particle;

    int visibleCount = 0;
    for (size_t i = 0; i < g_m3Impact.particles.size(); ++i) {
        const M3Particle& p = g_m3Impact.particles[i];
        if (p.segmentIndex != segmentIndex) continue;
        float age = 0.0f, life = 0.0f;
        idVec4 color;
        if (Q4ParticleRenderState(p, elapsedSec, age, life, color)) {
            ++visibleCount;
        }
    }
    if (visibleCount <= 0) return false;

    const idMaterial* material = declManager->FindMaterial(pt.material.c_str(), false);
    if (!material) return false;

    const int maxVerts = visibleCount * 4;
    const int maxIndexes = visibleCount * 6;
    srfTriangles_t* tri = model->AllocSurfaceTriangles(maxVerts, maxIndexes);
    if (!tri || !tri->verts || !tri->indexes) return false;
    tri->numVerts = 0;
    tri->numIndexes = 0;
    tri->generateNormals = false;

    const bool additive = IsAdditive(pt);
    int rendered = 0;

    // Raven rvSegment::Render traverses one segment particle list and appends
    // all rvLineParticle quads into THIS ONE surface. Keep our birth-order list
    // but restore that exact surface ownership and stable segment layering.
    for (size_t i = 0; i < g_m3Impact.particles.size(); ++i) {
        const M3Particle& p = g_m3Impact.particles[i];
        if (p.segmentIndex != segmentIndex) continue;

        float age = 0.0f, life = 0.0f;
        idVec4 color;
        if (!Q4ParticleRenderState(p, elapsedSec, age, life, color)) continue;

        const float width = EvalFloat(p.sizeStart.x, p.sizeEnd.x,
                                      FindDomain(pt.motion, "size"), life);
        const idVec3 length = EvalVec3(p.lengthStart, p.lengthEnd,
                                       FindDomain(pt.motion, "length"), life);
        const idVec3 pos = ParticleWorldPosition(p, age);
        const idVec3 end = pos + length;
        const idVec3 toView = viewOrigin - (pos + length * 0.5f);

        idVec3 side = length.Cross(toView);
        const float sideLenSqr = side.LengthSqr();
        if (sideLenSqr > M3_EPSILON) {
            side *= idMath::InvSqrt(sideLenSqr);
        } else {
            side = viewAxis[1];
        }
        side *= idMath::Fabs(width);

        const int base = tri->numVerts;
        const int ib = tri->numIndexes;

        // Exact Raven rvLineParticle UV layout. The blend_sphere2 alpha texture
        // supplies the soft streak profile; shrinking authored length provides
        // the inward/suction read.
        SetDrawVert(tri->verts[base + 0], pos + side, 0.0f, 0.0f, color, additive);
        SetDrawVert(tri->verts[base + 1], pos - side, 0.0f, 1.0f, color, additive);
        SetDrawVert(tri->verts[base + 2], end - side, 1.0f, 1.0f, color, additive);
        SetDrawVert(tri->verts[base + 3], end + side, 1.0f, 0.0f, color, additive);

        // Match Raven's line normal assignment. The material is unlit, but keep
        // the submitted geometry identical instead of relying on generic normals.
        tri->verts[base + 0].normal = pos;
        tri->verts[base + 1].normal = pos;
        tri->verts[base + 2].normal = pos;
        tri->verts[base + 3].normal = pos;

        tri->indexes[ib + 0] = base + 0;
        tri->indexes[ib + 1] = base + 1;
        tri->indexes[ib + 2] = base + 2;
        tri->indexes[ib + 3] = base + 0;
        tri->indexes[ib + 4] = base + 2;
        tri->indexes[ib + 5] = base + 3;

        tri->numVerts += 4;
        tri->numIndexes += 6;
        ++rendered;
    }

    if (rendered <= 0) {
        tri->numVerts = 0;
        tri->numIndexes = 0;
        return false;
    }

    modelSurface_t surface;
    surface.id = model->NumSurfaces();
    surface.shader = material;
    surface.geometry = tri;
    model->AddSurface(surface);
    return true;
}

'''

text = replace_once(text, anchor, helper + anchor, 'native line helper insertion')

old_loop = '''    int rendered = 0;
    for (size_t i = 0; i < g_m3Impact.particles.size(); ++i) {
        if (RenderParticle(g_m3Impact.model, g_m3Impact.particles[i], elapsedSec,
                           q4RenderViewOrigin, q4RenderViewAxis)) ++rendered;
    }
    g_m3Impact.model->FinishSurfaces();'''

new_loop = '''    int rendered = 0;

    // Raven BSE creates/render-surfaces by SEGMENT, not by particle. This matters
    // for the Dark Matter idle core's alpha-blended blacklines/small-lines:
    // one shared segment surface keeps their soft blend/order coherent instead
    // of dozens of independently sorted draw surfaces flickering over the orb.
    const bool q4NativeIdleCoreLines =
        g_m3Impact.q4ViewLocalGeometry &&
        !idStr::Icmp(g_m3Impact.effectPath.c_str(), "effects/weapons/dmg/core.fx");

    if (q4NativeIdleCoreLines && g_m3Impact.effect) {
        for (int segmentIndex = 0;
             segmentIndex < (int)g_m3Impact.effect->segments.size();
             ++segmentIndex) {
            const q4bse::Segment& segment = g_m3Impact.effect->segments[segmentIndex];

            if (segment.hasParticle && segment.particle.primitive == "line") {
                if (RenderQ4DarkMatterLineSegment(g_m3Impact.model, segmentIndex,
                                                  elapsedSec,
                                                  q4RenderViewOrigin,
                                                  q4RenderViewAxis)) {
                    ++rendered;
                }
                continue;
            }

            // Non-line layers are still rendered by the proven V21/V23 paths,
            // but now in stable authored segment order just like Raven.
            for (size_t i = 0; i < g_m3Impact.particles.size(); ++i) {
                if (g_m3Impact.particles[i].segmentIndex != segmentIndex) continue;
                if (RenderParticle(g_m3Impact.model, g_m3Impact.particles[i], elapsedSec,
                                   q4RenderViewOrigin, q4RenderViewAxis)) {
                    ++rendered;
                }
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

    g_m3Impact.model->FinishSurfaces();'''

text = replace_once(text, old_loop, new_loop, 'idle core segment-ordered rebuild')

for required in (
    'RenderQ4DarkMatterLineSegment',
    'q4NativeIdleCoreLines',
    'effects/weapons/dmg/core.fx',
    'one shared segment surface',
    'tri->verts[base + 0].normal = pos',
):
    if required not in text:
        raise SystemExit(f'ERROR: V19D verification missing: {required}')

IMPACT.write_text(text, encoding='utf-8')

print('Q4BSE V19D / V24 DARK MATTER NATIVE LINE PRESENTATION PASS.')
print('  - scoped to idle effects/weapons/dmg/core.fx only')
print('  - blacklines + small-lines now batch one surface per emitter segment')
print('  - stable authored segment layer order restored')
print('  - exact Raven rvLineParticle UV/ribbon math retained')
print('  - authored fade + shrinking length now blend as one suction layer')
print('  - V21 electricity path untouched')
print('  - V23 idle electricity tuning untouched')
print('  - grow/core_start and projectile paths untouched')
