#!/usr/bin/env python3
'''Compatibility shim for the corrected Dark Matter explosion work.

The old V19I experiment incorrectly fired fx_detonate from idProjectile::Explode
for every world collision, which stacked the air/fuse detonation on top of the
surface impact. Raven's real DMG already has the correct split through the
existing gameplay bridge after V19H:

    collision -> fx_impact   -> impact_default_mp.fx
    fuse/air  -> fx_detonate -> impact_default.fx

Keep the workflow filename stable, but replace that experiment with V19J's
stock-Raven BSE runtime parity patch.
'''

from pathlib import Path
import runpy

script = Path(__file__).with_name('apply_q4bse_v19j_darkmatter_stock_explosion_runtime.py')
if not script.exists():
    raise SystemExit(f'ERROR: missing corrected explosion runtime patch: {script}')

runpy.run_path(str(script), run_name='__main__')
