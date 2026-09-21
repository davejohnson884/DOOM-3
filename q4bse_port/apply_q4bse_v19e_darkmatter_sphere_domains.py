#!/usr/bin/env python3
'''V19E / user-facing V25: Dark Matter spherical spawn-domain parity.

Runs after V19D.

Root cause found after V24 showed no visible change:
The M3 sphere sampler added in V18N was deliberately scoped ONLY to
effects/weapons/rocketlauncher/*.  Dark Matter core/core_start also rely heavily
on Raven sphere-surface domains, but they were still falling through to the
generic unsupported-domain fallback, which places EVERY particle at the domain
minimum corner.

For the idle core this meant:
  blacklines   position sphere +/-0.75 surface -> ALL at (-.75,-.75,-.75)
  small lines  position sphere +/-0.75 surface -> ALL at (-.75,-.75,-.75)
  generatedNormal                              -> same diagonal normal for all

So 60 + 200 soft radial particles were stacked into one hard jittery clump
instead of being distributed around the black-hole shell.  That exactly matches
the user's screenshot.

This pass extends the already-proven Raven sphere sampler to only:
  effects/weapons/dmg/core.fx
  effects/weapons/dmg/core_start.fx
plus the existing Rocket path.

No effect declarations, line dimensions, envelopes, materials, electricity,
lifecycle, or projectile behavior are changed.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
if not IMPACT.exists():
    raise SystemExit(f'ERROR: V19E prerequisite missing: {IMPACT}')

text = IMPACT.read_text(encoding='utf-8-sig')

old = '''    else if (domain->type == "sphere" && dims >= 3 &&
             g_m3Impact.effectPath.find("effects/weapons/rocketlauncher/") != std::string::npos) {'''

new = '''    else if (domain->type == "sphere" && dims >= 3 &&
             (g_m3Impact.effectPath.find("effects/weapons/rocketlauncher/") != std::string::npos ||
              !idStr::Icmp(g_m3Impact.effectPath.c_str(), "effects/weapons/dmg/core.fx") ||
              !idStr::Icmp(g_m3Impact.effectPath.c_str(), "effects/weapons/dmg/core_start.fx"))) {'''

# Be tolerant of later patches reformatting the V18N condition. Also be
# idempotent when the Dark Matter paths are already present.
if 'g_m3Impact.effectPath.find("effects/weapons/dmg/")' in text and 'domain->type == "sphere"' in text:
    print('V19E: Dark Matter sphere-domain scope already present via dmg/ path; keeping it.')
else:
    import re
    pattern = re.compile(
        r'    else if \\(domain->type == "sphere" && dims >= 3 &&\\s*'
        r'g_m3Impact\\.effectPath\\.find\\("effects/weapons/rocketlauncher/"\\) != std::string::npos\\) \\{'
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise SystemExit(f'ERROR: V19E expected one Rocket sphere sampler, found {len(matches)}')

    commented = '''    // Raven sphere/sphere-surface parity. V18N originally limited this to
    // Rocket explosion FX. Dark Matter core/core_start use the same domain for
    // their generatedNormal electricity + blackline shells and MUST sample the
    // sphere too; otherwise all particles collapse to the minimum corner.
''' + new
    text = pattern.sub(commented, text, count=1)

# Either the exact core/core_start scope added by this script OR the broader
# already-accepted effects/weapons/dmg/ scope is valid.
if 'domain->type == "sphere"' not in text:
    raise SystemExit('ERROR: V19E verification missing sphere sampler')
if ('g_m3Impact.effectPath.find("effects/weapons/dmg/")' not in text and
    ('effects/weapons/dmg/core.fx' not in text or
     'effects/weapons/dmg/core_start.fx' not in text)):
    raise SystemExit('ERROR: V19E verification missing Dark Matter dmg sphere scope')

IMPACT.write_text(text, encoding='utf-8')

print('Q4BSE V19E / V25 DARK MATTER SPHERE DOMAIN PARITY PASS.')
print('  - idle blacklines now distribute over their authored sphere surface')
print('  - idle small-lines now distribute over their authored sphere surface')
print('  - generatedNormal becomes unique radial normal per particle')
print('  - core_start sphere-domain layers gain the same Raven parity')
print('  - V21 electricity, V23 tuning, V24 line batching remain untouched')
print('  - Rocket sphere behavior remains unchanged')
