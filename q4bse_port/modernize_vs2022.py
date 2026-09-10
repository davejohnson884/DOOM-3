#!/usr/bin/env python3
"""Behavior-neutral source compatibility fixes for building the 2011 Doom 3 GPL tree with VS2022.

Keep this separate from Q4BSE runtime code.  These edits only repair legacy token
concatenation accepted by the VS2010-era compiler but rejected by modern MSVC.
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

print("VS2022 compatibility pass complete.")
