#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
weapon = root / "neo" / "game" / "Weapon.cpp"
text = weapon.read_text(encoding="utf-8-sig")

# V20B: the Q4 Railgun uses Raven joint names. Doom 3's idWeapon hard-codes
# "flash" / "barrel" for the FP model and "flash" / "muzzle" for the world
# model, so add narrow Railgun fallbacks without touching any other weapon.
old_world = '''\tflashJointWorld = ent->GetAnimator()->GetJointHandle( "flash" );\n\tbarrelJointWorld = ent->GetAnimator()->GetJointHandle( "muzzle" );\n\tejectJointWorld = ent->GetAnimator()->GetJointHandle( "eject" );\n'''
new_world = '''\tflashJointWorld = ent->GetAnimator()->GetJointHandle( "flash" );\n\tbarrelJointWorld = ent->GetAnimator()->GetJointHandle( "muzzle" );\n\tejectJointWorld = ent->GetAnimator()->GetJointHandle( "eject" );\n\n\tif ( def->dict.GetBool( "q4_railgun_runtime" ) ) {\n\t\tif ( flashJointWorld == INVALID_JOINT ) {\n\t\t\tflashJointWorld = ent->GetAnimator()->GetJointHandle( "muzzle_flash" );\n\t\t}\n\t\tif ( barrelJointWorld == INVALID_JOINT ) {\n\t\t\tbarrelJointWorld = ent->GetAnimator()->GetJointHandle( "muzzle_flash" );\n\t\t}\n\t}\n'''
if text.count(old_world) != 1:
    raise SystemExit(f"V20B: expected one world-joint block, found {text.count(old_world)}")
text = text.replace(old_world, new_world, 1)

old_model = '''\t// setup the view model\n\tvmodel = weaponDef->dict.GetString( "model_view" );\n\tSetModel( vmodel );\n\n\t// setup the world model\n'''
new_model = '''\t// setup the view model\n\tvmodel = weaponDef->dict.GetString( "model_view" );\n\tSetModel( vmodel );\n\n\tif ( weaponDef->dict.GetBool( "q4_railgun_runtime" ) ) {\n\t\tgameLocal.Printf( "Q4 RAILGUN V20B: model_view '%s' -> %s\\n",\n\t\t\tvmodel, animator.ModelDef() ? "MODELDEF OK" : "MODELDEF NULL" );\n\t}\n\n\t// setup the world model\n'''
if text.count(old_model) != 1:
    raise SystemExit(f"V20B: expected one view-model setup block, found {text.count(old_model)}")
text = text.replace(old_model, new_model, 1)

old_view = '''\tbarrelJointView = animator.GetJointHandle( "barrel" );\n\tflashJointView = animator.GetJointHandle( "flash" );\n\tejectJointView = animator.GetJointHandle( "eject" );\n\tguiLightJointView = animator.GetJointHandle( "guiLight" );\n\tventLightJointView = animator.GetJointHandle( "ventLight" );\n'''
new_view = '''\tbarrelJointView = animator.GetJointHandle( "barrel" );\n\tflashJointView = animator.GetJointHandle( "flash" );\n\tejectJointView = animator.GetJointHandle( "eject" );\n\tguiLightJointView = animator.GetJointHandle( "guiLight" );\n\tventLightJointView = animator.GetJointHandle( "ventLight" );\n\n\tif ( weaponDef->dict.GetBool( "q4_railgun_runtime" ) ) {\n\t\tif ( flashJointView == INVALID_JOINT ) {\n\t\t\tflashJointView = animator.GetJointHandle( "srocket_muzzle_flash" );\n\t\t}\n\t\tif ( barrelJointView == INVALID_JOINT ) {\n\t\t\tbarrelJointView = animator.GetJointHandle( "srocket_muzzle_flash" );\n\t\t}\n\t\tgameLocal.Printf( "Q4 RAILGUN V20B: FP joints flash=%d barrel=%d\\n",\n\t\t\t(int)flashJointView, (int)barrelJointView );\n\t}\n'''
if text.count(old_view) != 1:
    raise SystemExit(f"V20B: expected one view-joint block, found {text.count(old_view)}")
text = text.replace(old_view, new_view, 1)

for needle in (
    'Q4 RAILGUN V20B: model_view',
    'srocket_muzzle_flash',
    'muzzle_flash',
):
    if needle not in text:
        raise SystemExit(f"V20B verification missing: {needle}")

weapon.write_text(text, encoding="utf-8")
print("V20B Railgun presentation fix applied")
