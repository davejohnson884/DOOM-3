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
IMPACT = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"

if not ENCODED.exists():
    raise SystemExit(f"ERROR: missing M3 source payload: {ENCODED}")
if not DEST.exists():
    raise SystemExit(f"ERROR: M1 integration must run first; missing {DEST}")
if not IMPACT.exists():
    raise SystemExit(f"ERROR: M1 integration must copy M3 impact source first; missing {IMPACT}")

try:
    packed = base64.b64decode(ENCODED.read_text(encoding="ascii").strip(), validate=True)
    source = zlib.decompress(packed)
except Exception as exc:
    raise SystemExit(f"ERROR: could not decode M3 source payload: {exc}")

if b'q4bse_m3_impact' not in source or b'Q4BSE M3' not in source:
    raise SystemExit("ERROR: decoded M3 source failed sanity check")

DEST.write_bytes(source)

# Retail Doom 3's idSoundEmitterLocal::UpdateEmitter requires a non-null
# soundShaderParms_t pointer.  The first M3 pass passed NULL and retail 1.3.1
# correctly aborted with "idSoundEmitterLocal::UpdateEmitter: NULL parms".
# Keep the Raven sound segment path intact, but provide neutral emitter parms.
impact_text = IMPACT.read_text(encoding="utf-8-sig")
old_sound = "    emitter->UpdateEmitter(g_m3Impact.origin, player ? player->GetListenerId() : 0, NULL);"
new_sound = (
    "    soundShaderParms_t emitterParms;\n"
    "    memset(&emitterParms, 0, sizeof(emitterParms));\n"
    "    emitter->UpdateEmitter(g_m3Impact.origin, player ? player->GetListenerId() : 0, &emitterParms);"
)
hits = impact_text.count(old_sound)
if hits != 1:
    raise SystemExit(f"ERROR: expected exactly one unsafe M3 sound UpdateEmitter anchor, found {hits}")
impact_text = impact_text.replace(old_sound, new_sound, 1)
IMPACT.write_text(impact_text, encoding="utf-8")

print(f"Q4BSE M3 overlay applied: {len(source)} bytes -> {DEST}")
print("Q4BSE M3 retail sound crashfix applied: UpdateEmitter now receives valid neutral parms.")
print("Architecture remains one ordinary source-built gamex86.dll; no wrapper or binary hook.")
