#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
weapon = root / "neo" / "game" / "Weapon.cpp"
text = weapon.read_text(encoding="utf-8-sig")

# V20A already honors Q4 joint_view_barrel / joint_view_flash for the FP model.
# V20B adds a narrow world-model Raven joint fallback and prints a deterministic
# modelDef diagnostic when the Railgun is loaded.
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

# FP joints are already declaration-driven by the accepted V14/V18 pipeline;
# just add a diagnostic so a test immediately tells us whether the model and
# Raven muzzle joint resolved.
old_fp = '''\tconst char *q4FlashJointName = weaponDef->dict.GetString( "joint_view_flash" );\n\tflashJointView = animator.GetJointHandle( ( q4FlashJointName && q4FlashJointName[0] ) ? q4FlashJointName : "flash" );\n\tejectJointView = animator.GetJointHandle( "eject" );\n'''
new_fp = '''\tconst char *q4FlashJointName = weaponDef->dict.GetString( "joint_view_flash" );\n\tflashJointView = animator.GetJointHandle( ( q4FlashJointName && q4FlashJointName[0] ) ? q4FlashJointName : "flash" );\n\tejectJointView = animator.GetJointHandle( "eject" );\n\tif ( weaponDef->dict.GetBool( "q4_railgun_runtime" ) ) {\n\t\tgameLocal.Printf( "Q4 RAILGUN V20B: FP joints flash=%d barrel=%d\\n",\n\t\t\t(int)flashJointView, (int)barrelJointView );\n\t}\n'''
if text.count(old_fp) != 1:
    raise SystemExit(f"V20B: expected one declaration-driven FP joint block, found {text.count(old_fp)}")
text = text.replace(old_fp, new_fp, 1)

for needle in (
    'Q4 RAILGUN V20B: model_view',
    'Q4 RAILGUN V20B: FP joints',
    'muzzle_flash',
):
    if needle not in text:
        raise SystemExit(f"V20B verification missing: {needle}")

weapon.write_text(text, encoding="utf-8")
print("V20B Railgun presentation fix applied")
