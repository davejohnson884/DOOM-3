#!/usr/bin/env python3
"""V17: bridge Quake 4 DecalLife semantics onto stock Doom 3 projected decals.

Quake 4 added the material expression DecalLife and evaluates it per projected
triangle (parm4 in the reconstructed renderer). Stock Doom 3's renderer does
not know the DecalLife token, so feeding the retail Q4 blaster_wall_mark3
material to Doom 3 defaults the material and produces the familiar black
fallback square.

The HyperBlaster mark uses three stages whose Q4 lifetime curves are simple:
  hot1: blasterdecalFade[ DecalLife * 4 ]  -> 1 through 1.25 s, fade to 0 by 2.5 s
  hot2: blasterdecalFade[ DecalLife * 2 ]  -> 1 through 2.5 s, fade to 0 by 5.0 s
  scorch: decalFade[ DecalLife ]           -> 1 through 8.8889 s, fade to 0 by 10 s

V17 keeps the original BSE decal primitive and projection geometry, but when
that exact Raven material is requested it projects three Doom-3-native decal
materials at the same origin/normal/size. Their decalInfo stay/fade times
reproduce the retail Q4 tables without requiring renderer/exe changes.
"""

from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"

if not IMPACT.exists():
    raise SystemExit(f"ERROR: V17 prerequisite missing: {IMPACT}")

text = IMPACT.read_text(encoding="utf-8-sig")

pattern = r'''static void ProjectDecalSegment\(const q4bse::Segment& segment\) \{.*?\n\}\n\nstatic int SampleSpawnerCount'''

replacement = r'''static void ProjectDecalSegment(const q4bse::Segment& segment) {
    if (!gameRenderWorld || !declManager || !segment.hasParticle) return;
    const q4bse::ParticleTemplate& pt = segment.particle;
    if (pt.material.empty()) return;

    idVec2 size(16.0f, 16.0f);
    SampleVec2Domain(FindDomain(pt.start, "size"), size, g_m3Impact.random);
    float decalSize = idMath::Fabs(size.x);
    if (idMath::Fabs(size.y) > decalSize) decalSize = idMath::Fabs(size.y);
    if (decalSize < 1.0f) decalSize = 1.0f;

    idVec3 normal = g_m3Impact.axis[0];
    if (normal.LengthSqr() <= M3_EPSILON) normal.Set(1.0f, 0.0f, 0.0f);
    normal.NormalizeFast();

    // Q4-only material semantics bridge.
    // Stock Doom 3 does not understand the Q4 renderer expression DecalLife.
    // The retail HyperBlaster mark is three independently fading stages, so
    // reproduce those exact lifetime curves with three native projected decals.
    if (!idStr::Icmp(pt.material.c_str(), "gfx/effects/decals/blaster_wall_mark3")) {
        static const char* q4WallMarkLayers[] = {
            "gfx/effects/decals/q4hb_blaster_wall_hot1",
            "gfx/effects/decals/q4hb_blaster_wall_hot2",
            "gfx/effects/decals/q4hb_blaster_wall_scorch"
        };

        for (int i = 0; i < 3; ++i) {
            const idMaterial* layerMaterial = declManager->FindMaterial(q4WallMarkLayers[i], false);
            if (!layerMaterial) {
                common->Warning("Q4BSE: translated decal material not found: %s", q4WallMarkLayers[i]);
                continue;
            }
            gameLocal.ProjectDecal(g_m3Impact.origin, -normal, 8.0f, true,
                                   decalSize, q4WallMarkLayers[i]);
        }
        return;
    }

    const idMaterial* material = declManager->FindMaterial(pt.material.c_str(), false);
    if (!material) {
        common->Warning("Q4BSE: decal material not found: %s", pt.material.c_str());
        return;
    }

    gameLocal.ProjectDecal(g_m3Impact.origin, -normal, 8.0f, true,
                           decalSize, pt.material.c_str());
}

static int SampleSpawnerCount'''

matches = list(re.finditer(pattern, text, re.S))
if len(matches) != 1:
    raise SystemExit(f"ERROR: V17 expected exactly one ProjectDecalSegment, found {len(matches)}")

text = re.sub(pattern, replacement, text, count=1, flags=re.S)

for needle in (
    'gfx/effects/decals/blaster_wall_mark3',
    'gfx/effects/decals/q4hb_blaster_wall_hot1',
    'gfx/effects/decals/q4hb_blaster_wall_hot2',
    'gfx/effects/decals/q4hb_blaster_wall_scorch',
    'gameLocal.ProjectDecal(g_m3Impact.origin, -normal, 8.0f, true,',
):
    if needle not in text:
        raise SystemExit(f"ERROR: V17 verification missing: {needle}")

IMPACT.write_text(text, encoding="utf-8")

print("Q4BSE V17 Q4 DECAL-LIFE BRIDGE PASS.")
print("  - retail Q4 blaster_wall_mark3 no longer enters Doom 3 material parser with DecalLife")
print("  - hot layer 1: 1.25 s hold + 1.25 s fade")
print("  - hot layer 2: 2.50 s hold + 2.50 s fade")
print("  - scorch layer: 8.8889 s hold + 1.1111 s fade")
print("  - all other BSE decal materials retain generic projection behavior")
