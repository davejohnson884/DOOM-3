#!/usr/bin/env python3
"""Normalize the single Weapon.h helper declaration anchor expected by V18P.

Cumulative Q4BSE patches preserve the declaration semantically but can alter its
whitespace.  V18P intentionally remains strict everywhere else; this tiny prep
step only canonicalizes the unique UpdateFlashPosition declaration.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
path = root / "neo" / "game" / "Weapon.h"
text = path.read_text(encoding="utf-8-sig")
lines = text.splitlines(True)
indices = [i for i, line in enumerate(lines) if "UpdateFlashPosition" in line and ";" in line]
if len(indices) != 1:
    raise SystemExit(f"ERROR: expected exactly one UpdateFlashPosition declaration, found {len(indices)}")

i = indices[0]
newline = "\r\n" if lines[i].endswith("\r\n") else "\n"
lines[i] = "\tvoid\t\t\t\t\t\tUpdateFlashPosition( void );" + newline
path.write_text("".join(lines), encoding="utf-8", newline="")
print("V18P Weapon.h anchor normalized: UpdateFlashPosition declaration")
