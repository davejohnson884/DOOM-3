#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
ANIM_H = ROOT / 'neo/game/anim/Anim.h'
ANIM_CPP = ROOT / 'neo/game/anim/Anim_Blend.cpp'
WEAPON = ROOT / 'neo/game/Weapon.cpp'
for p in (ANIM_H, ANIM_CPP, WEAPON):
    if not p.exists():
        raise SystemExit(f'V20D prerequisite missing: {p}')

def repl(text, old, new, label, count=1):
    hits = text.count(old)
    if hits != count:
        raise SystemExit(f'V20D {label}: expected {count} hit(s), found {hits}')
    return text.replace(old, new, count)

h = ANIM_H.read_text(encoding='utf-8-sig')
a = ANIM_CPP.read_text(encoding='utf-8-sig')
w = WEAPON.read_text(encoding='utf-8-sig')

# -----------------------------------------------------------------------------
# Raven/Q4 modelDefs allow `rate <float>` inside an animation declaration.
# Stock Doom 3 rejects that token and defaults the ENTIRE modelDef, which is why
# an otherwise valid Q4 Railgun could exist in inventory but have no view model,
# animations or frame-command sounds. Add the missing declarative feature
# generically instead of special-casing Railgun presentation.
# -----------------------------------------------------------------------------
h = repl(h,
'''\tidList<frameCommand_t>\t\tframeCommands;\n\tanimFlags_t\t\t\t\t\tflags;\n''',
'''\tidList<frameCommand_t>\t\tframeCommands;\n\tanimFlags_t\t\t\t\t\tflags;\n\tfloat\t\t\t\t\t\tplaybackRate;\t// Raven/Q4 modelDef `rate`, Doom 3 default = 1\n''',
'idAnim playbackRate member')

h = repl(h,
'''\tvoid\t\t\t\t\t\tSetAnimFlags( const animFlags_t &animflags );\n\tconst animFlags_t\t\t\t&GetAnimFlags( void ) const;\n''',
'''\tvoid\t\t\t\t\t\tSetAnimFlags( const animFlags_t &animflags );\n\tconst animFlags_t\t\t\t&GetAnimFlags( void ) const;\n\tvoid\t\t\t\t\t\tSetDeclPlaybackRate( float newRate ) { playbackRate = newRate; }\n\tfloat\t\t\t\t\t\tGetDeclPlaybackRate( void ) const { return playbackRate; }\n''',
'idAnim playbackRate accessors')

a = repl(a,
'''idAnim::idAnim() {\n\tmodelDef = NULL;\n\tnumAnims = 0;\n''',
'''idAnim::idAnim() {\n\tmodelDef = NULL;\n\tnumAnims = 0;\n\tplaybackRate = 1.0f;\n''',
'idAnim constructor rate')

a = repl(a,
'''\tflags = anim->flags;\n\n\tmemset( anims, 0, sizeof( anims ) );\n''',
'''\tflags = anim->flags;\n\tplaybackRate = anim->playbackRate;\n\n\tmemset( anims, 0, sizeof( anims ) );\n''',
'idAnim copy rate')

a = repl(a,
'''\tmemset( &flags, 0, sizeof( flags ) );\n\n\tfor( i = 0; i < frameCommands.Num(); i++ ) {\n''',
'''\tmemset( &flags, 0, sizeof( flags ) );\n\tplaybackRate = 1.0f;\n\n\tfor( i = 0; i < frameCommands.Num(); i++ ) {\n''',
'idAnim SetAnim rate reset')

# Parse Raven's rate token as declaration data instead of rejecting the modelDef.
a = repl(a,
'''\t\t\t} else if ( token == "anim_turn" ) {\n\t\t\t\tflags.anim_turn = true;\n\t\t\t} else if ( token == "frame" ) {\n''',
'''\t\t\t} else if ( token == "anim_turn" ) {\n\t\t\t\tflags.anim_turn = true;\n\t\t\t} else if ( token == "rate" ) {\n\t\t\t\tconst float declRate = src.ParseFloat();\n\t\t\t\tif ( declRate <= 0.0f ) {\n\t\t\t\t\tsrc.Warning( "Invalid animation playback rate %f", declRate );\n\t\t\t\t\tMakeDefault();\n\t\t\t\t\treturn false;\n\t\t\t\t}\n\t\t\t\tanim->SetDeclPlaybackRate( declRate );\n\t\t\t} else if ( token == "frame" ) {\n''',
'ParseAnim Raven rate')

# Apply the declaration rate whenever the animator starts/cycles that anim.
a = repl(a,
'''\tPushAnims( channelNum, currentTime, blendTime );\n\tchannels[ channelNum ][ 0 ].CycleAnim( modelDef, animNum, currentTime, blendTime );\n\tif ( entity ) {\n''',
'''\tPushAnims( channelNum, currentTime, blendTime );\n\tchannels[ channelNum ][ 0 ].CycleAnim( modelDef, animNum, currentTime, blendTime );\n\tchannels[ channelNum ][ 0 ].SetPlaybackRate( currentTime, modelDef->GetAnim( animNum )->GetDeclPlaybackRate() );\n\tif ( entity ) {\n''',
'CycleAnim declaration rate')

a = repl(a,
'''\tPushAnims( channelNum, currentTime, blendTime );\n\tchannels[ channelNum ][ 0 ].PlayAnim( modelDef, animNum, currentTime, blendTime );\n\tif ( entity ) {\n''',
'''\tPushAnims( channelNum, currentTime, blendTime );\n\tchannels[ channelNum ][ 0 ].PlayAnim( modelDef, animNum, currentTime, blendTime );\n\tchannels[ channelNum ][ 0 ].SetPlaybackRate( currentTime, modelDef->GetAnim( animNum )->GetDeclPlaybackRate() );\n\tif ( entity ) {\n''',
'PlayAnim declaration rate')

# -----------------------------------------------------------------------------
# Honor Raven's joint_* keys generically. This avoids Railgun-only hard-coded
# fallbacks and lets Q4 weapon defs describe their actual muzzle joints just as
# they do in Quake 4.
# -----------------------------------------------------------------------------
w = repl(w,
'''\tflashJointWorld = ent->GetAnimator()->GetJointHandle( "flash" );\n\tbarrelJointWorld = ent->GetAnimator()->GetJointHandle( "muzzle" );\n\tejectJointWorld = ent->GetAnimator()->GetJointHandle( "eject" );\n''',
'''\tconst char *q4WorldFlash = def->dict.GetString( "joint_world_flash" );\n\tconst char *q4WorldBarrel = def->dict.GetString( "joint_world_barrel" );\n\tconst char *q4WorldEject = def->dict.GetString( "joint_world_eject" );\n\tflashJointWorld = ent->GetAnimator()->GetJointHandle( q4WorldFlash[0] ? q4WorldFlash : "flash" );\n\tbarrelJointWorld = ent->GetAnimator()->GetJointHandle( q4WorldBarrel[0] ? q4WorldBarrel : ( q4WorldFlash[0] ? q4WorldFlash : "muzzle" ) );\n\tejectJointWorld = ent->GetAnimator()->GetJointHandle( q4WorldEject[0] ? q4WorldEject : "eject" );\n''',
'generic world joint keys')

w = repl(w,
'''\t// find some joints in the model for locating effects\n\tbarrelJointView = animator.GetJointHandle( "barrel" );\n\tflashJointView = animator.GetJointHandle( "flash" );\n\tejectJointView = animator.GetJointHandle( "eject" );\n\tguiLightJointView = animator.GetJointHandle( "guiLight" );\n\tventLightJointView = animator.GetJointHandle( "ventLight" );\n''',
'''\t// find joints in the model for locating effects. Raven/Q4 weapon defs carry\n\t// explicit joint_view_* keys; fall back to Doom 3 names for stock weapons.\n\tconst char *q4ViewBarrel = weaponDef->dict.GetString( "joint_view_barrel" );\n\tconst char *q4ViewFlash = weaponDef->dict.GetString( "joint_view_flash" );\n\tconst char *q4ViewEject = weaponDef->dict.GetString( "joint_view_eject" );\n\tconst char *q4ViewGui = weaponDef->dict.GetString( "joint_view_guiLight" );\n\tconst char *q4ViewVent = weaponDef->dict.GetString( "joint_view_ventLight" );\n\tbarrelJointView = animator.GetJointHandle( q4ViewBarrel[0] ? q4ViewBarrel : "barrel" );\n\tflashJointView = animator.GetJointHandle( q4ViewFlash[0] ? q4ViewFlash : "flash" );\n\tejectJointView = animator.GetJointHandle( q4ViewEject[0] ? q4ViewEject : "eject" );\n\tguiLightJointView = animator.GetJointHandle( q4ViewGui[0] ? q4ViewGui : "guiLight" );\n\tventLightJointView = animator.GetJointHandle( q4ViewVent[0] ? q4ViewVent : "ventLight" );\n''',
'generic view joint keys')

for needle in (
    'playbackRate;\t// Raven/Q4 modelDef `rate`',
    'token == "rate"',
    'GetDeclPlaybackRate()',
):
    if needle not in h + a:
        raise SystemExit(f'V20D animation verification missing: {needle}')
for needle in ('joint_world_flash', 'joint_view_barrel', 'joint_view_flash'):
    if needle not in w:
        raise SystemExit(f'V20D joint verification missing: {needle}')

ANIM_H.write_text(h, encoding='utf-8')
ANIM_CPP.write_text(a, encoding='utf-8')
WEAPON.write_text(w, encoding='utf-8')
print('Q4BSE V20D generic Q4 modelDef/joint compatibility PASS')
