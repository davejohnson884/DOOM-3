#!/usr/bin/env python3
"""Compatibility wrapper for V18P on the cumulative V18O build chain.

V18P was originally written against a single exact text layout. The cumulative
source chain now leaves a couple of semantically-identical duplicate anchors in
Weapon.cpp/Weapon.h, so V18P can abort before compilation even though the code
it wants to patch is present. This wrapper makes only whitespace-equivalent
normalizations so the original V18P patch can run unchanged.
"""

from pathlib import Path
import re
import runpy
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
weapon_h = ROOT / "neo" / "game" / "Weapon.h"
weapon_cpp = ROOT / "neo" / "game" / "Weapon.cpp"
for p in (weapon_h, weapon_cpp):
    if not p.exists():
        raise SystemExit(f"ERROR: V18P compat prerequisite missing: {p}")

# 1) Normalize the helper declaration to the exact legacy V18P anchor.
text = weapon_h.read_text(encoding="utf-8-sig")
pattern = re.compile(r"(?m)^[ \t]*void[ \t]+UpdateFlashPosition\([ \t]*void[ \t]*\);[ \t]*$")
matches = list(pattern.finditer(text))
if len(matches) != 1:
    raise SystemExit(f"ERROR: V18P compat expected one UpdateFlashPosition declaration, found {len(matches)}")
expected = "\tvoid\t\t\t\t\t\tUpdateFlashPosition( void );"
text = pattern.sub(expected, text, count=1)
weapon_h.write_text(text, encoding="utf-8")
print("V18P COMPAT: normalized Weapon.h UpdateFlashPosition anchor.")

# 2) V18P's constructor memset anchor now appears twice in the cumulative file.
# Keep the FIRST occurrence byte-for-byte (the constructor one) and change only
# later occurrences to equivalent C++ whitespace so replace_once sees one hit.
weapon = weapon_cpp.read_text(encoding="utf-8-sig")
legacy_memset = "\tmemset( &nozzleGlow, 0, sizeof( nozzleGlow ) );"
count = weapon.count(legacy_memset)
if count < 1:
    raise SystemExit("ERROR: V18P compat could not find nozzleGlow memset anchor")
if count > 1:
    first = weapon.find(legacy_memset)
    head = weapon[: first + len(legacy_memset)]
    tail = weapon[first + len(legacy_memset):]
    tail = tail.replace(legacy_memset, "\tmemset( &nozzleGlow, 0, sizeof(nozzleGlow) );")
    weapon = head + tail
    print(f"V18P COMPAT: reduced nozzleGlow memset anchor from {count} hits to 1 via whitespace-only normalization.")
weapon_cpp.write_text(weapon, encoding="utf-8")

original = ROOT / "q4bse_port" / "apply_q4bse_v18p_rocket_guidance_laser.py"
if not original.exists():
    raise SystemExit(f"ERROR: original V18P patch missing: {original}")

sys.argv = [str(original), str(ROOT)]
runpy.run_path(str(original), run_name="__main__")
