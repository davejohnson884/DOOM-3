#!/usr/bin/env python3
"""Normalize only the cumulative source anchors needed by V18P.

This is a clean replacement for the earlier build helper.  It deliberately does
NOT chain any follow-up patches into V18P; the V18S workflow runs V18Q and V18S
explicitly after V18P so the live-tested guidance path stays deterministic.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()

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

parts = []
cursor = 0
for n, pos in enumerate(positions):
    parts.append(wtext[cursor:pos])
    parts.append(needle if n == 0 else "\tmemset(&nozzleGlow, 0, sizeof(nozzleGlow));")
    cursor = pos + len(needle)
parts.append(wtext[cursor:])
wtext = "".join(parts)

if wtext.count(needle) != 1:
    raise SystemExit(f"ERROR: V18P nozzleGlow constructor anchor normalization left {wtext.count(needle)} exact matches")
wpath.write_text(wtext, encoding="utf-8", newline="")

print("V18S clean V18P anchor prep PASS.")
print("  - Weapon.h UpdateFlashPosition declaration canonicalized")
print("  - Weapon.cpp constructor nozzleGlow anchor made unique")
print("  - no V18Q/V18R/V18S patch chaining performed")
