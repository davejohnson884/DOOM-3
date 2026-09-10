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

patch_exact(Path("neo/TypeInfo/main.cpp"), [
    ('idStr( "../"SOURCE_CODE_BASE_FOLDER"/" )',
     'idStr( "../" SOURCE_CODE_BASE_FOLDER "/" )'),
    ('"../"SOURCE_CODE_BASE_FOLDER"/game"',
     '"../" SOURCE_CODE_BASE_FOLDER "/game"'),
    ('"../"SOURCE_CODE_BASE_FOLDER"/game/gamesys/GameTypeInfo.h"',
     '"../" SOURCE_CODE_BASE_FOLDER "/game/gamesys/GameTypeInfo.h"'),
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

print("VS2022 compatibility pass complete.")
