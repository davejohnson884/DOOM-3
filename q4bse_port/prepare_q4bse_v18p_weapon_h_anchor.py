#!/usr/bin/env python3
"""Normalize cumulative source anchors expected by the strict V18P patch.

Prior Q4BSE patches preserve these declarations/initializers semantically but can
introduce either whitespace drift or another identical nozzleGlow memset in the
V18D presentation path.  V18P intentionally remains strict everywhere else.
This prep step only canonicalizes the unique declaration and makes the weapon
constructor's nozzleGlow memset the sole exact V18P constructor anchor.

Guidance follow-ups:
V18Q moves the working V18P designator/guidance transport from Doom 3 Z zoom to
BUTTON_5 / the Q4 secondary-input path and restores stock Z zoom semantics.
V18R then applies the live-test polish: Raven-style guided slowdown/re-accel,
180-degree marker orientation correction, and a soft shadowless target light.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()

# Weapon.h helper declaration whitespace.
hpath = root / "neo" / "game" / "Weapon.h"
htext = hpath.read_text(encoding="utf-8-sig")
hlines = htext.splitlines(True)
hindices = [i for i, line in enumerate(hlines) if "UpdateFlashPosition" in line and ";" in line]
if len(hindices) != 1:
    raise SystemExit(f"ERROR: expected exactly one UpdateFlashPosition declaration, found {len(hindices)}")
i = hindices[0]
newline = "\r\n" if hlines[i].endswith("\r\n") else "\n"
hlines[i] = "\tvoid\t\t\t\t\t\tUpdateFlashPosition( void );" + newline
hpath.write_text("".join(hlines), encoding="utf-8", newline="")

# Weapon.cpp has one constructor memset and, after V18D, another legitimate
# presentation-time reset. V18P must inject its q4 render-entity memsets only in
# the constructor. The constructor occurrence is the first one in source order.
wpath = root / "neo" / "game" / "Weapon.cpp"
wtext = wpath.read_text(encoding="utf-8-sig")
needle = "\tmemset( &nozzleGlow, 0, sizeof( nozzleGlow ) );"
positions = []
start = 0
while True:
    pos = wtext.find(needle, start)
    if pos < 0:
        break
    positions.append(pos)
    start = pos + len(needle)
if len(positions) < 1:
    raise SystemExit("ERROR: no nozzleGlow memset found for V18P constructor anchor")

# Preserve the first (constructor) occurrence byte-for-byte; make later
# occurrences semantically identical but textually distinct so replace_once is
# deterministic.
parts = []
cursor = 0
for n, pos in enumerate(positions):
    parts.append(wtext[cursor:pos])
    if n == 0:
        parts.append(needle)
    else:
        parts.append("\tmemset(&nozzleGlow, 0, sizeof(nozzleGlow));")
    cursor = pos + len(needle)
parts.append(wtext[cursor:])
wtext = "".join(parts)

if wtext.count(needle) != 1:
    raise SystemExit(f"ERROR: V18P nozzleGlow constructor anchor normalization left {wtext.count(needle)} exact matches")
wpath.write_text(wtext, encoding="utf-8", newline="")

# Chain V18Q + V18R after V18P without duplicating the large cumulative workflow.
v18p_path = root / "q4bse_port" / "apply_q4bse_v18p_rocket_guidance_laser.py"
v18q_path = root / "q4bse_port" / "apply_q4bse_v18q_mouse2_guidance.py"
v18r_path = root / "q4bse_port" / "apply_q4bse_v18r_rocket_guidance_polish.py"
if not v18p_path.exists() or not v18q_path.exists() or not v18r_path.exists():
    raise SystemExit("ERROR: V18P/V18Q/V18R guidance patch source missing")

v18p_text = v18p_path.read_text(encoding="utf-8-sig")
hook_marker = "# V18Q_CHAIN_MOUSE2_GUIDANCE"
if hook_marker not in v18p_text:
    v18p_text += '''\n\n# V18Q_CHAIN_MOUSE2_GUIDANCE\n# Live-test correction: after V18P has installed the working guidance system,\n# move it from Doom 3 BUTTON_ZOOM to the Q4 Mouse2/secondary transport and\n# restore normal Z zoom semantics.\nimport runpy\nrunpy.run_path(str(ROOT / "q4bse_port" / "apply_q4bse_v18q_mouse2_guidance.py"), run_name="__main__")\n# V18R_GUIDANCE_POLISH\n# Apply Q4 guided-speed parity, marker orientation fix and target illumination.\nrunpy.run_path(str(ROOT / "q4bse_port" / "apply_q4bse_v18r_rocket_guidance_polish.py"), run_name="__main__")\n'''
else:
    # Defensive support for a workspace copy that already had V18Q chained.
    r_marker = "# V18R_GUIDANCE_POLISH"
    if r_marker not in v18p_text:
        v18p_text += '''\n# V18R_GUIDANCE_POLISH\nrunpy.run_path(str(ROOT / "q4bse_port" / "apply_q4bse_v18r_rocket_guidance_polish.py"), run_name="__main__")\n'''

v18p_path.write_text(v18p_text, encoding="utf-8", newline="")

print("V18P cumulative anchors normalized:")
print("  - Weapon.h UpdateFlashPosition declaration")
print("  - Weapon.cpp constructor nozzleGlow memset is the sole exact match")
print("  - V18Q Mouse2 guidance correction chained after V18P")
print("  - V18R speed/orientation/light polish chained after V18Q")
