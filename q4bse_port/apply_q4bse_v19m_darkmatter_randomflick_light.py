#!/usr/bin/env python3
'''V19M: Raven-style randomflick envelope support for Dark Matter lighting/core.

The Q4 Dark Matter FX author `randomflick` on the core and projectile. The
bridge previously fell through to a missing decl table and effectively behaved
linearly, so adding `randomflick` to a light segment did not create visible
lightning flicker.  Add a small deterministic 16-sample built-in curve.  A
one-second persistent projectile cycle therefore pulses at roughly the same
cadence as the 0.06 s electricity particles while keeping a nonzero base glow.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
CPP = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
if not CPP.exists():
    raise SystemExit(f'ERROR: missing {CPP}')

text = CPP.read_text(encoding='utf-8-sig')

anchor = '''    if (!idStr::Icmp(env, "halflinear")) {
        // Raven's half-linear family is used here only as an ease-in growth
        // curve for the long-lived fire sprites.
        return 0.5f * lookup + 0.5f * lookup * lookup;
    }
'''

insert = anchor + '''    if (!idStr::Icmp(env, "randomflick")) {
        // Raven Dark Matter uses randomflick for its unstable core and travel
        // energy.  Use a deterministic repeating table so persistent effects
        // flicker every frame without depending on mutable RNG state.
        static const float flicker[16] = {
            0.18f, 0.86f, 0.34f, 1.00f,
            0.52f, 0.91f, 0.27f, 0.73f,
            0.42f, 0.97f, 0.22f, 0.81f,
            0.57f, 0.89f, 0.31f, 0.68f
        };
        const float scaled = lookup * 16.0f;
        const int base = idMath::FtoiFast(idMath::Floor(scaled)) & 15;
        const int next = (base + 1) & 15;
        const float frac = scaled - idMath::Floor(scaled);
        // Smooth the transition enough to read as electrical light rather
        // than hard frame-to-frame popping.
        const float smooth = frac * frac * (3.0f - 2.0f * frac);
        return flicker[base] * (1.0f - smooth) + flicker[next] * smooth;
    }
'''

if 'static const float flicker[16]' in text:
    print('V19M randomflick already present; keeping it.')
elif anchor not in text:
    raise SystemExit('ERROR: V19M EnvelopeWeight anchor not found')
else:
    text = text.replace(anchor, insert, 1)

for required in ('randomflick', 'static const float flicker[16]', 'lookup * 16.0f'):
    if required not in text:
        raise SystemExit(f'ERROR: V19M verification missing {required}')

CPP.write_text(text, encoding='utf-8')
print('Q4BSE V19M DARK MATTER RANDOMFLICK LIGHT PASS.')
print('  - randomflick now has a deterministic Raven-style oscillating curve')
print('  - projectile/core randomflick no longer falls back to linear')
print('  - existing explosion/sphere orientation runtime remains untouched')
