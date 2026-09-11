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

# Stamp this retail checkpoint directly into q4bse_status.  The runtime DLL is loaded
# from a PK4 and stale binaries are otherwise very easy to confuse during rapid testing.
status_marker = b'common->Printf("Q4BSE source-integrated M3 status:\\n");'
status_replacement = (
    status_marker
    + b'\n    common->Printf("  build fingerprint: V7 RETAIL_NOSOUND\\n");'
)
status_hits = source.count(status_marker)
if status_hits != 1:
    raise SystemExit(f"ERROR: expected exactly one M3 status marker, found {status_hits}")
source = source.replace(status_marker, status_replacement, 1)
DEST.write_bytes(source)

# RETAIL VISUAL CHECKPOINT V7
# ---------------------------
# Two independent attempts to play the parsed Raven sound segment have caused retail
# Doom 3 1.3.1 to abort in idSoundEmitterLocal::UpdateEmitter(NULL parms): first through
# a manually allocated idSoundEmitter, then through idEntity::StartSoundShader.  The
# latter path is safe in the GPL source but still reaches the retail fatal path, which
# strongly suggests this sound interface needs separate ABI/runtime investigation.
#
# Do not let audio prevent validation of the six visual M3 segments.  For V7 the parsed
# sound segment is deliberately retained and reported, but performs *zero* Doom 3 sound
# API calls.  Exact impact-position audio will be restored after the visual BSE runtime
# is stable.
impact_text = IMPACT.read_text(encoding="utf-8-sig")
sound_start_marker = "static void PlaySoundSegment(const q4bse::Segment& segment) {"
sound_end_marker = "static void ProjectDecalSegment(const q4bse::Segment& segment) {"
sound_start = impact_text.find(sound_start_marker)
sound_end = impact_text.find(sound_end_marker, sound_start + 1)
if sound_start < 0 or sound_end < 0 or sound_end <= sound_start:
    raise SystemExit("ERROR: could not locate M3 PlaySoundSegment block for V7 suppression")

new_sound = '''static void PlaySoundSegment(const q4bse::Segment& segment) {
    // V7 retail checkpoint: intentionally no sound API calls.  Keep the parsed Raven
    // segment visible in the log so execution order remains observable while the six
    // visual segments are validated independently of the retail sound interface.
    if (!segment.soundShader.empty()) {
        common->Printf("Q4BSE M3: sound segment SUPPRESSED (V7 RETAIL_NOSOUND): %s\\n",
                       segment.soundShader.c_str());
    } else {
        common->Printf("Q4BSE M3: empty sound segment SUPPRESSED (V7 RETAIL_NOSOUND)\\n");
    }
}

'''
impact_text = impact_text[:sound_start] + new_sound + impact_text[sound_end:]

# Hard V7 safety gates.  This checkpoint must be physically incapable of entering the
# Doom 3 sound-emitter path from Q4BSEImpactM3.cpp.  Fail CI rather than ship another
# binary that can reproduce the sound crash.
for forbidden in ("->UpdateEmitter(", "AllocSoundEmitter(", "StartSoundShader("):
    if forbidden in impact_text:
        raise SystemExit(f"ERROR: forbidden M3 retail sound call remains: {forbidden}")

IMPACT.write_text(impact_text, encoding="utf-8")

print(f"Q4BSE M3 overlay applied: {len(source)} bytes -> {DEST}")
print("Q4BSE M3 V7 fingerprint applied: RETAIL_NOSOUND.")
print("Q4BSE M3 V7 sound suppression applied: parsed sound segment makes zero sound API calls.")
print("Q4BSE M3 V7 sound safety gates PASS: no UpdateEmitter/AllocSoundEmitter/StartSoundShader calls remain.")
print("Architecture remains one ordinary source-built gamex86.dll; no wrapper or binary hook.")
