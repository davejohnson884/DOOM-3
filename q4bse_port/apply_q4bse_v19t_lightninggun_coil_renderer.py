#!/usr/bin/env python3
'''V19T: Lightning Gun ammo-coil renderer fix.

Runs after the accepted V19S pipeline.  This is intentionally scoped only to
`effects/weapons/lightninggun/tube*` electricity.  Instead of drawing the entire
Raven bolt as one constant-width camera-facing sheet, build two very narrow
ribbons that follow the generated bolt centreline point-by-point.  The first
ribbon faces the view locally; the second is rotated 90 degrees around the local
bolt tangent.  This keeps the accepted Raven jitter/shape generation while
removing the obvious flat rectangular card inside the transparent ammo cells.
'''
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
impact_cpp = root / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"
if not impact_cpp.exists():
    raise SystemExit(f"V19T: prerequisite missing: {impact_cpp}")

text = impact_cpp.read_text(encoding="utf-8-sig")

old = r'''    // Raven uses one ribbon offset from the full bolt length. The old bridge
    // re-oriented every tiny bend and produced the angular "scribble/greeble".
    idVec3 side = length.Cross(viewOrigin);
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
                      &indexes[0], indexCount, color);
'''

new = r'''    const bool q4LightningGunTube =
        strstr(g_m3Impact.effectPath.c_str(), "effects/weapons/lightninggun/tube") != NULL;

    if (q4LightningGunTube) {
        // V19T: the stock Raven electricity primitive is fine for an open beam,
        // but inside transparent glass its one wide camera-facing ribbon exposes
        // the rectangular card.  Keep the exact generated centreline and Raven
        // per-frame jitter, but render it as two narrow intersecting fins that
        // twist with the local bolt tangent.  Geometry now hugs the filament.
        const int centerCount = (int)centers.size();
        const int pointCount = centerCount * 4;
        const int indexCount = (centerCount - 1) * 12;
        std::vector<idVec3> points((size_t)pointCount);
        std::vector<float> uv((size_t)pointCount * 2u);
        std::vector<int> indexes((size_t)indexCount);

        float tubeWidth = width * 0.28f;
        if (tubeWidth < 0.018f) tubeWidth = 0.018f;
        float crossWidth = tubeWidth * 0.82f;

        // Crop the source texture vertically to its bright central bolt/halo.
        // This preserves the original Q4 artwork without sampling the broad
        // low-level blue field that makes the quad boundary readable.
        const float vMin = 0.38f;
        const float vMax = 0.62f;

        for (int i = 0; i < centerCount; ++i) {
            idVec3 tangent;
            if (i == 0) tangent = centers[1].position - centers[0].position;
            else if (i == centerCount - 1) tangent = centers[i].position - centers[i - 1].position;
            else tangent = centers[i + 1].position - centers[i - 1].position;
            if (tangent.LengthSqr() > M3_EPSILON) tangent.NormalizeFast();
            else {
                tangent = length;
                if (tangent.LengthSqr() > M3_EPSILON) tangent.NormalizeFast();
                else tangent.Set(1.0f, 0.0f, 0.0f);
            }

            const idVec3 toView = viewOrigin - centers[i].position;
            idVec3 sideA = tangent.Cross(toView);
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

            for (int fin = 0; fin < 2; ++fin) {
                const int base = v + fin * 2;
                uv[(base + 0) * 2 + 0] = centers[i].s;
                uv[(base + 0) * 2 + 1] = vMin;
                uv[(base + 1) * 2 + 0] = centers[i].s;
                uv[(base + 1) * 2 + 1] = vMax;
            }
        }

        for (int i = 0; i < centerCount - 1; ++i) {
            const int v0 = i * 4;
            const int v1 = (i + 1) * 4;
            const int k = i * 12;

            // View-facing fin.
            indexes[k + 0] = v0 + 0; indexes[k + 1] = v0 + 1; indexes[k + 2] = v1 + 0;
            indexes[k + 3] = v0 + 1; indexes[k + 4] = v1 + 1; indexes[k + 5] = v1 + 0;
            // Perpendicular fin for actual thickness/depth inside the glass.
            indexes[k + 6]  = v0 + 2; indexes[k + 7]  = v0 + 3; indexes[k + 8]  = v1 + 2;
            indexes[k + 9]  = v0 + 3; indexes[k + 10] = v1 + 3; indexes[k + 11] = v1 + 2;
        }

        // Two fins overlap, so slightly temper RGB while retaining the authored
        // tint/fade and the existing additive material.
        const idVec4 tubeColor(color.x * 0.72f, color.y * 0.72f,
                               color.z * 0.72f, color.w);
        return AddSurface(model, pt, &points[0], &uv[0], pointCount,
                          &indexes[0], indexCount, tubeColor);
    }

    // Accepted Raven renderer for every non-tube electricity effect remains
    // byte-for-byte behaviorally unchanged.
    idVec3 side = length.Cross(viewOrigin);
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
                      &indexes[0], indexCount, color);
'''

hits = text.count(old)
if hits != 1:
    raise SystemExit(f"V19T: expected one Raven electricity ribbon anchor, found {hits}")
text = text.replace(old, new, 1)
impact_cpp.write_text(text, encoding="utf-8")

print("V19T Lightning Gun coil renderer applied")
print(" - tube* electricity only: centreline-following crossed narrow fins")
print(" - vertically crops original Q4 bolt texture to its bright central band")
print(" - spire/beam/impact/crawl/Dark Matter render paths unchanged")
