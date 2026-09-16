#!/usr/bin/env python3
"""Normalize cumulative source anchors expected by the strict V18P patch.

Prior Q4BSE patches preserve these declarations/initializers semantically but can
introduce either whitespace drift or another identical nozzleGlow memset in the
V18D presentation path.  V18P intentionally remains strict everywhere else.
This prep step only canonicalizes the unique declaration and makes the weapon
constructor's nozzleGlow memset the sole exact V18P constructor anchor.

V18Q follow-up:
The first live guidance test proved the steering/beam/marker path works, but it
also proved V18P used Doom 3 BUTTON_ZOOM (Z) rather than the Q4 secondary input
used by the existing Mouse2 weapon functions.  This prep step therefore chains
the dedicated V18Q post-patch immediately after V18P executes.  That keeps this
existing cumulative workflow intact while restoring stock Doom 3 Z zoom and
moving guidance to BUTTON_5 / the Q4 secondary-input path.
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

# Chain V18Q after V18P without duplicating the large cumulative workflow.
# This edits only the checked-out workspace copy of the patch script; the repo
# source remains modular (V18P + V18Q) and the final game source receives V18Q
# only after V18P has created the guidance code it corrects.
v18p_path = root / "q4bse_port" / "apply_q4bse_v18p_rocket_guidance_laser.py"
v18q_path = root / "q4bse_port" / "apply_q4bse_v18q_mouse2_guidance.py"
if not v18p_path.exists() or not v18q_path.exists():
    raise SystemExit("ERROR: V18P/V18Q guidance patch source missing")

v18p_text = v18p_path.read_text(encoding="utf-8-sig")
hook_marker = "# V18Q_CHAIN_MOUSE2_GUIDANCE"
if hook_marker not in v18p_text:
    v18p_text += '''\n\n# V18Q_CHAIN_MOUSE2_GUIDANCE\n# Live-test correction: after V18P has installed the working guidance system,\n# move it from Doom 3 BUTTON_ZOOM to the Q4 Mouse2/secondary transport and\n# restore normal Z zoom semantics.\nimport runpy\nrunpy.run_path(str(ROOT / "q4bse_port" / "apply_q4bse_v18q_mouse2_guidance.py"), run_name="__main__")\n'''
    v18p_path.write_text(v18p_text, encoding="utf-8", newline="")

print("V18P cumulative anchors normalized:")
print("  - Weapon.h UpdateFlashPosition declaration")
print("  - Weapon.cpp constructor nozzleGlow memset is the sole exact match")
print("  - V18Q Mouse2 guidance correction chained after V18P")
