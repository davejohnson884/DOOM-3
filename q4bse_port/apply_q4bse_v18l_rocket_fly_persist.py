#!/usr/bin/env python3
'''V18L: complete the Raven Rocket Launcher fly.fx path on top of V18K.

The retail Rocket Launcher fly effect exposed a few Raven BSE constructs that the
existing runtime had never needed before:
  * particle `persist` (trail particles stay where they were emitted)
  * particle `generatedLine` (accepted/preserved for Raven line particles)
  * sound-segment `volume` (parsed but audio ownership remains Doom 3/idProjectile)
  * `light` as a particle primitive inside a light segment
  * continuously serviced emitters for an attached projectile effect
  * recycling expired dynamic particles so a long-lived rocket does not exhaust
    M3_MAX_PARTICLES after a fraction of a second

All changes are generic but dormant for existing effects unless they use the new
Raven keywords. Continuous attached emitters are explicitly opt-in with the
projectile spawnarg `q4_bse_loop_emitters` so accepted weapons are not changed.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PARSER_H = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4FxParser.h'
PARSER_CPP = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4FxParser.cpp'
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'

for p in (PARSER_H, PARSER_CPP, IMPACT):
    if not p.exists():
        raise SystemExit(f'ERROR: V18L prerequisite missing: {p}')

parser_h = PARSER_H.read_text(encoding='utf-8-sig')
parser_cpp = PARSER_CPP.read_text(encoding='utf-8-sig')
impact = IMPACT.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V18L expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Parser data: preserve the two Raven particle flags used by rocket fly.fx.
# ---------------------------------------------------------------------------
parser_h = replace_once(
    parser_h,
    '''    bool generatedNormal;\n    bool generatedOriginNormal;\n    bool flipNormal;''',
    '''    bool generatedNormal;\n    bool generatedOriginNormal;\n    bool generatedLine;\n    bool flipNormal;\n    bool persist;''',
    'ParticleTemplate flag fields')

parser_h = replace_once(
    parser_h,
    '''    ParticleTemplate() : generatedNormal(false), generatedOriginNormal(false), flipNormal(false) {}''',
    '''    ParticleTemplate() : generatedNormal(false), generatedOriginNormal(false), generatedLine(false), flipNormal(false), persist(false) {}''',
    'ParticleTemplate constructor')

# Particle keywords.
parser_cpp = replace_once(
    parser_cpp,
    '''        else if (k == "generatedOriginNormal") p.generatedOriginNormal = true;\n        else if (k == "flipNormal") p.flipNormal = true;''',
    '''        else if (k == "generatedOriginNormal") p.generatedOriginNormal = true;\n        else if (k == "generatedLine") p.generatedLine = true;\n        else if (k == "flipNormal") p.flipNormal = true;\n        else if (k == "persist") p.persist = true;''',
    'Raven particle flags')

# A Raven light segment contains an inner `light { ... }` particle primitive.
parser_cpp = replace_once(
    parser_cpp,
    '''    return s == "sprite" || s == "line" || s == "oriented" || s == "decal" || s == "model" || s == "trail";''',
    '''    return s == "sprite" || s == "line" || s == "oriented" || s == "decal" || s == "model" || s == "trail" || s == "light";''',
    'light particle primitive')

# BSE sound playback is intentionally delegated to Doom 3, but the parser still
# needs to accept Raven's authored volume range or the whole effect is rejected.
parser_cpp = replace_once(
    parser_cpp,
    '''        else if (k == "soundShader") s.soundShader = ts.get();\n        else if (IsPrimitive(k)) {''',
    '''        else if (k == "soundShader") s.soundShader = ts.get();\n        else if (k == "volume") { (void)ParseRange(ts); }\n        else if (IsPrimitive(k)) {''',
    'sound volume parsing')

# Keep diagnostics useful.
parser_cpp = replace_once(
    parser_cpp,
    '''            if (p.generatedOriginNormal) os << " generatedOriginNormal";\n            if (p.flipNormal) os << " flipNormal";''',
    '''            if (p.generatedOriginNormal) os << " generatedOriginNormal";\n            if (p.generatedLine) os << " generatedLine";\n            if (p.flipNormal) os << " flipNormal";\n            if (p.persist) os << " persist";''',
    'particle diagnostic flags')


# ---------------------------------------------------------------------------
# Runtime particle state: Raven `persist` means an emitted particle is no longer
# transformed by the moving projectile after birth. Snapshot the BSE transform.
# ---------------------------------------------------------------------------
impact = replace_once(
    impact,
    '''    idVec3 localOffset;\n    idVec3 localVelocity;\n    idVec3 worldGravityAcceleration;''',
    '''    idVec3 localOffset;\n    idVec3 localVelocity;\n    bool persistWorld;\n    idVec3 worldSpawnOrigin;\n    idMat3 worldSpawnAxis;\n    idVec3 worldGravityAcceleration;''',
    'persistent particle fields')

impact = replace_once(
    impact,
    '''          localPosition(vec3_origin), localOffset(vec3_origin), localVelocity(vec3_origin), worldGravityAcceleration(vec3_origin),''',
    '''          localPosition(vec3_origin), localOffset(vec3_origin), localVelocity(vec3_origin), persistWorld(false),\n          worldSpawnOrigin(vec3_origin), worldSpawnAxis(mat3_identity), worldGravityAcceleration(vec3_origin),''',
    'persistent particle constructor')

snapshot_anchor = '''    if (transformByNormal) p.localVelocity = generatedNormal.ToMat3() * p.localVelocity;\n    if (pt.flipNormal) p.localVelocity = -p.localVelocity;'''
snapshot_new = snapshot_anchor + '''\n\n    // Raven persist: smoke/fire already emitted by a moving projectile must stay\n    // in world space instead of being dragged along with the attachment.\n    p.persistWorld = pt.persist && g_m3Impact.attachedPersistent;\n    if (p.persistWorld) {\n        p.worldSpawnOrigin = g_m3Impact.origin;\n        p.worldSpawnAxis = g_m3Impact.axis;\n    }'''
impact = replace_once(impact, snapshot_anchor, snapshot_new, 'persist transform snapshot')

impact = replace_once(
    impact,
    '''    const idVec3 local = p.localPosition + p.localOffset + p.localVelocity * ageSec;\n    idVec3 world = g_m3Impact.origin + g_m3Impact.axis * local;''',
    '''    const idVec3 local = p.localPosition + p.localOffset + p.localVelocity * ageSec;\n    idVec3 world;\n    if (p.persistWorld) {\n        world = p.worldSpawnOrigin + p.worldSpawnAxis * local;\n    } else {\n        world = g_m3Impact.origin + g_m3Impact.axis * local;\n    }''',
    'persistent particle world transform')


# ---------------------------------------------------------------------------
# Attached projectile effects: Q4 rocket fly.fx authors one-second emitters but
# the effect itself remains attached for the projectile lifetime. Loop only when
# the projectile explicitly opts in; HyperBlaster/Nailgun/etc retain their
# already-accepted behavior.
# ---------------------------------------------------------------------------
impact = replace_once(
    impact,
    '''            emitter.endSec = SampleRange(segment.duration, 0.0f, g_m3Impact.random);''',
    '''            idEntity* q4LoopOwner = g_m3Impact.attachedEntity.GetEntity();\n            const bool q4LoopAttachedEmitter = g_m3Impact.attachedPersistent && q4LoopOwner &&\n                q4LoopOwner->spawnArgs.GetBool( "q4_bse_loop_emitters" );\n            emitter.endSec = q4LoopAttachedEmitter ? 3600.0f :\n                SampleRange(segment.duration, 0.0f, g_m3Impact.random);''',
    'attached emitter lifetime')

# Expired emitter particles previously stayed in the vector forever. Rocket
# fly.fx emits hundreds per second, so it would hit M3_MAX_PARTICLES very fast.
service_anchor = '''static void ServiceEmitters(float elapsedSec) {'''
prune_block = '''static void PruneExpiredParticles(float elapsedSec) {\n    for (size_t i = 0; i < g_m3Impact.particles.size();) {\n        const M3Particle& p = g_m3Impact.particles[i];\n        const bool keepConstant = g_m3Impact.attachedPersistent && p.segment && p.segment->constant;\n        if (!keepConstant && elapsedSec >= p.birthSec + p.durationSec) {\n            g_m3Impact.particles.erase(g_m3Impact.particles.begin() + i);\n            continue;\n        }\n        ++i;\n    }\n}\n\n''' + service_anchor
impact = replace_once(impact, service_anchor, prune_block, 'expired particle recycler')

impact = replace_once(
    impact,
    '''        const float elapsedSec = (gameLocal.time - g_m3Impact.startTimeMS) * 0.001f;\n        ServiceEmitters(elapsedSec);''',
    '''        const float elapsedSec = (gameLocal.time - g_m3Impact.startTimeMS) * 0.001f;\n        PruneExpiredParticles(elapsedSec);\n        ServiceEmitters(elapsedSec);''',
    'frame particle recycling')


# Hard gates.
combined = parser_h + parser_cpp + impact
for required in (
    'bool generatedLine;',
    'bool persist;',
    'k == "persist"',
    'k == "generatedLine"',
    'k == "volume"',
    's == "light"',
    'persistWorld',
    'worldSpawnOrigin',
    'q4_bse_loop_emitters',
    'PruneExpiredParticles',
):
    if required not in combined:
        raise SystemExit(f'ERROR: V18L verification missing: {required}')

# Existing architectural guarantees must remain present.
for required in (
    'Q4BSE_AttachEffectToEntity',
    'attachedPersistent',
    'Q4BSE_StopEntityEffects',
):
    if required not in impact:
        raise SystemExit(f'ERROR: V18L cumulative BSE prerequisite disappeared: {required}')

PARSER_H.write_text(parser_h, encoding='utf-8')
PARSER_CPP.write_text(parser_cpp, encoding='utf-8')
IMPACT.write_text(impact, encoding='utf-8')

print('Q4BSE V18L ROCKET FLY/PERSIST PASS.')
print('  - Raven persist + generatedLine parsed')
print('  - Raven sound volume parsed while BSE audio ownership remains disabled')
print('  - Raven inner light primitive parses without rejecting the effect')
print('  - persist particles snapshot their world emission transform')
print('  - opt-in attached emitters run for projectile lifetime')
print('  - expired particles recycled before new emitter births')
print('  - existing accepted weapon BSE paths remain unchanged unless new keys are used')
