#!/usr/bin/env python3
from pathlib import Path
import sys
p=Path(sys.argv[1]).resolve()/"neo"/"game"/"Weapon.h"
t=p.read_text(encoding="utf-8-sig")
for line in t.splitlines():
    if "UpdateFlashPosition" in line or "UpdateNozzleFx" in line:
        print(repr(line))
