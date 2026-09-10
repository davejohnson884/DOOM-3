#!/usr/bin/env python3
"""Overlay the source-integrated M3 HyperBlaster impact runtime after M1 integration."""
from pathlib import Path
import base64
import sys
import zlib

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
HERE = Path(__file__).resolve().parent
ENCODED = HERE / "source_m3" / "Q4BSEDoom3.cpp.zlib.b64"
DEST = ROOT / "neo" / "game" / "q4bse" / "Q4BSEDoom3.cpp"

if not ENCODED.exists():
    raise SystemExit(f"ERROR: missing M3 source payload: {ENCODED}")
if not DEST.exists():
    raise SystemExit(f"ERROR: M1 integration must run first; missing {DEST}")

try:
    packed = base64.b64decode(ENCODED.read_text(encoding="ascii").strip(), validate=True)
    source = zlib.decompress(packed)
except Exception as exc:
    raise SystemExit(f"ERROR: could not decode M3 source payload: {exc}")

if b'q4bse_m3_impact' not in source or b'Q4BSE M3' not in source:
    raise SystemExit("ERROR: decoded M3 source failed sanity check")

DEST.write_bytes(source)
print(f"Q4BSE M3 overlay applied: {len(source)} bytes -> {DEST}")
print("Architecture remains one ordinary source-built gamex86.dll; no wrapper or binary hook.")
