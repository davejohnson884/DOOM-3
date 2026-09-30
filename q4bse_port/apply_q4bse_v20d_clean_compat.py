#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
hp = root/'neo/game/anim/Anim.h'
ap = root/'neo/game/anim/Anim_Blend.cpp'
wp = root/'neo/game/Weapon.cpp'
h = hp.read_text(encoding='utf-8-sig')
a = ap.read_text(encoding='utf-8-sig')
w = wp.read_text(encoding='utf-8-sig')

def one(text, old, new, label):
    n=text.count(old)
    if n!=1: raise SystemExit(f'V20D {label}: expected 1, found {n}')
    return text.replace(old,new,1)

# Generic Raven modelDef animation-rate support.
h=one(h,'\tidList<frameCommand_t>\t\tframeCommands;\n\tanimFlags_t\t\t\t\t\tflags;\n',
      '\tidList<frameCommand_t>\t\tframeCommands;\n\tanimFlags_t\t\t\t\t\tflags;\n\tfloat\t\t\t\t\t\tplaybackRate;\t// Raven/Q4 modelDef rate\n','rate member')
h=one(h,'\tvoid\t\t\t\t\t\tSetAnimFlags( const animFlags_t &animflags );\n\tconst animFlags_t\t\t\t&GetAnimFlags( void ) const;\n',
      '\tvoid\t\t\t\t\t\tSetAnimFlags( const animFlags_t &animflags );\n\tconst animFlags_t\t\t\t&GetAnimFlags( void ) const;\n\tvoid\t\t\t\t\t\tSetDeclPlaybackRate( float r ) { playbackRate = r; }\n\tfloat\t\t\t\t\t\tGetDeclPlaybackRate( void ) const { return playbackRate; }\n','rate accessors')
a=one(a,'idAnim::idAnim() {\n\tmodelDef = NULL;\n\tnumAnims = 0;\n',
      'idAnim::idAnim() {\n\tmodelDef = NULL;\n\tnumAnims = 0;\n\tplaybackRate = 1.0f;\n','ctor rate')
a=one(a,'\tflags = anim->flags;\n\n\tmemset( anims, 0, sizeof( anims ) );\n',
      '\tflags = anim->flags;\n\tplaybackRate = anim->playbackRate;\n\n\tmemset( anims, 0, sizeof( anims ) );\n','copy rate')
a=one(a,'\tmemset( &flags, 0, sizeof( flags ) );\n\n\tfor( i = 0; i < frameCommands.Num(); i++ ) {\n',
      '\tmemset( &flags, 0, sizeof( flags ) );\n\tplaybackRate = 1.0f;\n\n\tfor( i = 0; i < frameCommands.Num(); i++ ) {\n','setanim rate')
a=one(a,'\t\t\t} else if ( token == "anim_turn" ) {\n\t\t\t\tflags.anim_turn = true;\n\t\t\t} else if ( token == "frame" ) {\n',
      '\t\t\t} else if ( token == "anim_turn" ) {\n\t\t\t\tflags.anim_turn = true;\n\t\t\t} else if ( token == "rate" ) {\n\t\t\t\tconst float declRate = src.ParseFloat();\n\t\t\t\tif ( declRate <= 0.0f ) {\n\t\t\t\t\tsrc.Warning( "Invalid animation playback rate %f", declRate );\n\t\t\t\t\tMakeDefault();\n\t\t\t\t\treturn false;\n\t\t\t\t}\n\t\t\t\tanim->SetDeclPlaybackRate( declRate );\n\t\t\t} else if ( token == "frame" ) {\n','parse rate')
a=one(a,'\tPushAnims( channelNum, currentTime, blendTime );\n\tchannels[ channelNum ][ 0 ].CycleAnim( modelDef, animNum, currentTime, blendTime );\n\tif ( entity ) {\n',
      '\tPushAnims( channelNum, currentTime, blendTime );\n\tchannels[ channelNum ][ 0 ].CycleAnim( modelDef, animNum, currentTime, blendTime );\n\tchannels[ channelNum ][ 0 ].SetPlaybackRate( currentTime, modelDef->GetAnim( animNum )->GetDeclPlaybackRate() );\n\tif ( entity ) {\n','cycle rate')
a=one(a,'\tPushAnims( channelNum, currentTime, blendTime );\n\tchannels[ channelNum ][ 0 ].PlayAnim( modelDef, animNum, currentTime, blendTime );\n\tif ( entity ) {\n',
      '\tPushAnims( channelNum, currentTime, blendTime );\n\tchannels[ channelNum ][ 0 ].PlayAnim( modelDef, animNum, currentTime, blendTime );\n\tchannels[ channelNum ][ 0 ].SetPlaybackRate( currentTime, modelDef->GetAnim( animNum )->GetDeclPlaybackRate() );\n\tif ( entity ) {\n','play rate')

# Generic Raven world-joint keys. View-side joint keys are already part of the
# accepted cumulative Q4 weapon presentation pipeline; do not duplicate them.
w=one(w,'\tflashJointWorld = ent->GetAnimator()->GetJointHandle( "flash" );\n\tbarrelJointWorld = ent->GetAnimator()->GetJointHandle( "muzzle" );\n\tejectJointWorld = ent->GetAnimator()->GetJointHandle( "eject" );\n',
      '\tconst char *q4WorldFlash = def->dict.GetString( "joint_world_flash" );\n\tconst char *q4WorldBarrel = def->dict.GetString( "joint_world_barrel" );\n\tconst char *q4WorldEject = def->dict.GetString( "joint_world_eject" );\n\tflashJointWorld = ent->GetAnimator()->GetJointHandle( q4WorldFlash[0] ? q4WorldFlash : "flash" );\n\tbarrelJointWorld = ent->GetAnimator()->GetJointHandle( q4WorldBarrel[0] ? q4WorldBarrel : ( q4WorldFlash[0] ? q4WorldFlash : "muzzle" ) );\n\tejectJointWorld = ent->GetAnimator()->GetJointHandle( q4WorldEject[0] ? q4WorldEject : "eject" );\n','world joint keys')

# Accepted pipeline must already expose Raven view-joint keys.
if 'joint_view_barrel' not in w or 'joint_view_flash' not in w:
    raise SystemExit('V20D prerequisite: accepted Q4 view-joint bridge missing')

hp.write_text(h,encoding='utf-8')
ap.write_text(a,encoding='utf-8')
wp.write_text(w,encoding='utf-8')
print('Q4BSE V20D clean generic Q4 compatibility PASS')
