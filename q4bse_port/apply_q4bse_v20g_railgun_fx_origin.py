#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
H = ROOT / 'neo/game/Weapon.h'
W = ROOT / 'neo/game/Weapon.cpp'
for p in (H, W):
    if not p.exists():
        raise SystemExit(f'V20G prerequisite missing: {p}')

def repl(text, old, new, label, count=1):
    hits = text.count(old)
    if hits != count:
        raise SystemExit(f'V20G {label}: expected {count}, got {hits}')
    return text.replace(old, new, count)

h = H.read_text(encoding='utf-8-sig')
w = W.read_text(encoding='utf-8-sig')

# Mirror Raven's GetGlobalJointTransform(view,...,offset) behavior for the
# source-driven Q4 effects. The offset is authored in the joint's local axis
# before the viewmodel foreshorten transform is applied.
h = repl(
    h,
    'bool\t\t\t\t\t\tGetQ4PresentedJointTransform( jointHandle_t joint, idVec3 &origin, idMat3 &axis );',
    'bool\t\t\t\t\t\tGetQ4PresentedJointTransform( jointHandle_t joint, idVec3 &origin, idMat3 &axis, const idVec3 &localOffset = vec3_origin );',
    'helper declaration')

w = repl(
    w,
    'bool idWeapon::GetQ4PresentedJointTransform( jointHandle_t joint, idVec3 &origin, idMat3 &axis ) {',
    'bool idWeapon::GetQ4PresentedJointTransform( jointHandle_t joint, idVec3 &origin, idMat3 &axis, const idVec3 &localOffset ) {',
    'helper definition')

w = repl(
    w,
    '''\tidVec3 localOrigin;\n\tidMat3 localAxis;\n\tif ( !animator.GetJointTransform( joint, gameLocal.time, localOrigin, localAxis ) ) return false;\n\n\tidVec3 presentedOrigin = viewWeaponOrigin;\n''',
    '''\tidVec3 localOrigin;\n\tidMat3 localAxis;\n\tif ( !animator.GetJointTransform( joint, gameLocal.time, localOrigin, localAxis ) ) return false;\n\n\t// Quake 4 rvWeapon::GetGlobalJointTransform applies fxOriginOffset in the\n\t// animated joint's local axis before converting the result to presented\n\t// viewmodel space. Preserve that ordering here.\n\tlocalOrigin = localOffset * localAxis + localOrigin;\n\n\tidVec3 presentedOrigin = viewWeaponOrigin;\n''',
    'local joint offset')

w = repl(
    w,
    '''\t\tidVec3 railOrigin;\n\t\tidMat3 railAxis;\n\t\tif ( !GetQ4PresentedJointTransform( flashJointView, railOrigin, railAxis ) ) {\n\t\t\trailOrigin = playerViewOrigin;\n\t\t\trailAxis = playerViewAxis;\n\t\t}\n''',
    '''\t\tidVec3 railOrigin;\n\t\tidMat3 railAxis;\n\t\t// Retail Q4 hitscan_railgun authors fxOriginOffset \"0 -15 10\".\n\t\t// This is why the visible rail originates off-center from the gun and\n\t\t// converges toward the crosshair instead of appearing screen-centered.\n\t\tconst idVec3 railFxOriginOffset = weaponDef->dict.GetVector( \"fxOriginOffset\", \"0 0 0\" );\n\t\tif ( !GetQ4PresentedJointTransform( flashJointView, railOrigin, railAxis, railFxOriginOffset ) ) {\n\t\t\trailOrigin = playerViewOrigin;\n\t\t\trailAxis = playerViewAxis;\n\t\t}\n''',
    'Railgun fxOriginOffset')

for needle in (
    'const idVec3 &localOffset = vec3_origin',
    'localOrigin = localOffset * localAxis + localOrigin;',
    'railFxOriginOffset = weaponDef->dict.GetVector( "fxOriginOffset", "0 0 0" )',
    'GetQ4PresentedJointTransform( flashJointView, railOrigin, railAxis, railFxOriginOffset )',
):
    if needle not in h + w:
        raise SystemExit(f'V20G verification missing: {needle}')

H.write_text(h, encoding='utf-8')
W.write_text(w, encoding='utf-8')
print('Q4BSE V20G Railgun Q4 fxOriginOffset patch PASS')
