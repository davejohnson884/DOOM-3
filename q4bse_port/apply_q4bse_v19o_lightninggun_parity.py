#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
weapon_cpp = root / "neo" / "game" / "Weapon.cpp"
text = weapon_cpp.read_text(encoding="utf-8")

anchor = '''void idWeapon::UpdateQ4LightningGun( void ) {\n\tif ( !owner || !weaponDef || !weaponDef->dict.GetBool( "q4_lightning_runtime" ) ) return;\n\n\t// Raven UpdateTubes: three independently depleted tubes. We keep the exact\n'''
replacement = '''void idWeapon::UpdateQ4LightningGun( void ) {\n\tif ( !owner || !weaponDef || !weaponDef->dict.GetBool( "q4_lightning_runtime" ) ) return;\n\n\t// V19O: Raven's attached lightning-gun emitters (tube.fx / spire.fx) are\n\t// continuously serviced for as long as the weapon owns them.  The authored\n\t// emitter blocks are one-second windows; Raven's rvClientEffect stays alive\n\t// and keeps emitting while attached, so do the same here.\n\tspawnArgs.Set( "q4_bse_loop_emitters", "1" );\n\n\t// Raven UpdateTubes: three independently depleted tubes. We keep the exact\n'''
if anchor not in text:
    raise SystemExit("V19O: UpdateQ4LightningGun anchor not found")
text = text.replace(anchor, replacement, 1)

kick = '''\n\t\t// Preserve Doom 3's accumulated muzzle-kick behavior without a fake projectile.\n\t\tif ( kick_endtime < gameLocal.realClientTime ) kick_endtime = gameLocal.realClientTime;\n\t\tkick_endtime += muzzle_kick_time;\n\t\tif ( kick_endtime > gameLocal.realClientTime + muzzle_kick_maxtime )\n\t\t\tkick_endtime = gameLocal.realClientTime + muzzle_kick_maxtime;\n'''
if kick not in text:
    raise SystemExit("V19O: V19N muzzle-kick block not found")
text = text.replace(kick, '''\n\t\t// V19O: do not synthesize Doom 3 projectile-style muzzle rise here.\n\t\t// Raven's rvWeaponLightningGun::Think does not accumulate kick_endtime.\n''', 1)

weapon_cpp.write_text(text, encoding="utf-8")
print("V19O Lightning Gun parity overlay applied")
print(" - persistent attached LG emitters loop like Raven rvClientEffect")
print(" - removed V19N synthetic Doom 3 muzzle-kick accumulation")
