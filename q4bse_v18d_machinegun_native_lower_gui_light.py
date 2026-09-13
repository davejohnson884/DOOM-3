#!/usr/bin/env python3
"""V18D: opt-in native second GUI light for the Quake 4 Machinegun.

Runs after V18C. The primary idWeapon guiLight remains completely untouched.
This adds one narrowly gated SECOND first-person renderer light by reusing
idWeapon's otherwise-unused nozzleGlow slot when q4SecondGuiLight=1.

Why this path:
  * script-spawned idLight follows the visual weapon in world coordinates but
    does not illuminate the first-person receiver reliably;
  * idWeapon native lights carry the correct allowLightInViewID semantics;
  * Machinegun does not use nozzleFx, so the existing nozzleGlow storage/handle
    gives us full Clear/Save/Restore/free lifecycle without widening Weapon.h.

The second light has its own joint-local offset, anisotropic radius, shader,
loaded color, and exact-zero empty color. Weapons without q4SecondGuiLight are
byte-for-byte behaviorally unchanged.
"""

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
WEAPON = ROOT / "neo" / "game" / "Weapon.cpp"

if not WEAPON.exists():
    raise SystemExit(f"ERROR: V18D prerequisite missing: {WEAPON}")

text = WEAPON.read_text(encoding="utf-8-sig")

anchor = '''\tif ( status != WP_READY && sndHum ) {'''

native_lower = r'''	// Q4 V18D: optional SECOND native first-person GUI light. The validated
	// primary guiLight above is intentionally untouched. This path reuses the
	// normally-idle nozzleGlow render-light slot only for weapons that explicitly
	// request q4SecondGuiLight and do not use Doom 3 nozzleFx.
	if ( weaponDef && weaponDef->dict.GetBool( "q4SecondGuiLight" ) && !nozzleFx && guiLightJointView != INVALID_JOINT ) {
		idVec3 q4LowerLocalOrigin;
		idMat3 q4LowerLocalAxis;
		if ( animator.GetJointTransform( guiLightJointView, gameLocal.time, q4LowerLocalOrigin, q4LowerLocalAxis ) ) {
			// Offset is authored in the GUI-light joint basis, exactly like Raven's
			// glightOffset. For the MG this is the lower ammo-counter center plus a
			// small outward displacement from the physical screen plane.
			const idVec3 q4LowerOffset = weaponDef->dict.GetVector( "q4SecondGuiLightOffset", "0 0 0" );
			q4LowerLocalOrigin = q4LowerOffset * q4LowerLocalAxis + q4LowerLocalOrigin;

			// Reconstruct the exact source-integrated Q4 viewStyle/foreshorten space
			// used by the rendered gun and by the already-validated primary guiLight.
			idVec3 q4LowerPresentedOrigin = viewWeaponOrigin;
			idMat3 q4LowerPresentedAxis = viewWeaponAxis;
			idMat3 q4LowerBaseAxis = viewWeaponAxis;

			const char *q4ViewStyleName = weaponDef->dict.GetString( "def_viewStyle" );
			if ( q4ViewStyleName && q4ViewStyleName[0] ) {
				const idDeclEntityDef *q4ViewStyleDef = gameLocal.FindEntityDef( q4ViewStyleName, false );
				if ( q4ViewStyleDef ) {
					const idVec3 q4ViewOffset = q4ViewStyleDef->dict.GetVector( "viewoffset", "0 0 0" );
					const idAngles q4ViewAngles = q4ViewStyleDef->dict.GetAngles( "viewangles", "0 0 0" );
					const float q4Foreshorten = weaponDef->dict.GetFloat( "foreshorten", "1" );

					q4LowerPresentedOrigin += q4ViewOffset * viewWeaponAxis;
					q4LowerBaseAxis = q4ViewAngles.ToMat3() * viewWeaponAxis;
					q4LowerPresentedAxis = q4LowerBaseAxis;
					q4LowerPresentedAxis[0] *= q4Foreshorten;
				}
			}

			if ( nozzleGlowHandle == -1 ) {
				memset( &nozzleGlow, 0, sizeof( nozzleGlow ) );
				if ( owner ) {
					// Critical difference from a script-spawned idLight: this makes the
					// light participate in the first-person weapon render view.
					nozzleGlow.allowLightInViewID = owner->entityNumber + 1;
				}
				nozzleGlow.pointLight = true;
				nozzleGlow.noShadows = true;
				nozzleGlow.lightRadius = weaponDef->dict.GetVector( "q4SecondGuiLightRadius", "1 1 1" );

				const char *q4LowerShader = weaponDef->dict.GetString( "mtr_q4SecondGuiLightShader", "lights/squarelight1" );
				nozzleGlow.shader = declManager->FindMaterial( q4LowerShader, false );
				nozzleGlow.shaderParms[ SHADERPARM_TIMESCALE ] = 1.0f;
				nozzleGlow.shaderParms[ SHADERPARM_TIMEOFFSET ] = -MS2SEC( gameLocal.time );
			}

			nozzleGlow.origin = q4LowerLocalOrigin * q4LowerPresentedAxis + q4LowerPresentedOrigin;
			nozzleGlow.axis = q4LowerLocalAxis * q4LowerBaseAxis;

			idVec3 q4LowerColor = weaponDef->dict.GetVector( "q4SecondGuiLightColor", "0.14 0.42 0.07" );
			if ( AmmoInClip() <= 0 ) {
				q4LowerColor = weaponDef->dict.GetVector( "q4SecondGuiLightEmptyColor", "0.70 0.025 0.008" );
			}
			nozzleGlow.shaderParms[ SHADERPARM_RED ] = q4LowerColor.x;
			nozzleGlow.shaderParms[ SHADERPARM_GREEN ] = q4LowerColor.y;
			nozzleGlow.shaderParms[ SHADERPARM_BLUE ] = q4LowerColor.z;
			nozzleGlow.shaderParms[ SHADERPARM_ALPHA ] = 1.0f;

			if ( nozzleGlowHandle != -1 ) {
				gameRenderWorld->UpdateLightDef( nozzleGlowHandle, &nozzleGlow );
			} else {
				nozzleGlowHandle = gameRenderWorld->AddLightDef( &nozzleGlow );
			}
		}
	}

'''

hits = text.count(anchor)
if hits != 1:
    raise SystemExit(f"ERROR: V18D expected exactly one PresentWeapon status anchor, found {hits}")
text = text.replace(anchor, native_lower + anchor, 1)

for needle in (
    'GetBool( "q4SecondGuiLight" )',
    '!nozzleFx && guiLightJointView != INVALID_JOINT',
    'GetVector( "q4SecondGuiLightOffset", "0 0 0" )',
    'GetVector( "q4SecondGuiLightRadius", "1 1 1" )',
    'GetString( "mtr_q4SecondGuiLightShader", "lights/squarelight1" )',
    'nozzleGlow.allowLightInViewID = owner->entityNumber + 1',
    'q4LowerPresentedAxis[0] *= q4Foreshorten',
    'GetVector( "q4SecondGuiLightEmptyColor", "0.70 0.025 0.008" )',
    'gameRenderWorld->UpdateLightDef( nozzleGlowHandle, &nozzleGlow )',
):
    if needle not in text:
        raise SystemExit(f"ERROR: V18D verification missing: {needle}")

# Make sure we did not touch the proven V16/V18B primary GUI-light path or the
# V18C exact brass/flashlight gates.
for preserved in (
    'weaponDef->dict.GetVector( "glightOffset", "0 0 0" )',
    'weaponDef->dict.GetBool( "glightAmmoTrack" )',
    'weaponDef->dict.GetBool( "q4UseFlashlightJoint" )',
    'weaponDef->dict.GetBool( "q4ExactBrass" )',
):
    if preserved not in text:
        raise SystemExit(f"ERROR: V18D cumulative-path regression: {preserved}")

WEAPON.write_text(text, encoding="utf-8")

print("Q4BSE V18D MACHINEGUN NATIVE LOWER GUI LIGHT PASS.")
print("  - validated primary idWeapon guiLight untouched")
print("  - opt-in second first-person render light uses existing nozzleGlow lifecycle")
print("  - exact Q4 viewStyle + foreshorten transform")
print("  - independent anisotropic radius / joint-local offset / light shader")
print("  - loaded green and exact-zero red state")
print("  - V18C exact brass + dedicated flashlight path preserved")
