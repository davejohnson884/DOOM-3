#!/usr/bin/env python3
'''V19U: Lightning Gun ammo-coil procedural filament renderer.

Runs after V19T. The V19T experiment proved that bending the original bolt
texture onto narrow fins still leaves a readable 2D textured-sheet character
inside the transparent ammo cells. V19U keeps Raven's generated/jittering bolt
centreline but stops sampling any bolt-image texture for tube* effects.

Tube electricity becomes:
  - a razor-thin crossed white/blue core made from solid additive geometry;
  - one slightly wider, very faint cyan halo strip;
  - both follow the exact generated centreline point-by-point.

This remains path-scoped to effects/weapons/lightninggun/tube* only.
'''
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
impact_cpp = root / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
if not impact_cpp.exists():
    raise SystemExit(f'V19U: prerequisite missing: {impact_cpp}')

text = impact_cpp.read_text(encoding='utf-8-sig')

start_marker = '''    if (q4LightningGunTube) {\n        // V19T: keep the Raven-generated bolt centreline, but stop presenting'''
end_marker = '''    // Accepted renderer for every non-tube electricity effect: unchanged.'''

start = text.find(start_marker)
if start < 0:
    raise SystemExit('V19U: V19T tube renderer start marker not found')
end = text.find(end_marker, start)
if end < 0:
    raise SystemExit('V19U: V19T tube renderer end marker not found')

new_block = r'''    if (q4LightningGunTube) {
        // V19U: do not put a picture of lightning on the ammo-coil geometry at
        // all. Keep Raven's centreline/jitter, but draw that path directly as
        // a tiny luminous filament. The glass supplies the volume; the arc no
        // longer has a rectangular bolt texture that can read as a card.
        const int centerCount = (int)centers.size();
        if (centerCount < 2) return false;

        const float coreWidth = idMath::ClampFloat(0.010f, 0.024f, width * 0.075f);
        const float coreCrossWidth = coreWidth * 0.82f;
        const float haloWidth = idMath::ClampFloat(0.028f, 0.060f, width * 0.20f);

        // Solid additive materials supplied by the V19U content PK4. They map
        // _white only; no lgun_smallbolt image is sampled for these surfaces.
        q4bse::ParticleTemplate corePt = pt;
        corePt.material = "gfx/effects/weapons/lgun_coil_proc_core";
        corePt.blend = "add";
        q4bse::ParticleTemplate haloPt = pt;
        haloPt.material = "gfx/effects/weapons/lgun_coil_proc_halo";
        haloPt.blend = "add";

        // CORE: two intersecting ultra-thin fins following every local bend.
        const int corePointCount = centerCount * 4;
        const int coreIndexCount = (centerCount - 1) * 12;
        std::vector<idVec3> corePoints((size_t)corePointCount);
        std::vector<float> coreUV((size_t)corePointCount * 2u);
        std::vector<int> coreIndexes((size_t)coreIndexCount);

        // HALO: one faint view-facing strip, still very narrow.
        const int haloPointCount = centerCount * 2;
        const int haloIndexCount = (centerCount - 1) * 6;
        std::vector<idVec3> haloPoints((size_t)haloPointCount);
        std::vector<float> haloUV((size_t)haloPointCount * 2u);
        std::vector<int> haloIndexes((size_t)haloIndexCount);

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

            idVec3 sideB = tangent.Cross(sideA);
            if (sideB.LengthSqr() > M3_EPSILON) sideB.NormalizeFast();
            else sideB = viewAxis[2];

            const int cv = i * 4;
            corePoints[cv + 0] = centers[i].position + sideA * coreWidth;
            corePoints[cv + 1] = centers[i].position - sideA * coreWidth;
            corePoints[cv + 2] = centers[i].position + sideB * coreCrossWidth;
            corePoints[cv + 3] = centers[i].position - sideB * coreCrossWidth;
            for (int j = 0; j < 4; ++j) {
                coreUV[(cv + j) * 2 + 0] = centers[i].s;
                coreUV[(cv + j) * 2 + 1] = (j & 1) ? 1.0f : 0.0f;
            }

            const int hv = i * 2;
            haloPoints[hv + 0] = centers[i].position + sideA * haloWidth;
            haloPoints[hv + 1] = centers[i].position - sideA * haloWidth;
            haloUV[(hv + 0) * 2 + 0] = centers[i].s;
            haloUV[(hv + 0) * 2 + 1] = 0.0f;
            haloUV[(hv + 1) * 2 + 0] = centers[i].s;
            haloUV[(hv + 1) * 2 + 1] = 1.0f;
        }

        for (int i = 0; i < centerCount - 1; ++i) {
            const int cv0 = i * 4;
            const int cv1 = (i + 1) * 4;
            const int ck = i * 12;
            coreIndexes[ck + 0] = cv0 + 0; coreIndexes[ck + 1] = cv0 + 1; coreIndexes[ck + 2] = cv1 + 0;
            coreIndexes[ck + 3] = cv0 + 1; coreIndexes[ck + 4] = cv1 + 1; coreIndexes[ck + 5] = cv1 + 0;
            coreIndexes[ck + 6] = cv0 + 2; coreIndexes[ck + 7] = cv0 + 3; coreIndexes[ck + 8] = cv1 + 2;
            coreIndexes[ck + 9] = cv0 + 3; coreIndexes[ck + 10] = cv1 + 3; coreIndexes[ck + 11] = cv1 + 2;

            const int hv0 = i * 2;
            const int hv1 = (i + 1) * 2;
            const int hk = i * 6;
            haloIndexes[hk + 0] = hv0 + 0; haloIndexes[hk + 1] = hv0 + 1; haloIndexes[hk + 2] = hv1 + 0;
            haloIndexes[hk + 3] = hv0 + 1; haloIndexes[hk + 4] = hv1 + 1; haloIndexes[hk + 5] = hv1 + 0;
        }

        const idVec4 haloColor(0.12f, 0.48f, 1.00f, color.w * 0.18f);
        const idVec4 coreColor(0.78f, 0.93f, 1.00f, color.w * 0.88f);

        bool rendered = false;
        rendered |= AddSurface(model, haloPt, &haloPoints[0], &haloUV[0],
                               haloPointCount, &haloIndexes[0], haloIndexCount, haloColor);
        rendered |= AddSurface(model, corePt, &corePoints[0], &coreUV[0],
                               corePointCount, &coreIndexes[0], coreIndexCount, coreColor);
        return rendered;
    }

'''

text = text[:start] + new_block + text[end:]
impact_cpp.write_text(text, encoding='utf-8')

for needle in (
    'lgun_coil_proc_core',
    'lgun_coil_proc_halo',
    'coreWidth = idMath::ClampFloat',
    'haloWidth = idMath::ClampFloat',
    'q4LightningGunTube',
):
    if needle not in text:
        raise SystemExit(f'V19U: verification missing {needle}')

print('V19U Lightning Gun procedural coil renderer applied')
print(' - tube* only: no bolt-image texture sampling')
print(' - crossed razor-thin white/blue core follows Raven centreline')
print(' - faint cyan halo strip follows same centreline')
print(' - glass / lighting / beam / spire / impact / crawl unchanged')
