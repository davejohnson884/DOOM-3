#!/usr/bin/env python3
"""Source-integrate the proven Quake 4 viewmodel presentation transform.

This replaces the old proxy/inner-DLL RenderWorld hook with normal Doom 3 GPL
source.  It deliberately changes only the first-person renderEntity at submit
time: Doom 3 weapon bob, gameplay physics, projectile aim and script state keep
their authoritative transforms.

Data comes from the weapon defs, matching Raven's scheme:
  def_viewStyle -> entityDef containing viewoffset / viewangles
  foreshorten   -> local-forward-axis scale (Raven ForeshortenAxis)

The transform order matches the proven V108/V110 presentation hook:
  1) add viewoffset in the already-bobbed Doom 3 view basis
  2) pre-compose the Raven viewangles rotation
  3) scale only local forward axis [0]
"""

from pathlib import Path
import sys

MARKER = "Q4 source-integrated viewmodel presentation"

OLD = r'''\t// present the model
\tif ( showViewModel ) {
\t\tPresent();
\t} else {
\t\tFreeModelDef();
\t}
'''

NEW = r'''\t// Q4 source-integrated viewmodel presentation.
\t//
\t// The old V106/V110 chain intercepted AddEntityDef/UpdateEntityDef and
\t// changed only the submitted first-person renderEntity.  Keep that exact
\t// ownership here: Doom 3 bob/gameplay/aim remain untouched, while Raven's
\t// data-driven viewStyle and ForeshortenAxis are applied to presentation.
\tbool q4PresentationActive = false;
\tidVec3 q4PresentationSavedOrigin;
\tidMat3 q4PresentationSavedAxis;

\tif ( showViewModel && weaponDef ) {
\t\tconst char *q4ViewStyleName = weaponDef->dict.GetString( "def_viewStyle" );
\t\tif ( q4ViewStyleName && q4ViewStyleName[ 0 ] ) {
\t\t\tconst idDeclEntityDef *q4ViewStyleDef = gameLocal.FindEntityDef( q4ViewStyleName, false );
\t\t\tif ( q4ViewStyleDef ) {
\t\t\t\tconst idVec3 q4ViewOffset = q4ViewStyleDef->dict.GetVector( "viewoffset", "0 0 0" );
\t\t\t\tconst idAngles q4ViewAngles = q4ViewStyleDef->dict.GetAngles( "viewangles", "0 0 0" );
\t\t\t\tconst float q4Foreshorten = weaponDef->dict.GetFloat( "foreshorten", "1" );

\t\t\t\tq4PresentationSavedOrigin = renderEntity.origin;
\t\t\t\tq4PresentationSavedAxis = renderEntity.axis;

\t\t\t\t// Raven viewoffset is expressed in the current (already bobbed) view basis.
\t\t\t\trenderEntity.origin = q4PresentationSavedOrigin + q4ViewOffset * q4PresentationSavedAxis;

\t\t\t\t// Match the proven hook and Raven convention: local rotation first,
\t\t\t\t// then ForeshortenAxis scales only the local forward axis.
\t\t\t\trenderEntity.axis = q4ViewAngles.ToMat3() * q4PresentationSavedAxis;
\t\t\t\trenderEntity.axis[ 0 ] *= q4Foreshorten;
\t\t\t\tq4PresentationActive = true;
\t\t\t}
\t\t}
\t}

\t// present the model
\tif ( showViewModel ) {
\t\tPresent();
\t} else {
\t\tFreeModelDef();
\t}

\t// Restore the authoritative Doom 3 render transform after submission.  The
\t// renderer owns a copy of the transformed entity; subsequent gameplay and
\t// joint calculations therefore continue from the unmodified Doom 3 pose.
\tif ( q4PresentationActive ) {
\t\trenderEntity.origin = q4PresentationSavedOrigin;
\t\trenderEntity.axis = q4PresentationSavedAxis;
\t}
'''


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_q4_viewmodel_presentation.py <repo-root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1])
    path = root / "neo" / "game" / "Weapon.cpp"
    text = path.read_text(encoding="utf-8")

    if MARKER in text:
        print("Q4 viewmodel presentation already integrated.")
        return 0

    if OLD not in text:
        raise SystemExit("PresentWeapon presentation anchor not found; refusing fuzzy patch")

    text = text.replace(OLD, NEW, 1)

    required = [
        MARKER,
        'GetString( "def_viewStyle" )',
        'GetVector( "viewoffset", "0 0 0" )',
        'GetAngles( "viewangles", "0 0 0" )',
        'GetFloat( "foreshorten", "1" )',
        'renderEntity.axis[ 0 ] *= q4Foreshorten;',
        'renderEntity.origin = q4PresentationSavedOrigin;',
        'renderEntity.axis = q4PresentationSavedAxis;',
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise SystemExit("Q4 presentation verification failed: " + ", ".join(missing))

    path.write_text(text, encoding="utf-8", newline="")
    print("Q4 viewmodel presentation integrated into Weapon.cpp.")
    print("  - data-driven def_viewStyle/viewoffset/viewangles")
    print("  - Raven forward-axis-only foreshorten")
    print("  - Doom 3 bob/gameplay transforms remain authoritative")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
