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

# Do not manually own a raw idSoundEmitter for the M3 test sound.  Retail Doom 3
# 1.3.1 rejects a NULL UpdateEmitter parms pointer even though the public interface
# comment says NULL is acceptable.  Run #24 changed our explicit call to non-NULL,
# but the retail test still reached the same fatal path after the sound was started.
# Route M3 sound playback through idEntity::StartSoundShader instead: that is Doom 3's
# normal game-side ownership path and idEntity::UpdateSound always passes &refSound.parms.
# This milestone intentionally trades exact impact-position spatialization for a safe,
# owned emitter; a dedicated transient spatial sound proxy can be added after M3 visuals
# are stable.
impact_text = IMPACT.read_text(encoding="utf-8-sig")
sound_start_marker = "static void PlaySoundSegment(const q4bse::Segment& segment) {"
sound_end_marker = "static void ProjectDecalSegment(const q4bse::Segment& segment) {"
sound_start = impact_text.find(sound_start_marker)
sound_end = impact_text.find(sound_end_marker, sound_start + 1)
if sound_start < 0 or sound_end < 0 or sound_end <= sound_start:
    raise SystemExit("ERROR: could not locate M3 PlaySoundSegment block for retail-safe replacement")

new_sound = '''static void PlaySoundSegment(const q4bse::Segment& segment) {
    if (!gameSoundWorld || !declManager || segment.soundShader.empty()) return;
    const idSoundShader* shader = declManager->FindSound(segment.soundShader.c_str(), false);
    if (!shader) { common->Warning("Q4BSE M3: sound shader not found: %s", segment.soundShader.c_str()); return; }
    idPlayer* player = gameLocal.GetLocalPlayer();
    if (!player) { common->Warning("Q4BSE M3: no local player available for sound segment %s", segment.soundShader.c_str()); return; }
    int soundLengthMS = 0;
    if (!player->StartSoundShader(shader, SCHANNEL_ANY, 0, false, &soundLengthMS)) {
        common->Warning("Q4BSE M3: StartSoundShader failed for %s", segment.soundShader.c_str());
        return;
    }
    common->Printf("Q4BSE M3: sound %s started through owned idEntity emitter (%d ms)\\n",
                   segment.soundShader.c_str(), soundLengthMS);
}

'''
impact_text = impact_text[:sound_start] + new_sound + impact_text[sound_end:]

# Hard safety check: the M3 implementation must contain no direct raw UpdateEmitter
# calls after this replacement.  If one is added later, fail CI rather than shipping
# another retail crash.
if "->UpdateEmitter(" in impact_text:
    raise SystemExit("ERROR: unsafe direct UpdateEmitter call remains in Q4BSEImpactM3.cpp")

IMPACT.write_text(impact_text, encoding="utf-8")

print(f"Q4BSE M3 overlay applied: {len(source)} bytes -> {DEST}")
print("Q4BSE M3 retail sound crashfix v2 applied: sound now uses idEntity::StartSoundShader ownership.")
print("Q4BSE M3 sound safety check PASS: no direct UpdateEmitter calls remain in impact runtime.")
print("Architecture remains one ordinary source-built gamex86.dll; no wrapper or binary hook.")
