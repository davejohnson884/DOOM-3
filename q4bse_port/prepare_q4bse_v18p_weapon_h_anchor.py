#!/usr/bin/env python3
"""Normalize cumulative source anchors expected by the strict V18P patch.

Prior Q4BSE patches preserve these declarations/initializers semantically but can
introduce either whitespace drift or another identical nozzleGlow memset in the
V18D presentation path.  V18P intentionally remains strict everywhere else.
This prep step only canonicalizes the unique declaration and makes the weapon
constructor's nozzleGlow memset the sole exact V18P constructor anchor.
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

print("V18P cumulative anchors normalized:")
print("  - Weapon.h UpdateFlashPosition declaration")
print("  - Weapon.cpp constructor nozzleGlow memset is the sole exact match")
