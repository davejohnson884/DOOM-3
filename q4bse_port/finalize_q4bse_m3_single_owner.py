#!/usr/bin/env python3
"""Finalize the M3 build so exactly one implementation owns q4bse_m3_impact.

The compressed Q4BSEDoom3.cpp payload predates the split Q4BSEImpactM3.cpp runtime and
still contains an older monolithic M3 command.  apply_q4bse_m1.py also compiles and
initializes the newer Q4BSEImpactM3.cpp implementation.  Leaving both command names
alive makes idCmdSystem registration order decide which implementation receives
q4bse_m3_impact; retail testing showed the obsolete monolithic path was winning.

This build-time cleanup keeps the legacy code dormant/diagnostic-only and makes the
split Q4BSEImpactM3.cpp implementation the sole owner of the public command.
"""
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
DOOM3 = ROOT / "neo" / "game" / "q4bse" / "Q4BSEDoom3.cpp"
IMPACT = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"

for path in (DOOM3, IMPACT):
    if not path.exists():
        raise SystemExit(f"ERROR: required generated source missing: {path}")

legacy = DOOM3.read_text(encoding="utf-8-sig")
impact = IMPACT.read_text(encoding="utf-8-sig")

# The generated Q4BSEDoom3.cpp payload contains the obsolete command text.  Rename every
# occurrence in that TU so it cannot collide with the split runtime's public command.
legacy_hits = legacy.count("q4bse_m3_impact")
if legacy_hits < 1:
    raise SystemExit("ERROR: expected legacy monolithic q4bse_m3_impact text in Q4BSEDoom3.cpp")
legacy = legacy.replace("q4bse_m3_impact", "q4bse_m3_legacy_disabled")

# Promote the visible status fingerprint after the collision is removed.
if "V8 VISUAL_TRACE" not in legacy:
    raise SystemExit("ERROR: expected V8 fingerprint before V9 single-owner finalization")
legacy = legacy.replace("V8 VISUAL_TRACE", "V9 SINGLE_M3", 1)

if "q4bse_m3_impact" in legacy:
    raise SystemExit("ERROR: public M3 command name still exists in legacy Q4BSEDoom3.cpp")

# The split implementation must own the public command exactly once.
public_registration = 'cmdSystem->AddCommand("q4bse_m3_impact", Cmd_M3Impact'
if impact.count(public_registration) != 1:
    raise SystemExit(
        f"ERROR: expected one public M3 registration in Q4BSEImpactM3.cpp, found {impact.count(public_registration)}"
    )

# Add a command-entry marker before any trace, table, decal, particle, or render work.
cmd_marker = "static void Cmd_M3Impact(const idCmdArgs& args) {\n"
cmd_trace = (
    cmd_marker
    + '    common->Printf("Q4BSE M3 TRACE: Cmd_M3Impact V9 SINGLE OWNER\\n");\n'
)
if impact.count(cmd_marker) != 1:
    raise SystemExit(f"ERROR: expected one Cmd_M3Impact entry, found {impact.count(cmd_marker)}")
impact = impact.replace(cmd_marker, cmd_trace, 1)

# Keep the V8 engine-boundary traces; they are still useful once the correct command
# implementation is actually receiving console dispatch.
for required in (
    "Q4BSE M3 TRACE: StartImpactAt BEGIN",
    "Q4BSE M3 TRACE: decal ProjectDecalOntoWorld BEGIN",
    "Q4BSE M3 TRACE: decal ProjectDecalOntoWorld END",
    "Q4BSE M3 TRACE: RebuildImpactModel(0) BEGIN",
    "Q4BSE M3 TRACE: AddEntityDef BEGIN",
):
    if required not in impact:
        raise SystemExit(f"ERROR: required visual trace marker missing: {required}")

# BSE does not own audio in the split runtime.
for forbidden in ("->UpdateEmitter(", "AllocSoundEmitter(", "StartSoundShader(", "->StartSound("):
    if forbidden in impact:
        raise SystemExit(f"ERROR: forbidden BSE-owned sound call remains: {forbidden}")

DOOM3.write_text(legacy, encoding="utf-8")
IMPACT.write_text(impact, encoding="utf-8")

print(f"Q4BSE M3 V9 single-owner cleanup PASS: renamed {legacy_hits} legacy command-text occurrence(s).")
print("Q4BSE M3 V9 public command owner: Q4BSEImpactM3.cpp only.")
print("Q4BSE M3 V9 entry trace installed before any effect work.")
print("Q4BSE M3 V9 audio architecture PASS: BSE visual runtime owns no Doom 3 sound calls.")
