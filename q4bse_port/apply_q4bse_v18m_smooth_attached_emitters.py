#!/usr/bin/env python3
'''V18M: sub-frame smoothing for high-speed attached Raven BSE emitter births.

Runs after V18L.  The Rocket Launcher fly effect is now fully parsed and alive,
but its persistent smoke/fire particles can still be born in visible frame-sized
clusters: ServiceEmitters services several authored birth times at once, while
V18L snapshots every persistent particle at the projectile's *current* origin.
At 900 units/sec this quantizes the trail to the game frame and makes the live
Raven effect look steppy even at a high render framerate.

This patch is deliberately opt-in.  A projectile must carry:
    q4_bse_smooth_emitter_births 1

For that projectile only:
  * emitter births are not pre-spawned one frame into the future;
  * persistent particles back-project their world birth origin by the attached
    projectile's current linear velocity and the sub-frame birth age.

The authored Raven emitter rates/lifetimes/materials are unchanged.  All prior
accepted weapon BSE behavior is untouched without the new spawnarg.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'

if not IMPACT.exists():
    raise SystemExit(f'ERROR: V18M prerequisite missing: {IMPACT}')

text = IMPACT.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V18M expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)


# V18L persistent-particle snapshot.  Preserve its semantics, but for opted-in
# high-speed projectiles place a newly serviced particle at where the projectile
# was at the particle's authored sub-frame birth time rather than at the current
# frame origin.
persist_old = '''    p.persistWorld = pt.persist && g_m3Impact.attachedPersistent;\n    if (p.persistWorld) {\n        p.worldSpawnOrigin = g_m3Impact.origin;\n        p.worldSpawnAxis = g_m3Impact.axis;\n    }'''

persist_new = '''    p.persistWorld = pt.persist && g_m3Impact.attachedPersistent;\n    if (p.persistWorld) {\n        p.worldSpawnOrigin = g_m3Impact.origin;\n        p.worldSpawnAxis = g_m3Impact.axis;\n\n        idEntity* q4SmoothOwner = g_m3Impact.attachedEntity.GetEntity();\n        if (q4SmoothOwner && q4SmoothOwner->GetPhysics() &&\n            q4SmoothOwner->spawnArgs.GetBool( "q4_bse_smooth_emitter_births" )) {\n            const float q4NowSec = (gameLocal.time - g_m3Impact.startTimeMS) * 0.001f;\n            float q4BirthAge = q4NowSec - birthSec;\n            if (q4BirthAge < 0.0f) q4BirthAge = 0.0f;\n            // A normal service frame is ~16 ms.  Keep a generous cap so a hitch\n            // cannot back-project a particle hundreds of units through geometry.\n            if (q4BirthAge > 0.100f) q4BirthAge = 0.100f;\n            p.worldSpawnOrigin -= q4SmoothOwner->GetPhysics()->GetLinearVelocity() * q4BirthAge;\n        }\n    }'''

text = replace_once(text, persist_old, persist_new, 'V18L persistent birth snapshot')

# The older runtime intentionally looked one 60 Hz frame ahead.  That is useful
# for one-shot impacts, but on a moving attached emitter it makes future births
# share the current projectile origin.  Disable only for opted-in attached FX.
service_old = '''static void ServiceEmitters(float elapsedSec) {\n    const float future = elapsedSec + (1.0f / 60.0f);'''

service_new = '''static void ServiceEmitters(float elapsedSec) {\n    float future = elapsedSec + (1.0f / 60.0f);\n    idEntity* q4SmoothOwner = g_m3Impact.attachedEntity.GetEntity();\n    if (g_m3Impact.attachedPersistent && q4SmoothOwner &&\n        q4SmoothOwner->spawnArgs.GetBool( "q4_bse_smooth_emitter_births" )) {\n        // Tiny epsilon includes a birth authored exactly on the current time,\n        // without manufacturing a full frame of future particles.\n        future = elapsedSec + 0.0001f;\n    }'''

text = replace_once(text, service_old, service_new, 'ServiceEmitters look-ahead')

for required in (
    'q4_bse_smooth_emitter_births',
    'q4BirthAge',
    'GetLinearVelocity() * q4BirthAge',
    'future = elapsedSec + 0.0001f',
    'PruneExpiredParticles',
    'q4_bse_loop_emitters',
):
    if required not in text:
        raise SystemExit(f'ERROR: V18M verification missing: {required}')

IMPACT.write_text(text, encoding='utf-8')

print('Q4BSE V18M SMOOTH ATTACHED EMITTERS PASS.')
print('  - opt-in attached emitters no longer pre-spawn one frame into the future')
print('  - persistent births use sub-frame projectile position back-projection')
print('  - authored Raven rates/materials/lifetimes remain unchanged')
print('  - non-opt-in weapons/effects retain V18L behavior exactly')
