#!/usr/bin/env python3
'''V19C / V21 test: Dark Matter in-gun renderer parity on the V14 source lineage.

This pass intentionally starts from the exact source commit that produced the
accepted V14 DLL lineage.  It does NOT change core.fx or core_start.fx.

Goals:
  1) reproduce the two accepted V10/V11 binary lifecycle patches in source;
  2) make the looping idle fx_core actually loop its emitter segments;
  3) match Raven's generatedNormal LENGTH transform for the radial line layers;
  4) replace only Dark Matter electricity presentation with a closer Raven-style
     dynamically re-jittered recursive ribbon.

Projectile / impact / guidance paths are untouched.
'''

from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
WEAPON = ROOT / 'neo' / 'game' / 'Weapon.cpp'

for p in (IMPACT, WEAPON):
    if not p.exists():
        raise SystemExit(f'ERROR: V19C prerequisite missing: {p}')

impact = IMPACT.read_text(encoding='utf-8-sig')
weapon = WEAPON.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V19C expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# 1) Reproduce accepted V10/V11 lifecycle bytes IN SOURCE.
# ---------------------------------------------------------------------------
# V10's accepted DLL toggled the transform-attached path's attachedPersistent
# argument false -> true.  This is what made core_start stay owned/live on the
# animated weapon attachment until the later explicit handoff cleanup.
impact = replace_once(
    impact,
    '''    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), worldOrigin, worldAxis, entity, false, true);''',
    '''    // V14 lineage parity: V10 made transform-attached weapon FX persistent
    // until an explicit owner/path stop.  V11 owns the core_start cleanup.
    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), worldOrigin, worldAxis, entity, true, true);''',
    'V10 transform attachment persistence')


# V11's accepted DLL did NOT preserve the core_start tail into idle.  It always
# cleaned the old recharge instance before creating the final core.  Preserve
# that exact behavior rather than the later V19A overlap experiment.
old_idle = '''		else if ( q4HaveCoreTransform && q4CoreRequest == 2 ) {
			// Raven StartRings(false): if we came from reload, preserve core_start's
			// natural tail and layer the looping idle core over it.
			if ( q4CoreMode != 1 ) {
				Q4BSE_StopEntityEffects( this );
			}
			const char *q4CoreFx = weaponDef->dict.GetString( "fx_core" );'''

new_idle = '''		else if ( q4HaveCoreTransform && q4CoreRequest == 2 ) {
			// V14/V11 accepted handoff: core_start owns recharge only.  Clean it
			// before the persistent idle core is created so charge-only growth
			// layers can never spill into the completed core.
			Q4BSE_StopEntityEffects( this );
			const char *q4CoreFx = weaponDef->dict.GetString( "fx_core" );'''

weapon = replace_once(weapon, old_idle, new_idle, 'V11 recharge-to-idle cleanup')


# ---------------------------------------------------------------------------
# 2) Real looping semantics for the IDLE Dark Matter core.
# ---------------------------------------------------------------------------
# The bridge's attachedPersistent flag kept the instance alive, but the authored
# emitter segments still stopped after their local 1-second duration.  Quake 4
# PlayEffect(..., loop=true) loops the BSE itself.  For core.fx all emitter
# starts are zero, so lifetime-long emitter service is equivalent to repeated
# 1-second segment cycles while avoiding any FX-declaration rewrite.
old_loop = '''            idEntity* q4LoopOwner = g_m3Impact.attachedEntity.GetEntity();
            const bool q4LoopAttachedEmitter = g_m3Impact.attachedPersistent && q4LoopOwner &&
                q4LoopOwner->spawnArgs.GetBool( "q4_bse_loop_emitters" );
            emitter.active = rate > M3_EPSILON && (durationSec > 0.0f || q4LoopAttachedEmitter);
            emitter.endSec = q4LoopAttachedEmitter ? 3600.0f : (startSec + durationSec);'''

new_loop = '''            idEntity* q4LoopOwner = g_m3Impact.attachedEntity.GetEntity();
            const bool q4DarkMatterIdleCoreLoop =
                g_m3Impact.attachedPersistent &&
                !idStr::Icmp( g_m3Impact.effectPath.c_str(), "effects/weapons/dmg/core.fx" );
            const bool q4LoopAttachedEmitter = q4DarkMatterIdleCoreLoop ||
                (g_m3Impact.attachedPersistent && q4LoopOwner &&
                 q4LoopOwner->spawnArgs.GetBool( "q4_bse_loop_emitters" ));
            emitter.active = rate > M3_EPSILON && (durationSec > 0.0f || q4LoopAttachedEmitter);
            emitter.endSec = q4LoopAttachedEmitter ? 3600.0f : (startSec + durationSec);'''

impact = replace_once(impact, old_loop, new_loop, 'true looping idle core emitters')


# ---------------------------------------------------------------------------
# 3) generatedNormal line/electricity LENGTH transform parity.
# ---------------------------------------------------------------------------
# Raven intentionally transforms velocity with matrix*vector, but its length
# envelope uses rvEnvParms3Particle::Transform(normal), which performs
# vector*=normal.ToMat3().  The bridge had used matrix*vector for BOTH.  Keep
# the fix scoped to Dark Matter so already-accepted line FX on other weapons
# cannot regress in this test.
old_length = '''    if (transformByNormal) {
        const idMat3 normalAxis = generatedNormal.ToMat3();
        p.lengthStart = normalAxis * p.lengthStart;
        p.lengthEnd = normalAxis * p.lengthEnd;
    }'''

new_length = '''    if (transformByNormal) {
        const idMat3 normalAxis = generatedNormal.ToMat3();
        const bool q4DarkMatterCorePrimitive =
            g_m3Impact.effectPath.find("effects/weapons/dmg/core") != std::string::npos;
        if (q4DarkMatterCorePrimitive) {
            // Raven rvEnvParms3Particle::Transform(normal): vector * matrix.
            p.lengthStart *= normalAxis;
            p.lengthEnd *= normalAxis;
        } else {
            p.lengthStart = normalAxis * p.lengthStart;
            p.lengthEnd = normalAxis * p.lengthEnd;
        }
    }'''

impact = replace_once(impact, old_length, new_length, 'Dark Matter generatedNormal length transform')


# ---------------------------------------------------------------------------
# 4) Raven-style dynamic electricity renderer, Dark Matter ONLY.
# ---------------------------------------------------------------------------
# V18T's first implementation used a fixed 6-step sin/cos zig-zag whose seed was
# constant for the entire particle lifetime.  That is why the bolts read like
# rigid little greebles rotating with the gyro.  Raven re-jitters electricity
# during presentation (core authors jitterRate 0), applies the authored jitter
# table, then recursively shapes each section before building the ribbon.

render_anchor = '''static bool RenderParticle(idRenderModel* model, const M3Particle& p, float elapsedSec,
                           const idVec3& viewOrigin, const idMat3& viewAxis) {'''

if impact.count(render_anchor) != 1:
    raise SystemExit(f'ERROR: V19C RenderParticle anchor count={impact.count(render_anchor)}')

helpers = r'''static void Q4DMGElectricityApplyShape(M3Random& random,
                                      const idVec3& start,
                                      const idVec3& end,
                                      int recurse,
                                      std::vector<idVec3>& out) {
    if (recurse <= 0) {
        out.push_back(start);
        return;
    }

    idVec3 forward = end - start;
    const float segmentLength = forward.Length();
    if (segmentLength <= M3_EPSILON) {
        out.push_back(start);
        return;
    }
    forward *= (1.0f / segmentLength);

    idVec3 left;
    const float xy = forward.x * forward.x + forward.y * forward.y;
    if (xy > M3_EPSILON) {
        const float inv = idMath::InvSqrt(xy);
        left.Set(-forward.y * inv, forward.x * inv, 0.0f);
    } else {
        left.Set(1.0f, 0.0f, 0.0f);
    }

    idVec3 down = left.Cross(forward);
    if (down.LengthSqr() > M3_EPSILON) down.NormalizeFast();
    else down.Set(0.0f, 1.0f, 0.0f);

    const float randA = random.Range(0.05f, 0.09f);
    const float randB = random.Range(0.05f, 0.09f);
    const float shape = random.Range(0.56f, 0.76f);
    const float shapedLength = segmentLength * 0.70f;
    const float len1 = random.Range(-randA - 0.02f, 0.02f - randA) * shapedLength;
    const float len2 = random.Range(-randB - 0.02f, 0.02f - randB) * shapedLength;
    const idVec3 perturb = left * len1 + down * len2;

    const idVec3 point1 = start * shape + end * (1.0f - shape) + perturb;
    const float t2 = random.Range(0.23f, 0.43f);
    const idVec3 point2 = start * t2 + end * (1.0f - t2) + perturb;

    Q4DMGElectricityApplyShape(random, start, point1, recurse - 1, out);
    Q4DMGElectricityApplyShape(random, point1, point2, recurse - 1, out);
    Q4DMGElectricityApplyShape(random, point2, end, recurse - 1, out);
}

static bool Q4DMGRenderElectricity(idRenderModel* model,
                                   const M3Particle& p,
                                   const q4bse::ParticleTemplate& pt,
                                   const idVec4& color,
                                   const idVec3& worldPos,
                                   const idVec3& localLength,
                                   float width,
                                   const idVec3& viewOrigin,
                                   const idMat3& viewAxis) {
    // V19A core geometry is owner-local; all other paths remain untouched.
    const idVec3 renderLength = g_m3Impact.q4ViewLocalGeometry
        ? localLength : (g_m3Impact.axis * localLength);
    const idVec3 end = worldPos + renderLength;

    idVec3 forward = end - worldPos;
    const float mainLength = forward.Length();
    if (mainLength <= M3_EPSILON) return false;
    forward *= (1.0f / mainLength);

    idVec3 left;
    const float xy = forward.x * forward.x + forward.y * forward.y;
    if (xy > M3_EPSILON) {
        const float inv = idMath::InvSqrt(xy);
        left.Set(-forward.y * inv, forward.x * inv, 0.0f);
    } else {
        left.Set(1.0f, 0.0f, 0.0f);
    }
    idVec3 down = left.Cross(forward);
    if (down.LengthSqr() > M3_EPSILON) down.NormalizeFast();
    else down = viewAxis[2];

    float jitterX = 0.0f, jitterY = 0.0f, jitterZ = 0.0f;
    if (!pt.jitterSize.empty()) {
        jitterX = idMath::Fabs(pt.jitterSize[0]);
        jitterY = idMath::Fabs(pt.jitterSize.size() > 1 ? pt.jitterSize[1] : pt.jitterSize[0]);
        jitterZ = idMath::Fabs(pt.jitterSize.size() > 2 ? pt.jitterSize[2] : pt.jitterSize[0]);
    }

    M3EnvelopeTable* jitterTable = NULL;
    if (!pt.jitterTable.empty()) {
        std::string tableError;
        jitterTable = FindEnvelopeTable(pt.jitterTable.c_str(), tableError);
    }

    // Raven GetBoltCount: ceil(length * 0.0625), clamped 3..200.
    int boltCount = (int)idMath::Ceil(mainLength * 0.0625f);
    if (boltCount < 3) boltCount = 3;
    if (boltCount > 200) boltCount = 200;

    // core.fx authors jitterRate 0. Raven therefore permits a new jitter seed
    // on every presentation. Include game time so a bolt does not become a
    // rigid shape that merely follows inner_ring rotation.
    const unsigned int birthMS = (unsigned int)idMath::FtoiFast(p.birthSec * 1000.0f);
    const unsigned int frameMS = (unsigned int)gameLocal.time;
    M3Random random((unsigned int)(0x9e3779b9u ^
        (unsigned int)(p.segmentIndex * 2654435761u) ^
        (birthMS * 2246822519u) ^ (frameMS * 3266489917u)));

    std::vector<idVec3> centers;
    centers.reserve((size_t)(boltCount * 27 + 2));

    idVec3 old = worldPos;
    for (int i = 1; i <= boltCount; ++i) {
        const float fraction = (float)i / (float)boltCount;
        float noise = 1.0f;
        if (jitterTable) noise = TableLookup(*jitterTable, fraction);

        const idVec3 jitter(
            random.Range(-jitterX, jitterX),
            random.Range(-jitterY, jitterY),
            random.Range(-jitterZ, jitterZ));

        const idVec3 offset =
            forward * jitter.x + left * jitter.y + down * jitter.z;
        idVec3 current = worldPos + (end - worldPos) * fraction + offset * noise;
        if (i == boltCount) current = end;

        // Raven RenderBranch calls ApplyShape(..., recurse=2) for each section.
        Q4DMGElectricityApplyShape(random, old, current, 2, centers);
        old = current;
    }
    centers.push_back(end);

    if (centers.size() < 2) return false;

    const int centerCount = (int)centers.size();
    const int vertCount = centerCount * 2;
    const int indexCount = (centerCount - 1) * 6;
    std::vector<idVec3> points((size_t)vertCount);
    std::vector<float> uv((size_t)vertCount * 2);
    std::vector<int> indexes((size_t)indexCount);

    for (int i = 0; i < centerCount; ++i) {
        idVec3 tangent;
        if (i == 0) tangent = centers[1] - centers[0];
        else if (i == centerCount - 1) tangent = centers[i] - centers[i - 1];
        else tangent = centers[i + 1] - centers[i - 1];

        if (tangent.LengthSqr() > M3_EPSILON) tangent.NormalizeFast();
        else tangent = forward;

        idVec3 toView = viewOrigin - centers[i];
        idVec3 side = tangent.Cross(toView);
        if (side.LengthSqr() > M3_EPSILON) side.NormalizeFast();
        else side = viewAxis[1];
        side *= idMath::Fabs(width);

        points[(size_t)i * 2 + 0] = centers[i] + side;
        points[(size_t)i * 2 + 1] = centers[i] - side;

        const float u = (float)i / (float)(centerCount - 1);
        uv[((size_t)i * 2 + 0) * 2 + 0] = u;
        uv[((size_t)i * 2 + 0) * 2 + 1] = 0.0f;
        uv[((size_t)i * 2 + 1) * 2 + 0] = u;
        uv[((size_t)i * 2 + 1) * 2 + 1] = 1.0f;
    }

    for (int i = 0; i < centerCount - 1; ++i) {
        const int v = i * 2;
        const int k = i * 6;
        indexes[k + 0] = v + 0;
        indexes[k + 1] = v + 1;
        indexes[k + 2] = v + 3;
        indexes[k + 3] = v + 0;
        indexes[k + 4] = v + 3;
        indexes[k + 5] = v + 2;
    }

    return AddSurface(model, pt, &points[0], &uv[0], vertCount,
                      &indexes[0], indexCount, color);
}

'''

impact = impact.replace(render_anchor, helpers + render_anchor, 1)


# Insert the parity renderer BEFORE the older generic V18T electricity block.
old_electric_start = '''    if (pt.primitive == "electricity") {
        const float width = idMath::Fabs(EvalFloat(p.sizeStart.x, p.sizeEnd.x, FindDomain(pt.motion, "size"), life));
        const idVec3 localLength = EvalVec3(p.lengthStart, p.lengthEnd, FindDomain(pt.motion, "length"), life);
        const idVec3 worldLength = g_m3Impact.q4ViewLocalGeometry ? localLength : (g_m3Impact.axis * localLength);'''

new_electric_start = '''    if (pt.primitive == "electricity" &&
        g_m3Impact.effectPath.find("effects/weapons/dmg/core") != std::string::npos) {
        const float width = idMath::Fabs(EvalFloat(p.sizeStart.x, p.sizeEnd.x,
                                                   FindDomain(pt.motion, "size"), life));
        const idVec3 localLength = EvalVec3(p.lengthStart, p.lengthEnd,
                                            FindDomain(pt.motion, "length"), life);
        return Q4DMGRenderElectricity(model, p, pt, color, worldPos, localLength,
                                      width, viewOrigin, viewAxis);
    }

    if (pt.primitive == "electricity") {
        const float width = idMath::Fabs(EvalFloat(p.sizeStart.x, p.sizeEnd.x, FindDomain(pt.motion, "size"), life));
        const idVec3 localLength = EvalVec3(p.lengthStart, p.lengthEnd, FindDomain(pt.motion, "length"), life);
        const idVec3 worldLength = g_m3Impact.q4ViewLocalGeometry ? localLength : (g_m3Impact.axis * localLength);'''

impact = replace_once(impact, old_electric_start, new_electric_start,
                      'Dark Matter electricity parity dispatch')


# Strong gates: ensure this is the V14-lineage runtime fix and not another FX
# redesign/lifecycle-overlap experiment.
combined = impact + weapon
for required in (
    'V14 lineage parity',
    'V14/V11 accepted handoff',
    'q4DarkMatterIdleCoreLoop',
    'p.lengthStart *= normalAxis',
    'Q4DMGElectricityApplyShape',
    'FindEnvelopeTable(pt.jitterTable.c_str()',
    'gameLocal.time',
    'boltCount < 3',
):
    if required not in combined:
        raise SystemExit(f'ERROR: V19C verification missing: {required}')

if 'preserve core_start\'s\n\t\t\t// natural tail' in weapon:
    raise SystemExit('ERROR: V19C stale V19A recharge overlap still present')

IMPACT.write_text(impact, encoding='utf-8')
WEAPON.write_text(weapon, encoding='utf-8')

print('Q4BSE V19C / V21 DARK MATTER CORE RENDERER PARITY PASS.')
print('  - V10 transform-attachment persistence reproduced in source')
print('  - V11 recharge->idle cleanup reproduced in source')
print('  - idle core emitter segments now continue for the looping core')
print('  - Dark Matter generatedNormal length uses Raven vector*matrix transform')
print('  - Dark Matter electricity now re-jitters per presentation, uses jitterTable,')
print('    Raven bolt-count scaling, and recursive section shaping')
print('  - FX declarations / projectile systems untouched')
