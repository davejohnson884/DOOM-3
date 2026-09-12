#!/usr/bin/env python3
"""V18C: make opt-in Nailgun GUI light shrink/expand with ammo fill.

Runs after V18B. V18B moves the entire light center with ammo, which makes the
screen surround look like different areas are merely getting weaker. V18C adds
an opt-in mode that changes the light's vertical extent and shifts its center so
the illuminated region itself visibly shrinks from the top as ammo is spent.

At exactly zero ammo, the light returns to full screen extent and uses V18B's
red empty color, matching the Nailgun GUI's red-empty state.
"""

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
WEAPON = ROOT / "neo" / "game" / "Weapon.cpp"

if not WEAPON.exists():
    raise SystemExit(f"ERROR: V18C prerequisite missing: {WEAPON}")

text = WEAPON.read_text(encoding="utf-8-sig")

old = '''\t\t\t\t// Axis is authored in GUI-light joint-local space. The light tracks the\n\t\t\t\t// TOP of the vertical ammo fill: full = +travel/2, empty = -travel/2.\n\t\t\t\tconst idVec3 q4AmmoAxis = weaponDef->dict.GetVector( "glightAmmoAxis", "0 0 1" );\n\t\t\t\tconst float q4AmmoTravel = weaponDef->dict.GetFloat( "glightAmmoTravel", "0" );\n\t\t\t\tq4GuiLocalOrigin += ( q4AmmoAxis * q4GuiLocalAxis ) * ( ( q4AmmoPct - 0.5f ) * q4AmmoTravel );'''

new = '''\t\t\t\t// Axis is authored in GUI-light joint-local space. V18B's original mode\n\t\t\t\t// moves the whole light to the top of the bar. V18C optionally changes the\n\t\t\t\t// actual light extent so the illuminated patch itself shrinks/expands.\n\t\t\t\tconst idVec3 q4AmmoAxis = weaponDef->dict.GetVector( "glightAmmoAxis", "0 0 1" );\n\t\t\t\tconst float q4AmmoTravel = weaponDef->dict.GetFloat( "glightAmmoTravel", "0" );\n\n\t\t\t\tif ( weaponDef->dict.GetBool( "glightAmmoExtentTrack" ) ) {\n\t\t\t\t\tconst int q4RadiusAxis = idMath::ClampInt( 0, 2, weaponDef->dict.GetInt( "glightAmmoRadiusAxis", "1" ) );\n\t\t\t\t\tconst float q4FullRadius = weaponDef->dict.GetFloat( "glightRadius", "3" );\n\t\t\t\t\tconst float q4MinRadius = weaponDef->dict.GetFloat( "glightAmmoMinRadius", "0.35" );\n\n\t\t\t\t\tif ( q4AmmoInClip <= 0 ) {\n\t\t\t\t\t\t// Empty Nailgun GUI becomes a full red warning screen. Restore full\n\t\t\t\t\t\t// vertical light extent and center; V18B handles the red RGB below.\n\t\t\t\t\t\tguiLight.lightRadius[q4RadiusAxis] = q4FullRadius;\n\t\t\t\t\t} else {\n\t\t\t\t\t\tconst float q4FillRadius = q4MinRadius + ( q4FullRadius - q4MinRadius ) * q4AmmoPct;\n\t\t\t\t\t\tguiLight.lightRadius[q4RadiusAxis] = q4FillRadius;\n\n\t\t\t\t\t\t// Keep the nominal bottom of the ammo-fill glow anchored while the\n\t\t\t\t\t\t// top edge descends. The shift is based on the authored GUI travel,\n\t\t\t\t\t\t// not the oversized diffuse light radius, so it stays on-screen.\n\t\t\t\t\t\tq4GuiLocalOrigin -= ( q4AmmoAxis * q4GuiLocalAxis ) * ( ( 1.0f - q4AmmoPct ) * q4AmmoTravel * 0.5f );\n\t\t\t\t\t}\n\t\t\t\t} else {\n\t\t\t\t\tq4GuiLocalOrigin += ( q4AmmoAxis * q4GuiLocalAxis ) * ( ( q4AmmoPct - 0.5f ) * q4AmmoTravel );\n\t\t\t\t}'''

hits = text.count(old)
if hits != 1:
    raise SystemExit(f"ERROR: V18C expected exactly one V18B ammo-position block, found {hits}")
text = text.replace(old, new, 1)

for needle in (
    'weaponDef->dict.GetBool( "glightAmmoExtentTrack" )',
    'weaponDef->dict.GetInt( "glightAmmoRadiusAxis", "1" )',
    'weaponDef->dict.GetFloat( "glightAmmoMinRadius", "0.35" )',
    'guiLight.lightRadius[q4RadiusAxis] = q4FillRadius',
    '( 1.0f - q4AmmoPct ) * q4AmmoTravel * 0.5f',
    'q4GuiPresentedAxis[0] *= q4Foreshorten',
):
    if needle not in text:
        raise SystemExit(f"ERROR: V18C verification missing: {needle}")

WEAPON.write_text(text, encoding="utf-8")

print("Q4BSE V18C NAILGUN GUI FILL EXTENT PASS.")
print("  - opt-in GUI light vertical extent now shrinks/expands with ammo")
print("  - glow bottom remains nominally anchored while top follows ammo fill")
print("  - empty state restores full extent for red warning screen")
print("  - weapons without glightAmmoExtentTrack are untouched")
