#!/usr/bin/env python3
from pathlib import Path
import base64
import zlib

payload = Path(__file__).with_name("v19n_lightning_payload.b64")
source = zlib.decompress(base64.b64decode(payload.read_text(encoding="ascii").strip()))
code = compile(source, str(payload), "exec")
exec(code, {"__name__": "__main__", "__file__": str(Path(__file__).resolve())})
