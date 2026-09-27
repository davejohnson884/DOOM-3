#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
weapon_cpp = root / "neo" / "game" / "Weapon.cpp"

text = weapon_cpp.read_text(encoding="utf-8")

old = '''\tlight.shader = muzzleFlash.shader ? muzzleFlash.shader : declManager->FindMaterial( "lights/muzzleflash", false );\n\tlight.shaderParms[ SHADERPARM_RED ] = color[0];\n\tlight.shaderParms[ SHADERPARM_GREEN ] = color[1];\n\tlight.shaderParms[ SHADERPARM_BLUE ] = color[2];\n\tlight.shaderParms[ SHADERPARM_TIMESCALE ] = 1.0f;\n\tlight.shaderParms[ SHADERPARM_TIMEOFFSET ] = -MS2SEC( gameLocal.time );\n'''
new = '''\t// V19R: use the renderer's built-in static default point-light shader.\n\t// V19Q reused lights/muzzleflash and reset its TIMEOFFSET every frame; that\n\t// animated muzzle-flash material can evaluate at effectively zero intensity.\n\t// A NULL shader is explicitly defined by idTech 4 as lights/defaultPointLight.\n\tlight.shader = NULL;\n\tlight.shaderParms[ SHADERPARM_RED ] = color[0];\n\tlight.shaderParms[ SHADERPARM_GREEN ] = color[1];\n\tlight.shaderParms[ SHADERPARM_BLUE ] = color[2];\n\tlight.shaderParms[ SHADERPARM_ALPHA ] = 1.0f;\n'''
if old not in text:
    raise SystemExit("V19R: dynamic-light shader anchor not found")
text = text.replace(old, new, 1)

old = '''\tif ( !gameLocal.isMultiplayer && owner == gameLocal.GetLocalPlayer() ) {\n\t\towner->playerView.SetShakeParms( MS2SEC( gameLocal.time + 500 ), 2.0f );\n\t}\n'''
new = '''\tif ( !gameLocal.isMultiplayer && owner == gameLocal.GetLocalPlayer() ) {\n\t\tconst float lgShakeScale = weaponDef->dict.GetFloat( "q4_lg_shake_scale", "1.6" );\n\t\towner->playerView.SetShakeParms( MS2SEC( gameLocal.time + 500 ), lgShakeScale );\n\t}\n'''
if old not in text:
    raise SystemExit("V19R: sustained shake anchor not found")
text = text.replace(old, new, 1)

# Pull the small weapon-local lights slightly outside the mesh so they illuminate
# nearby gun surfaces instead of sitting buried inside the MD5 volume.
old = '''\t\t\t\tUpdateQ4LightningGunLight( i, tubeOrigin + tubeAxis[0] * 0.5f, coilRadius, coilColor * attenuation );\n'''
new = '''\t\t\t\tconst idVec3 coilLightOrigin = tubeOrigin - playerViewAxis[0] * 2.0f + playerViewAxis[2] * 1.0f;\n\t\t\t\tUpdateQ4LightningGunLight( i, coilLightOrigin, coilRadius, coilColor * attenuation );\n'''
if old not in text:
    raise SystemExit("V19R: coil-light origin anchor not found")
text = text.replace(old, new, 1)

old = '''\t\t\tUpdateQ4LightningGunLight( Q4_LG_SPIRE_LIGHT, spireOrigin + spireAxis[0] * 1.85f, spireRadius, spireColor );\n'''
new = '''\t\t\tconst idVec3 spireLightOrigin = spireOrigin - playerViewAxis[0] * 1.5f + playerViewAxis[2] * 2.0f;\n\t\t\tUpdateQ4LightningGunLight( Q4_LG_SPIRE_LIGHT, spireLightOrigin, spireRadius, spireColor );\n'''
if old not in text:
    raise SystemExit("V19R: spire-light origin anchor not found")
text = text.replace(old, new, 1)

weapon_cpp.write_text(text, encoding="utf-8")
print("V19R Lightning Gun lighting fix applied")
print(" - dynamic lights now use static defaultPointLight shader")
print(" - coil/spire lights are nudged outside the viewmodel mesh")
print(" - sustained shake defaults to scale 1.6 and is content-tunable")
