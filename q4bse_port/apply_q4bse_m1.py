#!/usr/bin/env python3
"""Apply Q4BSE M1 to a clean id-Software/DOOM-3 GPL source tree.

This patch is intentionally source-only.  It creates one normal Game DLL with
Q4BSE code compiled inside it.  It does NOT wrap, forward to, patch, or load
Phrozo or any other game DLL.
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
SRC = HERE / "source" / "neo" / "game" / "q4bse"
DST = GAME / "q4bse"

for p in (LOCAL, PROJ):
    if not p.exists():
        raise SystemExit(f"ERROR: {p} not found. Pass the root of a clean id-Software/DOOM-3 GPL tree.")

if not SRC.exists():
    raise SystemExit(f"ERROR: package source folder missing: {SRC}")

DST.mkdir(parents=True, exist_ok=True)
for src in SRC.iterdir():
    if src.is_file():
        shutil.copy2(src, DST / src.name)

for p in (LOCAL, PROJ):
    bak = p.with_suffix(p.suffix + ".q4bse_m1.bak")
    if not bak.exists():
        shutil.copy2(p, bak)

text = LOCAL.read_text(encoding="utf-8-sig")

# 1) Header include.
anchor = '#include "Game_local.h"'
include = '#include "q4bse/Q4BSEDoom3.h"'
if include not in text:
    if anchor not in text:
        raise SystemExit("ERROR: Game_local.cpp include anchor not found")
    text = text.replace(anchor, anchor + "\n" + include, 1)

# 2) One-time subsystem initialization after normal game console commands exist.
anchor = "\tInitConsoleCommands();"
call = "\tQ4BSE_Init();"
if call not in text:
    if anchor not in text:
        raise SystemExit("ERROR: InitConsoleCommands anchor not found")
    text = text.replace(anchor, anchor + "\n\n\t// Q4BSE M1: source-integrated Raven FX subsystem.\n" + call, 1)

# 3) Shutdown before game commands are removed.
anchor = "\tShutdownConsoleCommands();"
call = "\tQ4BSE_Shutdown();"
if call not in text:
    if anchor not in text:
        raise SystemExit("ERROR: ShutdownConsoleCommands anchor not found")
    text = text.replace(anchor, "\t// Q4BSE M1: release render defs/models and commands.\n" + call + "\n\n" + anchor, 1)

# 4) Map-begin parser load.  Scope the search to InitFromNewMap to avoid a wrong MapPopulate.
call = "\tQ4BSE_BeginMap();"
if call not in text:
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
    text = text[:a] + "\n\n\t// Q4BSE M1: parse real Raven .fx via normal Doom 3 VFS.\n" + call + text[a:]

# 5) Map-end cleanup.  Safe to call more than once.
call = "\tQ4BSE_EndMap();"
if call not in text:
    sig = "void idGameLocal::MapShutdown( void ) {"
    pos = text.find(sig)
    if pos < 0:
        raise SystemExit("ERROR: MapShutdown signature not found")
    pos += len(sig)
    text = text[:pos] + "\n\t// Q4BSE M1: free source-integrated runtime render objects first.\n" + call + text[pos:]

# 6) Service runtime lifetime from the normal game frame, no engine/vtable hooks.
call = "\tQ4BSE_Frame( time );"
if call not in text:
    run = text.find("gameReturn_t idGameLocal::RunFrame( const usercmd_t *clientCmds ) {")
    if run < 0:
        raise SystemExit("ERROR: RunFrame signature not found")
    anchor = "\t// show any debug info for this frame"
    a = text.find(anchor, run)
    if a < 0:
        raise SystemExit("ERROR: RunFrame debug-info anchor not found")
    text = text[:a] + "\t// Q4BSE M1: service live BSE instances from the ordinary Game DLL frame.\n" + call + "\n\n" + text[a:]

LOCAL.write_text(text, encoding="utf-8")

xml = PROJ.read_text(encoding="utf-8-sig")
compile_files = [
    r"game\q4bse\Q4FxParser.cpp",
    r"game\q4bse\Q4BSECore.cpp",
    r"game\q4bse\Q4BSEDoom3.cpp",
]
include_files = [
    r"game\q4bse\Q4FxParser.h",
    r"game\q4bse\Q4BSECore.h",
    r"game\q4bse\Q4BSEDoom3.h",
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

print("Q4BSE M1 source integration patch applied.")
print("No wrapper DLL and no Phrozo dependency were added.")
print("Build neo\\doom.sln -> Game -> Release | Win32.")
