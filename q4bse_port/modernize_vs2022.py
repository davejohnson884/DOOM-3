#!/usr/bin/env python3
"""Behavior-neutral source compatibility fixes for building the 2011 Doom 3 GPL tree with VS2022.

Keep this separate from Q4BSE runtime code. These edits only repair legacy
compiler/CRT assumptions in the original GPL tree so the Game DLL can be built
with a modern Win32 toolchain.
"""
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()


def patch_exact(relpath, replacements):
    p = ROOT / relpath
    if not p.exists():
        raise SystemExit(f"ERROR: missing {p}")
    text = p.read_text(encoding="utf-8-sig")
    changed = 0
    for old, new in replacements:
        if old in text:
            text = text.replace(old, new)
            changed += 1
        elif new not in text:
            raise SystemExit(f"ERROR: compatibility anchor not found in {relpath}: {old}")
    p.write_text(text, encoding="utf-8")
    print(f"VS2022 compatibility: {relpath}: {changed} replacement group(s) applied")


# C++11 introduced user-defined string literal suffixes. The VS2010-era source
# omitted whitespace between adjacent string literals and macros in a few places.
patch_exact(Path("neo/idlib/math/Simd.cpp"), [
    ('idLib::common->Printf( "   simd->Memcpy() "S_COLOR_RED"X\\n" );',
     'idLib::common->Printf( "   simd->Memcpy() " S_COLOR_RED "X\\n" );'),
    ('idLib::common->Printf( "   simd->Memset() "S_COLOR_RED"X\\n" );',
     'idLib::common->Printf( "   simd->Memset() " S_COLOR_RED "X\\n" );'),
])

patch_exact(Path("neo/game/gamesys/SysCmds.cpp"), [
    ('gameLocal.Printf( "\\\"%s\\\"  "S_COLOR_WHITE"\\\"%s\\\"\\n", kv->GetKey().c_str(), kv->GetValue().c_str() );',
     'gameLocal.Printf( "\\\"%s\\\"  " S_COLOR_WHITE "\\\"%s\\\"\\n", kv->GetKey().c_str(), kv->GetValue().c_str() );'),
])

# TypeInfo intentionally turns private/protected into public so its generated
# inspection code can reach arbitrary game members. Modern MSVC's STL rejects
# keyword macros unless this explicit compatibility opt-in is present. Access
# specifiers do not affect object layout, so this preserves the original hack.
patch_exact(Path("neo/game/gamesys/TypeInfo.cpp"), [
    ('// This is real evil but allows the code to inspect arbitrary class variables.\n#define private\t\tpublic\n#define protected\tpublic',
     '// This is real evil but allows the code to inspect arbitrary class variables.\n#define _ALLOW_KEYWORD_MACROS\n#define private\t\tpublic\n#define protected\tpublic'),
])

# Modern GitHub checkout paths contain "DOOM-3". The original TypeInfo helper
# searched for the substring "Doom" and truncated the working directory there,
# which turns D:\\a\\DOOM-3\\DOOM-3 into D:\\a\\DOOM. Keep the original fallback
# for old local layouts, but first accept the current working directory when it
# actually contains the source-code folder.
patch_exact(Path("neo/TypeInfo/main.cpp"), [
    ('idStr( "../"SOURCE_CODE_BASE_FOLDER"/" )',
     'idStr( "../" SOURCE_CODE_BASE_FOLDER "/" )'),
    ('"../"SOURCE_CODE_BASE_FOLDER"/game"',
     '"../" SOURCE_CODE_BASE_FOLDER "/game"'),
    ('"../"SOURCE_CODE_BASE_FOLDER"/game/gamesys/GameTypeInfo.h"',
     '"../" SOURCE_CODE_BASE_FOLDER "/game/gamesys/GameTypeInfo.h"'),
    ('\tint i = idStr::FindText( cwd, CD_BASEDIR, false );\n\tif ( i >= 0 ) {\n\t\tcwd[i + strlen( CD_BASEDIR )] = \'\\0\';\n\t}\n\n\treturn cwd;',
     '\tidStr sourceRoot = cwd;\n\tsourceRoot += "\\\\";\n\tsourceRoot += SOURCE_CODE_BASE_FOLDER;\n\tif ( _access( sourceRoot.c_str(), 0 ) == 0 ) {\n\t\treturn cwd;\n\t}\n\n\tint i = idStr::FindText( cwd, CD_BASEDIR, false );\n\tif ( i >= 0 ) {\n\t\tcwd[i + strlen( CD_BASEDIR )] = \'\\0\';\n\t}\n\n\treturn cwd;'),
])

patch_exact(Path("neo/TypeInfo/TypeInfoGen.cpp"), [
    ('"Type Info Generator v"TYPE_INFO_GEN_VERSION" (c) 2004 id Software\\n"',
     '"Type Info Generator v" TYPE_INFO_GEN_VERSION " (c) 2004 id Software\\n"'),
    ('"\\tThis file has been generated with the Type Info Generator v"TYPE_INFO_GEN_VERSION" (c) 2004 id Software\\n"',
     '"\\tThis file has been generated with the Type Info Generator v" TYPE_INFO_GEN_VERSION " (c) 2004 id Software\\n"'),
])

# Modern UCRT makes FILE opaque; use the supported descriptor accessor rather
# than reaching into the old MSVCRT FILE::_file implementation detail.
patch_exact(Path("neo/framework/FileSystem.cpp"), [
    ('static_cast<idFile_Permanent*>(bgl->f)->GetFilePtr()->_file',
     '_fileno( static_cast<idFile_Permanent*>(bgl->f)->GetFilePtr() )'),
])

# The GPL source release does not include the retail Doom 3 base assets, but the
# legacy TypeInfo build helper initializes idFileSystem and insists that a
# base/default.cfg exists before it scans the C++ tree. An empty build-only stub
# is sufficient; it is created in the CI working tree and is never committed.
base_dir = ROOT / "base"
base_dir.mkdir(exist_ok=True)
default_cfg = base_dir / "default.cfg"
if not default_cfg.exists():
    default_cfg.write_text("// Build-only stub for the GPL TypeInfo generator.\n", encoding="ascii")
    print(f"VS2022 compatibility: created build-only {default_cfg}")

print("VS2022 compatibility pass complete.")
