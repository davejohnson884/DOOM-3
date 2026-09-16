#!/usr/bin/env python3
'''V18L: complete the Raven Rocket Launcher fly.fx path on top of V18K.

V18 already taught the parser the grenade-launcher Raven syntax, including
`persist` and `generatedLine`.  Rocket fly.fx adds two parse requirements plus
runtime semantics V18 did not need:
  * sound-segment `volume` is accepted but gameplay audio remains Doom 3-owned
  * `light` is accepted as the inner particle primitive of a Raven light segment
  * `persist` particles snapshot their world emission transform so smoke/fire
    remains behind a moving projectile instead of being dragged with it
  * attached emitters can be kept alive for a projectile lifetime via the
    opt-in spawnarg `q4_bse_loop_emitters`
  * expired particles are recycled so high-rate Rocket emitters do not exhaust
    the M3 particle budget after a fraction of a second

The changes are cumulative and opt-in where behavior could affect an existing
weapon. Accepted HyperBlaster/Nailgun/Blaster/MG/Shotgun/GL behavior is retained.
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


# V18 prerequisites: do not add these twice.
for required in ('bool generatedLine;', 'bool persist;'):
    if required not in parser_h:
        raise SystemExit(f'ERROR: V18L missing V18 parser prerequisite: {required}')
for required in ('k == "generatedLine"', 'k == "persist"'):
    if required not in parser_cpp:
        raise SystemExit(f'ERROR: V18L missing V18 parser implementation: {required}')

# A Raven light segment contains an inner `light { ... }` particle primitive.
parser_cpp = replace_once(
    parser_cpp,
    '''    return s == "sprite" || s == "line" || s == "oriented" || s == "decal" || s == "model" || s == "trail";''',
    '''    return s == "sprite" || s == "line" || s == "oriented" || s == "decal" || s == "model" || s == "trail" || s == "light";''',
    'light particle primitive')

# BSE sound playback remains intentionally delegated to Doom 3, but the parser
# must consume Raven's authored volume range or the complete fly.fx is rejected.
parser_cpp = replace_once(
    parser_cpp,
    '''        else if (k == "soundShader") s.soundShader = ts.get();\n        else if (IsPrimitive(k)) {''',
    '''        else if (k == "soundShader") s.soundShader = ts.get();\n        else if (k == "volume") { (void)ParseRange(ts); }\n        else if (IsPrimitive(k)) {''',
    'sound volume parsing')


# ---------------------------------------------------------------------------
# Runtime particle state: Raven `persist` means a particle emitted by a moving
# effect keeps the transform at which it was born.
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
snapshot_new = snapshot_anchor + '''\n\n    // Raven persist: smoke/fire already emitted by a moving projectile stays in\n    // world space rather than following the current attachment transform.\n    p.persistWorld = pt.persist && g_m3Impact.attachedPersistent;\n    if (p.persistWorld) {\n        p.worldSpawnOrigin = g_m3Impact.origin;\n        p.worldSpawnAxis = g_m3Impact.axis;\n    }'''
impact = replace_once(impact, snapshot_anchor, snapshot_new, 'persist transform snapshot')

impact = replace_once(
    impact,
    '''    const idVec3 local = p.localPosition + p.localOffset + p.localVelocity * ageSec;\n    idVec3 world = g_m3Impact.origin + g_m3Impact.axis * local;''',
    '''    const idVec3 local = p.localPosition + p.localOffset + p.localVelocity * ageSec;\n    idVec3 world;\n    if (p.persistWorld) {\n        world = p.worldSpawnOrigin + p.worldSpawnAxis * local;\n    } else {\n        world = g_m3Impact.origin + g_m3Impact.axis * local;\n    }''',
    'persistent particle world transform')


# ---------------------------------------------------------------------------
# V18 added delayed emitter scheduling. Preserve that exactly, but permit an
# attached projectile to opt into lifetime-long emission. No other projectile is
# changed unless its DEF explicitly carries q4_bse_loop_emitters.
# ---------------------------------------------------------------------------
emitter_old = '''            const float durationSec = SampleRange(segment.duration, 0.0f, g_m3Impact.random);\n            emitter.active = rate > M3_EPSILON && durationSec > 0.0f;\n            emitter.endSec = startSec + durationSec;\n            emitter.nextSpawnSec = startSec;'''
emitter_new = '''            const float durationSec = SampleRange(segment.duration, 0.0f, g_m3Impact.random);\n            idEntity* q4LoopOwner = g_m3Impact.attachedEntity.GetEntity();\n            const bool q4LoopAttachedEmitter = g_m3Impact.attachedPersistent && q4LoopOwner &&\n                q4LoopOwner->spawnArgs.GetBool( "q4_bse_loop_emitters" );\n            emitter.active = rate > M3_EPSILON && (durationSec > 0.0f || q4LoopAttachedEmitter);\n            emitter.endSec = q4LoopAttachedEmitter ? 3600.0f : (startSec + durationSec);\n            emitter.nextSpawnSec = startSec;'''
impact = replace_once(impact, emitter_old, emitter_new, 'attached emitter lifetime')

# Expired particles used to remain in the vector until the whole BSE instance
# died. Rocket fly.fx can author ~280 births/sec, so recycle dead entries before
# servicing the next emitter births.
service_anchor = '''static void ServiceEmitters(float elapsedSec) {'''
prune_block = '''static void PruneExpiredParticles(float elapsedSec) {\n    for (size_t i = 0; i < g_m3Impact.particles.size();) {\n        const M3Particle& p = g_m3Impact.particles[i];\n        const bool keepConstant = g_m3Impact.attachedPersistent && p.segment && p.segment->constant;\n        if (!keepConstant && elapsedSec >= p.birthSec + p.durationSec) {\n            g_m3Impact.particles.erase(g_m3Impact.particles.begin() + i);\n            continue;\n        }\n        ++i;\n    }\n}\n\n''' + service_anchor
impact = replace_once(impact, service_anchor, prune_block, 'expired particle recycler')

impact = replace_once(
    impact,
    '''        const float elapsedSec = (gameLocal.time - g_m3Impact.startTimeMS) * 0.001f;\n        ServiceEmitters(elapsedSec);''',
    '''        const float elapsedSec = (gameLocal.time - g_m3Impact.startTimeMS) * 0.001f;\n        PruneExpiredParticles(elapsedSec);\n        ServiceEmitters(elapsedSec);''',
    'frame particle recycling')


combined = parser_h + parser_cpp + impact
for required in (
    'bool generatedLine;',
    'bool persist;',
    'k == "volume"',
    's == "light"',
    'persistWorld',
    'worldSpawnOrigin',
    'q4_bse_loop_emitters',
    'PruneExpiredParticles',
):
    if required not in combined:
        raise SystemExit(f'ERROR: V18L verification missing: {required}')

for required in (
    'Q4BSE_AttachEffectToEntity',
    'attachedPersistent',
    'Q4BSE_StopEntityEffects',
):
    if required not in impact:
        raise SystemExit(f'ERROR: V18L cumulative BSE prerequisite disappeared: {required}')

PARSER_CPP.write_text(parser_cpp, encoding='utf-8')
IMPACT.write_text(impact, encoding='utf-8')

print('Q4BSE V18L ROCKET FLY/PERSIST PASS.')
print('  - V18 persist/generatedLine parser support retained')
print('  - Raven sound volume parsed while BSE audio ownership remains disabled')
print('  - Raven inner light primitive parses without rejecting fly.fx')
print('  - persist particles snapshot their world emission transform')
print('  - opt-in attached emitters run for projectile lifetime')
print('  - expired particles recycled before new emitter births')
print('  - existing accepted weapon BSE paths remain unchanged unless the new key is used')
