#!/usr/bin/env python3
"""V20: accept Raven envelope/domain `count` modifiers used by Nailgun FX.

Runs after V19.  The count modifier controls Raven envelope repetition/frequency;
for Doom 3's visual bridge the envelope table itself is already evaluated, so
this compatibility pass consumes the authored numeric count vector instead of
rejecting the complete effect declaration.  It is intentionally parser-only.
"""
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PARSER_CPP = ROOT / "neo" / "game" / "q4bse" / "Q4FxParser.cpp"

if not PARSER_CPP.exists():
    raise SystemExit(f"ERROR: V20 prerequisite missing: {PARSER_CPP}")

text = PARSER_CPP.read_text(encoding="utf-8-sig")

old = '''        if (ts.peek() == "linearSpacing") { ts.get(); d.linearSpacing = true; continue; }\n        // Raven spawn domains may opt into the effect's end-origin coordinate.'''
new = '''        if (ts.peek() == "linearSpacing") { ts.get(); d.linearSpacing = true; continue; }\n        // Raven envelopes may append `count` with one or more scalar values\n        // (for example: envelope linear count 2,2,2).  Preserve parser fidelity\n        // by consuming the modifier; the current renderer already evaluates the\n        // named envelope table and does not need the repetition vector itself.\n        if (ts.peek() == "count") {\n            ts.get();\n            while (!ts.eof() && ts.peek() != "}") {\n                if (ts.accept(",")) continue;\n                if (IsNum(ts.peek())) { ts.get(); continue; }\n                break;\n            }\n            continue;\n        }\n        // Raven spawn domains may opt into the effect's end-origin coordinate.'''

hits = text.count(old)
if hits != 1:
    raise SystemExit(f"ERROR: V20 expected exactly one ParseDomain linearSpacing anchor, found {hits}")
text = text.replace(old, new, 1)

if 'if (ts.peek() == "count")' not in text:
    raise SystemExit("ERROR: V20 domain count compatibility verification failed")

PARSER_CPP.write_text(text, encoding="utf-8")
print("Q4BSE V20 NAILGUN DOMAIN COUNT PASS.")
print("  - envelope/domain count vectors are accepted without rejecting Raven FX")
