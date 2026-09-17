#!/usr/bin/env python3
"""Compatibility wrapper for V18P on the cumulative V18O build chain.

The V18P patch historically matched one exact tab layout for the
UpdateFlashPosition declaration in Weapon.h. Earlier cumulative source passes
can preserve the declaration but normalize its whitespace, causing V18P to
abort before compilation. This wrapper normalizes only that declaration's
whitespace, then executes the original V18P patch unchanged.
"""

from pathlib import Path
import re
import runpy
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
weapon_h = ROOT / "neo" / "game" / "Weapon.h"
if not weapon_h.exists():
    raise SystemExit(f"ERROR: V18P compat prerequisite missing: {weapon_h}")

text = weapon_h.read_text(encoding="utf-8-sig")
pattern = re.compile(r"(?m)^[ \t]*void[ \t]+UpdateFlashPosition\([ \t]*void[ \t]*\);[ \t]*$")
matches = list(pattern.finditer(text))
if len(matches) != 1:
    raise SystemExit(f"ERROR: V18P compat expected one UpdateFlashPosition declaration, found {len(matches)}")

expected = "\tvoid\t\t\t\t\t\tUpdateFlashPosition( void );"
text = pattern.sub(expected, text, count=1)
weapon_h.write_text(text, encoding="utf-8")
print("V18P COMPAT: normalized Weapon.h UpdateFlashPosition anchor.")

original = ROOT / "q4bse_port" / "apply_q4bse_v18p_rocket_guidance_laser.py"
if not original.exists():
    raise SystemExit(f"ERROR: original V18P patch missing: {original}")

# Preserve argv exactly as the original patch expects.
sys.argv = [str(original), str(ROOT)]
runpy.run_path(str(original), run_name="__main__")
