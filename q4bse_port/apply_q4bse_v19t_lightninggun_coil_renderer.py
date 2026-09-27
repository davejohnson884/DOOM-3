#!/usr/bin/env python3
'''V19T: Lightning Gun ammo-coil renderer fix.

Runs after the accepted V19S pipeline.  Scope is ONLY
`effects/weapons/lightninggun/tube*` electricity.

The accepted Raven electricity path is retained for its per-frame generated
centreline/jitter, but the ammo tubes no longer use one broad constant-width
camera-facing ribbon.  V19T builds two narrow fins that follow the generated
bolt point-by-point and cross around the local tangent, so the geometry hugs
the filament instead of exposing a flat rectangular card through the glass.
'''
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
impact_cpp = root / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"
if not impact_cpp.exists():
    raise SystemExit(f"V19T: prerequisite missing: {impact_cpp}")

text = impact_cpp.read_text(encoding="utf-8-sig")

fn_anchor = "static bool RenderQ4DarkMatterElectricity("
fn = text.find(fn_anchor)
if fn < 0:
    raise SystemExit("V19T: RenderQ4DarkMatterElectricity not found")

# V19G changed the view-vector math after V19C, so do not depend on the older
# exact block.  Locate the final accepted ribbon construction structurally.
start = text.find("    idVec3 q4ViewVector = viewOrigin;", fn)
if start < 0:
    start = text.find("    idVec3 side = length.Cross(", fn)
if start < 0:
    raise SystemExit("V19T: final Raven electricity ribbon start not found")

end_marker = '''    return AddSurface(model, pt, &points[0], &uv[0], pointCount,
                      &indexes[0], indexCount, color);'''
end = text.find(end_marker, start)
if end < 0:
    raise SystemExit("V19T: final Raven electricity ribbon return not found")
end += len(end_marker)

old_block = text[start:end]

new_block = r'''    const bool q4LightningGunTube =
        strstr(g_m3Impact.effectPath.c_str(), "effects/weapons/lightninggun/tube") != NULL;

    if (q4LightningGunTube) {
        // V19T: keep the Raven-generated bolt centreline, but stop presenting
        // the ammo-cell arc as one big camera-facing sheet.  Two very narrow
        // fins follow the local tangent at every generated point.  One faces
        // the viewer locally, the second sits 90 degrees around the tangent.
        const int centerCount = (int)centers.size();
        const int pointCount = centerCount * 4;
        const int indexCount = (centerCount - 1) * 12;
        std::vector<idVec3> points((size_t)pointCount);
        std::vector<float> uv((size_t)pointCount * 2u);
        std::vector<int> indexes((size_t)indexCount);

        float tubeWidth = width * 0.28f;
        if (tubeWidth < 0.018f) tubeWidth = 0.018f;
        const float crossWidth = tubeWidth * 0.82f;

        // Raven's smallbolt artwork stays intact.  Only sample its bright
        // central vertical band, avoiding the broad low-level blue field at
        // the top/bottom of the texture that makes a transparent quad readable.
        const float vMin = 0.38f;
        const float vMax = 0.62f;

        for (int i = 0; i < centerCount; ++i) {
            idVec3 tangent;
            if (i == 0) {
                tangent = centers[1].position - centers[0].position;
            } else if (i == centerCount - 1) {
                tangent = centers[i].position - centers[i - 1].position;
            } else {
                tangent = centers[i + 1].position - centers[i - 1].position;
            }
            if (tangent.LengthSqr() > M3_EPSILON) {
                tangent.NormalizeFast();
            } else {
                tangent = length;
                if (tangent.LengthSqr() > M3_EPSILON) tangent.NormalizeFast();
                else tangent.Set(1.0f, 0.0f, 0.0f);
            }

            idVec3 q4TubeView = viewOrigin;
            if (!g_m3Impact.q4ViewLocalGeometry) {
                q4TubeView = viewOrigin - centers[i].position;
            }

            idVec3 sideA = tangent.Cross(q4TubeView);
            if (sideA.LengthSqr() > M3_EPSILON) sideA.NormalizeFast();
            else sideA = viewAxis[1];
            sideA *= tubeWidth;

            idVec3 sideB = tangent.Cross(sideA);
            if (sideB.LengthSqr() > M3_EPSILON) sideB.NormalizeFast();
            else sideB = viewAxis[2];
            sideB *= crossWidth;

            const int v = i * 4;
            points[v + 0] = centers[i].position + sideA;
            points[v + 1] = centers[i].position - sideA;
            points[v + 2] = centers[i].position + sideB;
            points[v + 3] = centers[i].position - sideB;

            uv[(v + 0) * 2 + 0] = centers[i].s;
            uv[(v + 0) * 2 + 1] = vMin;
            uv[(v + 1) * 2 + 0] = centers[i].s;
            uv[(v + 1) * 2 + 1] = vMax;
            uv[(v + 2) * 2 + 0] = centers[i].s;
            uv[(v + 2) * 2 + 1] = vMin;
            uv[(v + 3) * 2 + 0] = centers[i].s;
            uv[(v + 3) * 2 + 1] = vMax;
        }

        for (int i = 0; i < centerCount - 1; ++i) {
            const int v0 = i * 4;
            const int v1 = (i + 1) * 4;
            const int k = i * 12;

            indexes[k + 0] = v0 + 0; indexes[k + 1] = v0 + 1; indexes[k + 2] = v1 + 0;
            indexes[k + 3] = v0 + 1; indexes[k + 4] = v1 + 1; indexes[k + 5] = v1 + 0;

            indexes[k + 6]  = v0 + 2; indexes[k + 7]  = v0 + 3; indexes[k + 8]  = v1 + 2;
            indexes[k + 9]  = v0 + 3; indexes[k + 10] = v1 + 3; indexes[k + 11] = v1 + 2;
        }

        // Two fins can overlap in projection; keep the original authored tint
        // but temper the combined additive energy slightly.
        const idVec4 tubeColor(color.x * 0.72f, color.y * 0.72f,
                               color.z * 0.72f, color.w);
        return AddSurface(model, pt, &points[0], &uv[0], pointCount,
                          &indexes[0], indexCount, tubeColor);
    }

    // Accepted renderer for every non-tube electricity effect: unchanged.
    idVec3 q4ViewVector = viewOrigin;
    if (!g_m3Impact.q4ViewLocalGeometry) {
        q4ViewVector = viewOrigin - (worldPos + length * 0.5f);
    }
    idVec3 side = length.Cross(q4ViewVector);
    if (side.LengthSqr() > M3_EPSILON) side.NormalizeFast();
    else side = viewAxis[1];
    side *= width;

    const int centerCount = (int)centers.size();
    const int pointCount = centerCount * 2;
    const int indexCount = (centerCount - 1) * 6;
    std::vector<idVec3> points((size_t)pointCount);
    std::vector<float> uv((size_t)pointCount * 2u);
    std::vector<int> indexes((size_t)indexCount);

    for (int i = 0; i < centerCount; ++i) {
        points[i * 2 + 0] = centers[i].position + side;
        points[i * 2 + 1] = centers[i].position - side;
        uv[(i * 2 + 0) * 2 + 0] = centers[i].s;
        uv[(i * 2 + 0) * 2 + 1] = 0.0f;
        uv[(i * 2 + 1) * 2 + 0] = centers[i].s;
        uv[(i * 2 + 1) * 2 + 1] = 1.0f;
    }
    for (int i = 0; i < centerCount - 1; ++i) {
        const int v = i * 2;
        const int k = i * 6;
        indexes[k + 0] = v + 0;
        indexes[k + 1] = v + 1;
        indexes[k + 2] = v + 2;
        indexes[k + 3] = v + 1;
        indexes[k + 4] = v + 3;
        indexes[k + 5] = v + 2;
    }

    return AddSurface(model, pt, &points[0], &uv[0], pointCount,
                      &indexes[0], indexCount, color);'''

text = text[:start] + new_block + text[end:]

# Tight gates so this cannot silently alter other electricity paths.
for required in (
    'q4LightningGunTube',
    'effects/weapons/lightninggun/tube',
    'tubeWidth = width * 0.28f',
    'const float vMin = 0.38f',
    'const idVec4 tubeColor',
    'q4ViewVector = viewOrigin',
):
    if required not in text:
        raise SystemExit(f"V19T: verification missing {required}")

impact_cpp.write_text(text, encoding="utf-8")

print("V19T Lightning Gun coil renderer applied")
print(" - tube* electricity only: centreline-following crossed narrow fins")
print(" - original Q4 bolt texture sampled only across its bright central band")
print(" - spire/beam/impact/crawl/Dark Matter render paths unchanged")
