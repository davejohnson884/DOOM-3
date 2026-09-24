#!/usr/bin/env python3
'''V19L: Dark Matter wall-impact Raven oriented-particle orientation parity.

Runs after V19K.

V19K proved the remaining problem is not particle count, sphere sampling, or
radial velocity.  The stock Raven BSE path does NOT render generatedNormal
oriented cards by multiplying a generated-normal matrix into the quad at render
time.  Instead, at spawn Raven:
  1) uses generatedNormal to transform velocity/acceleration, then
  2) converts that normal to angles, and
  3) adds those angles to the oriented particle's rotation envelope via
     HandleOrientation().

rvOrientedParticle::Render then builds the quad only from that already-oriented
rotation envelope.  This difference matters because Euler-angle addition is not
identical to matrix-composing generatedNormal.ToMat3() with the authored roll.

Scope this exact behavior only to the already-isolated stock DMG wall explosion
`effects/weapons/dmg/impact_default_mp.fx`.  Air/fuse detonation, Rocket, core,
projectile flight, and other oriented effects remain untouched.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
if not IMPACT.exists():
    raise SystemExit(f'ERROR: V19L prerequisite missing: {IMPACT}')

text = IMPACT.read_text(encoding='utf-8-sig')

# Add Raven HandleOrientation-equivalent immediately after authored oriented
# rotation values have been converted from turns to radians.
old_spawn = '''        ApplyRelative(endRotate, p.rotateStart, p.rotateEnd);\n        p.rotateStart *= M3_TWO_PI; p.rotateEnd *= M3_TWO_PI;\n    } else {'''

new_spawn = '''        ApplyRelative(endRotate, p.rotateStart, p.rotateEnd);\n        p.rotateStart *= M3_TWO_PI; p.rotateEnd *= M3_TWO_PI;\n\n        // Raven rvParticle::FinishSpawn calls HandleOrientation(normalAngles)\n        // after generatedNormal has radialized motion.  For an oriented\n        // particle this adds the generated normal's pitch/yaw/roll to BOTH\n        // ends of the rotation envelope.  Do exactly that for the stock DMG\n        // wall sphere and nowhere else.\n        const bool q4DMGWallGeneratedOrientation =\n            transformByNormal &&\n            !idStr::Icmp(g_m3Impact.effectPath.c_str(),\n                         "effects/weapons/dmg/impact_default_mp.fx");\n        if (q4DMGWallGeneratedOrientation) {\n            const idAngles normalAngles = generatedNormal.ToAngles();\n            const idVec3 normalOrientation(\n                DEG2RAD(normalAngles.pitch),\n                DEG2RAD(normalAngles.yaw),\n                DEG2RAD(normalAngles.roll));\n            p.rotateStart += normalOrientation;\n            p.rotateEnd += normalOrientation;\n        }\n    } else {'''

hits = text.count(old_spawn)
if hits != 1:
    raise SystemExit(f'ERROR: V19L expected one oriented rotation spawn block, found {hits}')
text = text.replace(old_spawn, new_spawn, 1)

# Undo V19K's render-time generated-axis composition.  Raven's oriented render
# consumes the rotation envelope after HandleOrientation; the whole local quad
# is then carried by our effect axis because this bridge bakes world vertices.
old_render = '''        // V18O's effect-axis plane is correct for Rocket firesphere, but the\n        // stock DMG wall explosion uses generatedNormal to build a true radial\n        // matter shell.  Reuse the exact per-particle basis that already\n        // radializes velocity/acceleration, and only for impact_default_mp.fx.\n        idMat3 q4RenderAxis = g_m3Impact.q4ViewLocalGeometry ? mat3_identity : g_m3Impact.axis;\n        const bool q4DMGWallGeneratedNormal =\n            p.hasGeneratedNormal &&\n            !idStr::Icmp(g_m3Impact.effectPath.c_str(), "effects/weapons/dmg/impact_default_mp.fx");\n        if (q4DMGWallGeneratedNormal) {\n            const idMat3 generatedAxis = p.generatedNormal.ToMat3();\n            q4RenderAxis = g_m3Impact.q4ViewLocalGeometry\n                ? generatedAxis\n                : g_m3Impact.axis * generatedAxis;\n        }\n\n        const idVec3 right = q4RenderAxis * (localRotation[1] * -size.x);\n        const idVec3 up = q4RenderAxis * (localRotation[2] * size.y);'''

new_render = '''        // Raven parity: generatedNormal orientation is already baked into the\n        // oriented particle's rotation envelope at spawn (HandleOrientation).\n        // Render with the ordinary effect axis; do not compose generatedNormal\n        // again here.\n        const idMat3 q4RenderAxis = g_m3Impact.q4ViewLocalGeometry ? mat3_identity : g_m3Impact.axis;\n        const idVec3 right = q4RenderAxis * (localRotation[1] * -size.x);\n        const idVec3 up = q4RenderAxis * (localRotation[2] * size.y);'''

hits = text.count(old_render)
if hits != 1:
    raise SystemExit(f'ERROR: V19L expected one V19K render-time generatedNormal block, found {hits}')
text = text.replace(old_render, new_render, 1)

for required in (
    'q4DMGWallGeneratedOrientation',
    'const idAngles normalAngles = generatedNormal.ToAngles();',
    'p.rotateStart += normalOrientation;',
    'p.rotateEnd += normalOrientation;',
    'p.localVelocity = generatedAxis * p.localVelocity;',
    'p.localAcceleration = generatedAxis * p.localAcceleration;',
    'const idMat3 q4RenderAxis = g_m3Impact.q4ViewLocalGeometry ? mat3_identity : g_m3Impact.axis;',
):
    if required not in text:
        raise SystemExit(f'ERROR: V19L verification missing: {required}')

for forbidden in (
    'q4DMGWallGeneratedNormal',
    'q4RenderAxis = g_m3Impact.axis * generatedAxis;',
):
    if forbidden in text:
        raise SystemExit(f'ERROR: V19L old render-time normal composition remains: {forbidden}')

IMPACT.write_text(text, encoding='utf-8')

print('Q4BSE V19L DMG RAVEN ORIENTATION ENVELOPE PASS.')
print('  - generatedNormal velocity + acceleration transform retained')
print('  - DMG wall oriented rotation envelope receives Raven normal angles')
print('  - V19K render-time normal matrix composition removed')
print('  - collision effect axis still rotates complete effect for wall/floor/angles')
print('  - air detonation / Rocket / core / projectile behavior untouched')
