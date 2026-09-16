#!/usr/bin/env python3
'''V18O: Quake 4 Rocket Launcher oriented-particle parity.

Runs after V18N. V18N correctly added Rocket sphere/sphere-surface sampling and
preserved Raven generatedNormal for radial velocity, but it also used the
generated normal as the oriented quad's render plane. Reference Raven/openQ4
behavior does not do that: generatedNormal transforms velocity/acceleration
(and generated length where applicable), while an `oriented` particle keeps
its ordinary effect-axis render plane plus authored rotate envelope.

For Rocket `firesphere`, using the generated normal as the quad plane turns the
40 synchronized particles into a loose fuzzy 3D shell. Keeping the V18N sphere
spawn + radial velocity while restoring the ordinary oriented plane produces
the tighter controlled Quake 4-style expanding shockwave.

This patch only removes the V18N Rocket generatedNormal render-plane override.
The V18N sphere-domain sampler and generatedNormal velocity transform remain.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'

if not IMPACT.exists():
    raise SystemExit(f'ERROR: V18O prerequisite missing: {IMPACT}')

text = IMPACT.read_text(encoding='utf-8-sig')

old = '''    if (pt.primitive == "oriented") {
        const idVec2 size = EvalVec2(p.sizeStart, p.sizeEnd, FindDomain(pt.motion, "size"), life);
        const idVec3 rotate = EvalVec3(p.rotateStart, p.rotateEnd, FindDomain(pt.motion, "rotate"), life);
        const idAngles angles(RAD2DEG(rotate.x), RAD2DEG(rotate.y), RAD2DEG(rotate.z));
        const idMat3 localRotation = angles.ToMat3();

        idMat3 orientedAxis = g_m3Impact.axis;
        if (p.hasGeneratedNormal &&
            g_m3Impact.effectPath.find("effects/weapons/rocketlauncher/") != std::string::npos) {
            idVec3 worldGeneratedNormal = g_m3Impact.axis * p.generatedNormal;
            if (worldGeneratedNormal.LengthSqr() > M3_EPSILON) {
                worldGeneratedNormal.NormalizeFast();
                orientedAxis = worldGeneratedNormal.ToMat3();
            }
        }

        const idVec3 right = orientedAxis * (localRotation[1] * -size.x);
        const idVec3 up = orientedAxis * (localRotation[2] * size.y);
        idVec3 points[4] = { worldPos - right - up, worldPos - right + up, worldPos + right + up, worldPos + right - up };
        return AddSurface(model, pt, points, st, 4, idx, 6, color);
    }'''

new = '''    if (pt.primitive == "oriented") {
        const idVec2 size = EvalVec2(p.sizeStart, p.sizeEnd, FindDomain(pt.motion, "size"), life);
        const idVec3 rotate = EvalVec3(p.rotateStart, p.rotateEnd, FindDomain(pt.motion, "rotate"), life);
        const idAngles angles(RAD2DEG(rotate.x), RAD2DEG(rotate.y), RAD2DEG(rotate.z));
        const idMat3 localRotation = angles.ToMat3();

        // Raven parity: generatedNormal radializes particle motion, not the
        // render plane of an `oriented` primitive. Locked Rocket firesphere
        // quads therefore stay in the effect-axis plane while their sphere
        // spawn positions and velocities expand radially.
        const idVec3 right = g_m3Impact.axis * (localRotation[1] * -size.x);
        const idVec3 up = g_m3Impact.axis * (localRotation[2] * size.y);
        idVec3 points[4] = { worldPos - right - up, worldPos - right + up, worldPos + right + up, worldPos + right - up };
        return AddSurface(model, pt, points, st, 4, idx, 6, color);
    }'''

hits = text.count(old)
if hits != 1:
    raise SystemExit(f'ERROR: V18O expected exactly one V18N oriented block, found {hits}')
text = text.replace(old, new, 1)

# Hard gates: keep the fixes V18N proved while removing only the render-plane override.
for required in (
    'domain->type == "sphere"',
    'const float z = random.Range(-1.0f, 1.0f);',
    'p.localVelocity = generatedNormal.ToMat3() * p.localVelocity;',
    'const idVec3 right = g_m3Impact.axis * (localRotation[1] * -size.x);',
    'const idVec3 up = g_m3Impact.axis * (localRotation[2] * size.y);',
):
    if required not in text:
        raise SystemExit(f'ERROR: V18O verification missing: {required}')

for forbidden in (
    'orientedAxis = worldGeneratedNormal.ToMat3()',
    'const idVec3 right = orientedAxis *',
    'const idVec3 up = orientedAxis *',
):
    if forbidden in text:
        raise SystemExit(f'ERROR: V18O radial render-plane override remains: {forbidden}')

IMPACT.write_text(text, encoding='utf-8')

print('Q4BSE V18O ROCKET ORIENTED PARITY PASS.')
print('  - V18N Rocket sphere/sphere-surface sampling retained')
print('  - generatedNormal radial velocity transform retained')
print('  - Rocket oriented quads restored to ordinary Raven effect-axis plane')
print('  - removes loose fuzzy 3D shell caused by radial quad-plane override')
print('  - prior accepted weapon behavior remains unchanged')
