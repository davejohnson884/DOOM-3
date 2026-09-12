#!/usr/bin/env python3
"""V18B: opt-in native Q4 GUI light ammo tracking.

Runs after the validated V18 chain. This patch touches ONLY idWeapon's already-
validated V16 GUI-light update path, and only changes behavior for weapon defs
that explicitly set glightAmmoTrack=1.

Adds:
  * GUI light position follows the vertical level of a weapon's ammo bar.
  * GUI light color can switch to a separate empty color at 0 rounds.
  * No custom/script-spawned idLight is involved.
  * HyperBlaster and all weapons without glightAmmoTrack remain unchanged.
"""

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
WEAPON = ROOT / "neo" / "game" / "Weapon.cpp"

if not WEAPON.exists():
    raise SystemExit(f"ERROR: V18B prerequisite missing: {WEAPON}")

text = WEAPON.read_text(encoding="utf-8-sig")

old = '''\t\t\tconst idVec3 q4GuiOffset = weaponDef ? weaponDef->dict.GetVector( "glightOffset", "0 0 0" ) : vec3_origin;\n\t\t\tq4GuiLocalOrigin = q4GuiOffset * q4GuiLocalAxis + q4GuiLocalOrigin;\n\n\t\t\tidVec3 q4GuiPresentedOrigin = viewWeaponOrigin;'''

new = '''\t\t\tconst idVec3 q4GuiOffset = weaponDef ? weaponDef->dict.GetVector( "glightOffset", "0 0 0" ) : vec3_origin;\n\t\t\tq4GuiLocalOrigin = q4GuiOffset * q4GuiLocalAxis + q4GuiLocalOrigin;\n\n\t\t\t// Optional Raven-style ammo-bar tracking. This is intentionally gated by\n\t\t\t// a weapon-def key so the validated HyperBlaster GUI light remains untouched.\n\t\t\tif ( weaponDef && weaponDef->dict.GetBool( "glightAmmoTrack" ) ) {\n\t\t\t\tfloat q4AmmoPct = 0.0f;\n\t\t\t\tconst int q4ClipSize = ClipSize();\n\t\t\t\tconst int q4AmmoInClip = AmmoInClip();\n\t\t\t\tif ( q4ClipSize > 0 ) {\n\t\t\t\t\tq4AmmoPct = idMath::ClampFloat( 0.0f, 1.0f, (float)q4AmmoInClip / (float)q4ClipSize );\n\t\t\t\t}\n\n\t\t\t\t// Axis is authored in GUI-light joint-local space. The light tracks the\n\t\t\t\t// TOP of the vertical ammo fill: full = +travel/2, empty = -travel/2.\n\t\t\t\tconst idVec3 q4AmmoAxis = weaponDef->dict.GetVector( "glightAmmoAxis", "0 0 1" );\n\t\t\t\tconst float q4AmmoTravel = weaponDef->dict.GetFloat( "glightAmmoTravel", "0" );\n\t\t\t\tq4GuiLocalOrigin += ( q4AmmoAxis * q4GuiLocalAxis ) * ( ( q4AmmoPct - 0.5f ) * q4AmmoTravel );\n\n\t\t\t\t// The light material uses 'colored', so these parms directly control the\n\t\t\t\t// cast color. At exactly zero rounds switch to the screen's empty red.\n\t\t\t\tidVec3 q4GuiColor = weaponDef->dict.GetVector( "glightColor", "1 1 1" );\n\t\t\t\tif ( q4AmmoInClip <= 0 ) {\n\t\t\t\t\tq4GuiColor = weaponDef->dict.GetVector( "glightEmptyColor", "1 0 0" );\n\t\t\t\t}\n\t\t\t\tguiLight.shaderParms[ SHADERPARM_RED ] = q4GuiColor.x;\n\t\t\t\tguiLight.shaderParms[ SHADERPARM_GREEN ] = q4GuiColor.y;\n\t\t\t\tguiLight.shaderParms[ SHADERPARM_BLUE ] = q4GuiColor.z;\n\t\t\t\tguiLight.shaderParms[ SHADERPARM_ALPHA ] = 1.0f;\n\t\t\t}\n\n\t\t\tidVec3 q4GuiPresentedOrigin = viewWeaponOrigin;'''

hits = text.count(old)
if hits != 1:
    raise SystemExit(f"ERROR: V18B expected exactly one V16 GUI-offset anchor, found {hits}")
text = text.replace(old, new, 1)

for needle in (
    'weaponDef->dict.GetBool( "glightAmmoTrack" )',
    'weaponDef->dict.GetVector( "glightAmmoAxis", "0 0 1" )',
    'weaponDef->dict.GetFloat( "glightAmmoTravel", "0" )',
    'weaponDef->dict.GetVector( "glightEmptyColor", "1 0 0" )',
    'guiLight.shaderParms[ SHADERPARM_RED ] = q4GuiColor.x',
    'q4GuiPresentedAxis[0] *= q4Foreshorten',
):
    if needle not in text:
        raise SystemExit(f"ERROR: V18B verification missing: {needle}")

WEAPON.write_text(text, encoding="utf-8")

print("Q4BSE V18B NATIVE GUI AMMO TRACK PASS.")
print("  - opt-in glightAmmoTrack follows ammo-bar vertical level")
print("  - opt-in empty color switches at zero rounds")
print("  - native idWeapon GUI light only; no DoomScript helper")
print("  - weapons without glightAmmoTrack are untouched")
