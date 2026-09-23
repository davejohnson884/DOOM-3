#!/usr/bin/env python3
'''V19K: Dark Matter wall-impact generatedNormal oriented-plane parity.

Runs after V19J.  The stock Raven DMG wall explosion
`effects/weapons/dmg/impact_default_mp.fx` builds its three 70-particle matter
shells from `oriented` particles spawned on a sphere with `generatedNormal`.
V18N already radialized generatedNormal velocity/acceleration correctly, while
V18O intentionally restored the ordinary effect-axis render plane for Rocket
Launcher firesphere parity.  That Rocket rule cannot be applied globally to the
DMG wall shells: keeping all 210 large DMG quads parallel makes the effect read
as a stretched/flat sheet in open areas.

Scope this correction to the stock DMG wall impact only.  Its oriented quads use
the same per-particle generated-normal basis already stored at spawn, so each
card lies tangent to the particle's radial shell.  Air/fuse detonation
`impact_default.fx`, Rocket effects, projectile flight/core visuals, and all
other oriented particles are untouched.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'

if not IMPACT.exists():
    raise SystemExit(f'ERROR: V19K prerequisite missing: {IMPACT}')

text = IMPACT.read_text(encoding='utf-8-sig')

old = '''    if (pt.primitive == "oriented") {
        const idVec2 size = EvalVec2(p.sizeStart, p.sizeEnd, FindDomain(pt.motion, "size"), life);
        const idVec3 rotate = EvalVec3(p.rotateStart, p.rotateEnd, FindDomain(pt.motion, "rotate"), life);
        const idAngles angles(RAD2DEG(rotate.x), RAD2DEG(rotate.y), RAD2DEG(rotate.z));
        const idMat3 localRotation = angles.ToMat3();

        // Raven parity: generatedNormal radializes particle motion, not the
        // render plane of an `oriented` primitive. Locked Rocket firesphere
        // quads therefore stay in the effect-axis plane while their sphere
        // spawn positions and velocities expand radially.
        const idMat3 q4RenderAxis = g_m3Impact.q4ViewLocalGeometry ? mat3_identity : g_m3Impact.axis;
        const idVec3 right = q4RenderAxis * (localRotation[1] * -size.x);
        const idVec3 up = q4RenderAxis * (localRotation[2] * size.y);
        idVec3 points[4] = { worldPos - right - up, worldPos - right + up, worldPos + right + up, worldPos + right - up };
        return AddSurface(model, pt, points, st, 4, idx, 6, color);
    }'''

new = '''    if (pt.primitive == "oriented") {
        const idVec2 size = EvalVec2(p.sizeStart, p.sizeEnd, FindDomain(pt.motion, "size"), life);
        const idVec3 rotate = EvalVec3(p.rotateStart, p.rotateEnd, FindDomain(pt.motion, "rotate"), life);
        const idAngles angles(RAD2DEG(rotate.x), RAD2DEG(rotate.y), RAD2DEG(rotate.z));
        const idMat3 localRotation = angles.ToMat3();

        // V18O's effect-axis plane is correct for Rocket firesphere, but the
        // stock DMG wall explosion uses generatedNormal to build a true radial
        // matter shell.  Reuse the exact per-particle basis that already
        // radializes velocity/acceleration, and only for impact_default_mp.fx.
        idMat3 q4RenderAxis = g_m3Impact.q4ViewLocalGeometry ? mat3_identity : g_m3Impact.axis;
        const bool q4DMGWallGeneratedNormal =
            p.hasGeneratedNormal &&
            !idStr::Icmp(g_m3Impact.effectPath.c_str(), "effects/weapons/dmg/impact_default_mp.fx");
        if (q4DMGWallGeneratedNormal) {
            const idMat3 generatedAxis = p.generatedNormal.ToMat3();
            q4RenderAxis = g_m3Impact.q4ViewLocalGeometry
                ? generatedAxis
                : g_m3Impact.axis * generatedAxis;
        }

        const idVec3 right = q4RenderAxis * (localRotation[1] * -size.x);
        const idVec3 up = q4RenderAxis * (localRotation[2] * size.y);
        idVec3 points[4] = { worldPos - right - up, worldPos - right + up, worldPos + right + up, worldPos + right - up };
        return AddSurface(model, pt, points, st, 4, idx, 6, color);
    }'''

hits = text.count(old)
if hits != 1:
    raise SystemExit(f'ERROR: V19K expected exactly one oriented render block, found {hits}')
text = text.replace(old, new, 1)

for required in (
    'p.localVelocity = generatedAxis * p.localVelocity;',
    'p.localAcceleration = generatedAxis * p.localAcceleration;',
    'effects/weapons/dmg/impact_default_mp.fx',
    'q4DMGWallGeneratedNormal',
    'g_m3Impact.axis * generatedAxis',
):
    if required not in text:
        raise SystemExit(f'ERROR: V19K verification missing: {required}')

block = text[text.index("// V18O's effect-axis plane"):text.index('return AddSurface(model, pt, points, st, 4, idx, 6, color);', text.index("// V18O's effect-axis plane"))]
if 'effects/weapons/dmg/impact_default.fx"' in block:
    raise SystemExit('ERROR: V19K accidentally touches good air/fuse detonation')

IMPACT.write_text(text, encoding='utf-8')

print('Q4BSE V19K DMG GENERATEDNORMAL ORIENTED PASS.')
print('  - wall impact_default_mp generatedNormal quads use radial/tangent basis')
print('  - existing generatedNormal velocity + acceleration transform retained')
print('  - air impact_default detonation untouched')
print('  - Rocket V18O oriented behavior untouched')
print('  - V37/V19J projectile/core/flight behavior untouched')
