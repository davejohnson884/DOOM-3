#!/usr/bin/env python3
"""V19b: accept Raven domain `count` modifiers used by Nailgun glass/electronics FX."""
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PARSER = ROOT / "neo" / "game" / "q4bse" / "Q4FxParser.cpp"
if not PARSER.exists():
    raise SystemExit(f"ERROR: parser missing: {PARSER}")
text = PARSER.read_text(encoding="utf-8-sig")
old = '''        if (ts.peek() == "linearSpacing") { ts.get(); d.linearSpacing = true; continue; }
        // Raven spawn domains may opt into the effect's end-origin coordinate.'''
new = '''        if (ts.peek() == "linearSpacing") { ts.get(); d.linearSpacing = true; continue; }
        // Raven permits envelope repetition counts, e.g. tint { envelope linear count 2,2,2 }.
        // The current bridge evaluates one normalized envelope but must preserve parseability.
        if (ts.peek() == "count") {
            ts.get();
            while (!ts.eof() && ts.peek() != "}") {
                if (ts.accept(",")) continue;
                if (IsNum(ts.peek())) { ts.get(); continue; }
                break;
            }
            continue;
        }
        // Raven spawn domains may opt into the effect's end-origin coordinate.'''
hits = text.count(old)
if hits != 1:
    raise SystemExit(f"ERROR: V19b expected one domain modifier anchor, found {hits}")
text = text.replace(old, new, 1)
PARSER.write_text(text, encoding="utf-8")
print("Q4BSE V19b NAILGUN DOMAIN COUNT PASS.")
