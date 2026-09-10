#!/usr/bin/env python3
"""Apply the source-integrated Q4BSE runtime to a clean Doom 3 GPL tree.

The result is one ordinary Win32 Game DLL with the Raven-FX parser/runtime
compiled directly into it.  No wrapper DLL, forwarding DLL, vtable patch,
binary detour, or Phrozo dependency is introduced.
"""
from pathlib import Path
import shutil
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
HERE = Path(__file__).resolve().parent
NEO = ROOT / "neo"
GAME = NEO / "game"
LOCAL = GAME / "Game_local.cpp"
PROJ = NEO / "game.vcxproj"
SIMD = NEO / "idlib" / "math" / "Simd.cpp"
SRC = HERE / "source" / "neo" / "game" / "q4bse"
DST = GAME / "q4bse"

for p in (LOCAL, PROJ, SIMD):
    if not p.exists():
        raise SystemExit(f"ERROR: {p} not found. Pass the root of a clean id-Software/DOOM-3 GPL tree.")

if not SRC.exists():
    raise SystemExit(f"ERROR: package source folder missing: {SRC}")

DST.mkdir(parents=True, exist_ok=True)
for src in SRC.iterdir():
    if src.is_file():
        shutil.copy2(src, DST / src.name)

# M3 dynamic quads use proper four-corner geometry.  The first M3 draft used
# the four axis extrema (left/down/right/up), which produces a diamond and
# halves the authored sprite/oriented surface area.  Patch the copied source
# before compilation so the retail test DLL gets the correct corners.
m3_cpp = DST / "Q4BSEImpactM3.cpp"
if m3_cpp.exists():
    m3_text = m3_cpp.read_text(encoding="utf-8-sig")
    old_quad = 'idVec3 points[4] = { worldPos - right, worldPos - up, worldPos + right, worldPos + up };'
    new_quad = 'idVec3 points[4] = { worldPos - right - up, worldPos - right + up, worldPos + right + up, worldPos + right - up };'
    hits = m3_text.count(old_quad)
    if hits != 2:
        raise SystemExit(f"ERROR: expected 2 M3 quad-geometry anchors, found {hits}")
    m3_text = m3_text.replace(old_quad, new_quad)
    m3_cpp.write_text(m3_text, encoding="utf-8")

for p in (LOCAL, PROJ, SIMD):
    bak = p.with_suffix(p.suffix + ".q4bse_m1.bak")
    if not bak.exists():
        shutil.copy2(p, bak)

# Modern MSVC compatibility for two 2011-era adjacent string/macro tokens.
simd_text = SIMD.read_text(encoding="utf-8-sig")
old_memcpy = 'idLib::common->Printf( "   simd->Memcpy() "S_COLOR_RED"X\\n" );'
new_memcpy = 'idLib::common->Printf( "   simd->Memcpy() " S_COLOR_RED "X\\n" );'
old_memset = 'idLib::common->Printf( "   simd->Memset() "S_COLOR_RED"X\\n" );'
new_memset = 'idLib::common->Printf( "   simd->Memset() " S_COLOR_RED "X\\n" );'
if old_memcpy in simd_text:
    simd_text = simd_text.replace(old_memcpy, new_memcpy, 1)
elif new_memcpy not in simd_text:
    raise SystemExit("ERROR: Simd.cpp Memcpy compatibility anchor not found")
if old_memset in simd_text:
    simd_text = simd_text.replace(old_memset, new_memset, 1)
elif new_memset not in simd_text:
    raise SystemExit("ERROR: Simd.cpp Memset compatibility anchor not found")
SIMD.write_text(simd_text, encoding="utf-8")

text = LOCAL.read_text(encoding="utf-8-sig")

# 1) Headers for the proven M1/M2 diagnostic path and the M3 full-impact path.
anchor = '#include "Game_local.h"'
include_m2 = '#include "q4bse/Q4BSEDoom3.h"'
include_m3 = '#include "q4bse/Q4BSEImpactM3.h"'
if include_m2 not in text or include_m3 not in text:
    if anchor not in text:
        raise SystemExit("ERROR: Game_local.cpp include anchor not found")
    block = anchor
    if include_m2 not in text:
        block += "\n" + include_m2
    if include_m3 not in text:
        block += "\n" + include_m3
    text = text.replace(anchor, block, 1)

# 2) One-time subsystem initialization after normal game console commands exist.
anchor = "\tInitConsoleCommands();"
call_m2 = "\tQ4BSE_Init();"
call_m3 = "\tQ4BSE_M3_Init();"
if call_m2 not in text or call_m3 not in text:
    if anchor not in text:
        raise SystemExit("ERROR: InitConsoleCommands anchor not found")
    block = anchor + "\n\n\t// Q4BSE: source-integrated Raven FX runtimes.\n"
    if call_m2 not in text:
        block += call_m2 + "\n"
    if call_m3 not in text:
        block += call_m3
    text = text.replace(anchor, block.rstrip(), 1)

# 3) Shutdown before game commands are removed. M3 is torn down before M2.
anchor = "\tShutdownConsoleCommands();"
call_m3 = "\tQ4BSE_M3_Shutdown();"
call_m2 = "\tQ4BSE_Shutdown();"
if call_m3 not in text or call_m2 not in text:
    if anchor not in text:
        raise SystemExit("ERROR: ShutdownConsoleCommands anchor not found")
    block = "\t// Q4BSE: release runtime objects and commands.\n"
    if call_m3 not in text:
        block += call_m3 + "\n"
    if call_m2 not in text:
        block += call_m2 + "\n"
    block += "\n" + anchor
    text = text.replace(anchor, block, 1)

# 4) Map-begin parser/runtime load. Scope search to InitFromNewMap.
call_m2 = "\tQ4BSE_BeginMap();"
call_m3 = "\tQ4BSE_M3_BeginMap();"
if call_m2 not in text or call_m3 not in text:
    fn = 'void idGameLocal::InitFromNewMap( const char *mapName, idRenderWorld *renderWorld, idSoundWorld *soundWorld, bool isServer, bool isClient, int randseed ) {'
    pos = text.find(fn)
    if pos < 0:
        fn2 = 'void idGameLocal::InitFromNewMap( const char *mapName, idRenderWorld *renderWorld, idSoundWorld *soundWorld, bool isServer, bool isClient, int randSeed ) {'
        pos = text.find(fn2)
    if pos < 0:
        raise SystemExit("ERROR: InitFromNewMap signature not found")
    a = text.find("\tMapPopulate();", pos)
    if a < 0:
        raise SystemExit("ERROR: MapPopulate anchor not found inside InitFromNewMap")
    a += len("\tMapPopulate();")
    block = "\n\n\t// Q4BSE: parse real Raven .fx via the normal Doom 3 VFS.\n"
    if call_m2 not in text:
        block += call_m2 + "\n"
    if call_m3 not in text:
        block += call_m3
    text = text[:a] + block.rstrip() + text[a:]

# 5) Map-end cleanup. Safe to call more than once.
call_m3 = "\tQ4BSE_M3_EndMap();"
call_m2 = "\tQ4BSE_EndMap();"
if call_m3 not in text or call_m2 not in text:
    sig = "void idGameLocal::MapShutdown( void ) {"
    pos = text.find(sig)
    if pos < 0:
        raise SystemExit("ERROR: MapShutdown signature not found")
    pos += len(sig)
    block = "\n\t// Q4BSE: free source-integrated runtime render objects first.\n"
    if call_m3 not in text:
        block += call_m3 + "\n"
    if call_m2 not in text:
        block += call_m2
    text = text[:pos] + block.rstrip() + text[pos:]

# 6) Service both runtimes from the ordinary game frame, no engine/vtable hooks.
call_m2 = "\tQ4BSE_Frame( time );"
call_m3 = "\tQ4BSE_M3_Frame( time );"
if call_m2 not in text or call_m3 not in text:
    run = text.find("gameReturn_t idGameLocal::RunFrame( const usercmd_t *clientCmds ) {")
    if run < 0:
        raise SystemExit("ERROR: RunFrame signature not found")
    anchor = "\t// show any debug info for this frame"
    a = text.find(anchor, run)
    if a < 0:
        raise SystemExit("ERROR: RunFrame debug-info anchor not found")
    block = "\t// Q4BSE: service live BSE instances from the ordinary Game DLL frame.\n"
    if call_m2 not in text:
        block += call_m2 + "\n"
    if call_m3 not in text:
        block += call_m3 + "\n"
    block += "\n"
    text = text[:a] + block + text[a:]

LOCAL.write_text(text, encoding="utf-8")

xml = PROJ.read_text(encoding="utf-8-sig")
compile_files = [
    r"game\q4bse\Q4FxParser.cpp",
    r"game\q4bse\Q4BSECore.cpp",
    r"game\q4bse\Q4BSEDoom3.cpp",
    r"game\q4bse\Q4BSEImpactM3.cpp",
]
include_files = [
    r"game\q4bse\Q4FxParser.h",
    r"game\q4bse\Q4BSECore.h",
    r"game\q4bse\Q4BSEDoom3.h",
    r"game\q4bse\Q4BSEImpactM3.h",
]

compile_anchor = '    <ClCompile Include="game\\Game_local.cpp" />'
for path in compile_files:
    entry = f'    <ClCompile Include="{path}" />'
    if path not in xml:
        if compile_anchor not in xml:
            raise SystemExit("ERROR: game.vcxproj Game_local.cpp compile anchor not found")
        xml = xml.replace(compile_anchor, compile_anchor + "\n" + entry, 1)

include_anchor = '    <ClInclude Include="game\\Game_local.h" />'
for path in include_files:
    entry = f'    <ClInclude Include="{path}" />'
    if path not in xml:
        if include_anchor not in xml:
            raise SystemExit("ERROR: game.vcxproj Game_local.h include anchor not found")
        xml = xml.replace(include_anchor, include_anchor + "\n" + entry, 1)

PROJ.write_text(xml, encoding="utf-8")

print("Q4BSE source integration patch applied through M3 full-impact runtime.")
print("Applied two behavior-neutral VS2022 compatibility fixes to idlib/math/Simd.cpp.")
print("Applied M3 four-corner sprite/oriented geometry correction.")
print("No wrapper DLL, forwarding DLL, vtable patch, binary detour, or Phrozo dependency was added.")
print("Build neo\\game.vcxproj -> Release | Win32.")
