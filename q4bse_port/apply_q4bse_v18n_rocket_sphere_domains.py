#!/usr/bin/env python3
'''V18N: Quake 4 Rocket Launcher spherical explosion-domain fidelity.

Runs after V18M.  The retail Rocket Launcher impact/detonate FX use Raven
`position { sphere ... }` domains heavily, including a 40-particle oriented
surface shell (`firesphere2`) that forms part of the expanding explosion.

The M3 runtime previously had no sphere sampler: unsupported domains fell back
to their minimum corner.  On the Rocket Launcher that stacked whole particle
families 20-100 units away from the actual impact point.  In addition, Raven
`generatedNormal` was used for velocity/length but not for oriented-particle
plane orientation, so the surface shell collapsed into a flat puff.

This patch is deliberately Rocket-FX scoped by effect name.  Existing accepted
HyperBlaster/Nailgun/Blaster/MG/Shotgun/GL presentation is unchanged.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'

if not IMPACT.exists():
    raise SystemExit(f'ERROR: V18N prerequisite missing: {IMPACT}')

text = IMPACT.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V18N expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)


# Store the Raven generated normal per particle so oriented sprites can use it.
text = replace_once(
    text,
    '''    idVec3 localOffset;\n    idVec3 localVelocity;\n    bool persistWorld;''',
    '''    idVec3 localOffset;\n    idVec3 localVelocity;\n    bool hasGeneratedNormal;\n    idVec3 generatedNormal;\n    bool persistWorld;''',
    'generated-normal particle fields')

text = replace_once(
    text,
    '''          localPosition(vec3_origin), localOffset(vec3_origin), localVelocity(vec3_origin), persistWorld(false),''',
    '''          localPosition(vec3_origin), localOffset(vec3_origin), localVelocity(vec3_origin),\n          hasGeneratedNormal(false), generatedNormal(1.0f, 0.0f, 0.0f), persistWorld(false),''',
    'generated-normal constructor')

# The retail Rocket impact/detonate effects use true sphere / sphere-surface
# domains.  Sample an ellipsoid from Raven's min/max bounds instead of falling
# through to the minimum corner.  Scope to Rocket Launcher FX only so already
# accepted effects cannot change unexpectedly.
cylinder_old = '''    else if (domain->type == "cylinder" && dims >= 3) {\n        const float t = random.Unit();\n        const float phi = random.Range(0.0f, M3_TWO_PI);\n        const float radial = domain->surface ? 1.0f : random.Unit();\n        const float cy = 0.5f * (mins[1] + maxs[1]);\n        const float cz = 0.5f * (mins[2] + maxs[2]);\n        const float ry = 0.5f * (maxs[1] - mins[1]);\n        const float rz = 0.5f * (maxs[2] - mins[2]);\n        out[0] = mins[0] + (maxs[0] - mins[0]) * t;\n        out[1] = cy + idMath::Cos(phi) * ry * radial;\n        out[2] = cz + idMath::Sin(phi) * rz * radial;\n    }\n    else {'''

cylinder_new = '''    else if (domain->type == "cylinder" && dims >= 3) {\n        const float t = random.Unit();\n        const float phi = random.Range(0.0f, M3_TWO_PI);\n        const float radial = domain->surface ? 1.0f : random.Unit();\n        const float cy = 0.5f * (mins[1] + maxs[1]);\n        const float cz = 0.5f * (mins[2] + maxs[2]);\n        const float ry = 0.5f * (maxs[1] - mins[1]);\n        const float rz = 0.5f * (maxs[2] - mins[2]);\n        out[0] = mins[0] + (maxs[0] - mins[0]) * t;\n        out[1] = cy + idMath::Cos(phi) * ry * radial;\n        out[2] = cz + idMath::Sin(phi) * rz * radial;\n    }\n    else if (domain->type == "sphere" && dims >= 3 &&\n             g_m3ImpactEffect.name.find("effects/weapons/rocketlauncher/") != std::string::npos) {\n        const float cx = 0.5f * (mins[0] + maxs[0]);\n        const float cy = 0.5f * (mins[1] + maxs[1]);\n        const float cz = 0.5f * (mins[2] + maxs[2]);\n        const float rx = 0.5f * (maxs[0] - mins[0]);\n        const float ry = 0.5f * (maxs[1] - mins[1]);\n        const float rz = 0.5f * (maxs[2] - mins[2]);\n\n        // Uniform direction on a unit sphere.  Volume domains get an interior\n        // radial sample; surface domains stay on the shell.\n        const float z = random.Range(-1.0f, 1.0f);\n        const float phi = random.Range(0.0f, M3_TWO_PI);\n        float xy2 = 1.0f - z * z;\n        if (xy2 < 0.0f) xy2 = 0.0f;\n        const float xy = idMath::Sqrt(xy2);\n        const float radial = domain->surface ? 1.0f : random.Unit();\n        out[0] = cx + idMath::Cos(phi) * xy * rx * radial;\n        out[1] = cy + idMath::Sin(phi) * xy * ry * radial;\n        out[2] = cz + z * rz * radial;\n    }\n    else {'''

text = replace_once(text, cylinder_old, cylinder_new, 'Rocket sphere sampler')

# Preserve the generated normal sampled from the start-position domain.
transform_old = '''    const bool transformByNormal = pt.generatedOriginNormal || pt.generatedNormal;\n    if (transformByNormal) p.localVelocity = generatedNormal.ToMat3() * p.localVelocity;'''
transform_new = '''    const bool transformByNormal = pt.generatedOriginNormal || pt.generatedNormal;\n    p.hasGeneratedNormal = transformByNormal;\n    p.generatedNormal = generatedNormal;\n    if (transformByNormal) p.localVelocity = generatedNormal.ToMat3() * p.localVelocity;'''
text = replace_once(text, transform_old, transform_new, 'generated-normal snapshot')

# Raven oriented particles with generatedNormal are tangent to their generated
# radial normal.  The old renderer used only the impact axis, stacking the
# Rocket's firesphere shell into one flat puff.  Apply the true normal only to
# Rocket Launcher FX.
orient_old = '''    if (pt.primitive == "oriented") {\n        const idVec2 size = EvalVec2(p.sizeStart, p.sizeEnd, FindDomain(pt.motion, "size"), life);\n        const idVec3 rotate = EvalVec3(p.rotateStart, p.rotateEnd, FindDomain(pt.motion, "rotate"), life);\n        const idAngles angles(RAD2DEG(rotate.x), RAD2DEG(rotate.y), RAD2DEG(rotate.z));\n        const idMat3 localRotation = angles.ToMat3();\n        const idVec3 right = g_m3Impact.axis * (localRotation[1] * -size.x);\n        const idVec3 up = g_m3Impact.axis * (localRotation[2] * size.y);\n        idVec3 points[4] = { worldPos - right - up, worldPos - right + up, worldPos + right + up, worldPos + right - up };\n        return AddSurface(model, pt, points, st, 4, idx, 6, color);\n    }'''

orient_new = '''    if (pt.primitive == "oriented") {\n        const idVec2 size = EvalVec2(p.sizeStart, p.sizeEnd, FindDomain(pt.motion, "size"), life);\n        const idVec3 rotate = EvalVec3(p.rotateStart, p.rotateEnd, FindDomain(pt.motion, "rotate"), life);\n        const idAngles angles(RAD2DEG(rotate.x), RAD2DEG(rotate.y), RAD2DEG(rotate.z));\n        const idMat3 localRotation = angles.ToMat3();\n\n        idMat3 orientedAxis = g_m3Impact.axis;\n        if (p.hasGeneratedNormal &&\n            g_m3ImpactEffect.name.find("effects/weapons/rocketlauncher/") != std::string::npos) {\n            idVec3 worldGeneratedNormal = g_m3Impact.axis * p.generatedNormal;\n            if (worldGeneratedNormal.LengthSqr() > M3_EPSILON) {\n                worldGeneratedNormal.NormalizeFast();\n                orientedAxis = worldGeneratedNormal.ToMat3();\n            }\n        }\n\n        const idVec3 right = orientedAxis * (localRotation[1] * -size.x);\n        const idVec3 up = orientedAxis * (localRotation[2] * size.y);\n        idVec3 points[4] = { worldPos - right - up, worldPos - right + up, worldPos + right + up, worldPos + right - up };\n        return AddSurface(model, pt, points, st, 4, idx, 6, color);\n    }'''

text = replace_once(text, orient_old, orient_new, 'Rocket oriented generatedNormal plane')

for required in (
    'domain->type == "sphere"',
    'effects/weapons/rocketlauncher/',
    'hasGeneratedNormal',
    'worldGeneratedNormal',
    'orientedAxis = worldGeneratedNormal.ToMat3()',
    'q4_bse_smooth_emitter_births',
):
    if required not in text:
        raise SystemExit(f'ERROR: V18N verification missing: {required}')

IMPACT.write_text(text, encoding='utf-8')

print('Q4BSE V18N ROCKET SPHERE/ORIENTED NORMAL PASS.')
print('  - Rocket sphere domains now sample around the true effect origin')
print('  - sphere surface particles distribute around the explosion shell')
print('  - Rocket oriented generatedNormal sprites face their radial normals')
print('  - fixes off-center delayed particles and the collapsed firesphere puff')
print('  - non-Rocket effect domain/render behavior remains unchanged')
