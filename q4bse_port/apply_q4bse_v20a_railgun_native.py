#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.cwd()
PLAYER=ROOT/'neo/game/Player.cpp'
WEAPON=ROOT/'neo/game/Weapon.cpp'
PROGRAM=ROOT/'neo/game/script/Script_Program.cpp'
for p in (PLAYER,WEAPON,PROGRAM):
    if not p.exists(): raise SystemExit(f'V20A prerequisite missing: {p}')

def replace_exact(text,old,new,label,count=1):
    hits=text.count(old)
    if hits!=count: raise SystemExit(f'V20A {label}: expected {count} hits, found {hits}')
    return text.replace(old,new,count)

p=PLAYER.read_text(encoding='utf-8-sig')
w=WEAPON.read_text(encoding='utf-8-sig')
s=PROGRAM.read_text(encoding='utf-8-sig')

# Player slot + reserve. Slot 13 is genuinely unused in Doom 3 and does not collide
# with the Q4 ports that deliberately retain their stock Doom identities.
old='''\tspawnArgs.Set( "max_ammo_lightninggun", "400" );\n'''
new='''\tspawnArgs.Set( "max_ammo_lightninggun", "400" );\n\n\t// Q4 V20A: Railgun is the one true additional weapon in the compact sandbox.\n\tspawnArgs.Set( "def_weapon13", "weapon_railgun" );\n\tspawnArgs.Set( "weapon13_best", "1" );\n\tspawnArgs.Set( "weapon13_cycle", "1" );\n\tspawnArgs.Set( "weapon13_toggle", "0" );\n\tspawnArgs.Set( "weapon13_allowempty", "0" );\n\tspawnArgs.Set( "weapon13_visible", "1" );\n\tspawnArgs.Set( "max_ammo_railgun", "35" );\n'''
p=replace_exact(p,old,new,'player Railgun slot anchor')

# Explicit Q4 wheel order: Rocket -> Railgun -> Lightning Gun -> Dark Matter Gun.
old_cycle='''\t\t"weapon_plasmagun",\n\t\t"weapon_rocketlauncher",\n\t\t"weapon_chainsaw",\n\t\t"weapon_bfg"\n'''
new_cycle='''\t\t"weapon_plasmagun",\n\t\t"weapon_rocketlauncher",\n\t\t"weapon_railgun",\n\t\t"weapon_chainsaw",\n\t\t"weapon_bfg"\n'''
p=replace_exact(p,old_cycle,new_cycle,'Q4 cycle insertion',count=2)
p=replace_exact(p,'\t\t\tstart = 9; // previous from Soul Cube lands on Dark Matter\n','\t\t\tstart = 10; // previous from Soul Cube lands on Dark Matter\n','Soul Cube reverse-cycle index')
p=p.replace('start = 7; // after Rocket comes Lightning Gun','start = 7; // after Rocket comes Railgun',1)

# Doom 3 player body has no railgun animation set. Reuse the two-handed Plasma Gun
# player animation family while leaving the Q4 first-person Railgun animations native.
old_anim='''\t\t\tanimPrefix.Strip( "weapon_" );\n'''
new_anim='''\t\t\tanimPrefix.Strip( "weapon_" );\n\t\t\tif ( !idStr::Icmp( spawnArgs.GetString( va( "def_weapon%d", currentWeapon ) ), "weapon_railgun" ) ) {\n\t\t\t\tanimPrefix = "plasmagun";\n\t\t\t}\n'''
p=replace_exact(p,old_anim,new_anim,'Railgun third-person alias',count=2)

# Dedicated ammo bucket after Lightning Gun's index 10.
old='''\tif ( !idStr::Icmp( ammoname, "ammo_lightninggun" ) ) {\n\t\treturn ( ammo_t )10;\n\t}\n'''
new='''\tif ( !idStr::Icmp( ammoname, "ammo_lightninggun" ) ) {\n\t\treturn ( ammo_t )10;\n\t}\n\tif ( !idStr::Icmp( ammoname, "ammo_railgun" ) ) {\n\t\treturn ( ammo_t )11;\n\t}\n'''
w=replace_exact(w,old,new,'Railgun ammo name->index')
old='''\tif ( ammonum == ( ammo_t )10 ) {\n\t\treturn "ammo_lightninggun";\n\t}\n'''
new='''\tif ( ammonum == ( ammo_t )10 ) {\n\t\treturn "ammo_lightninggun";\n\t}\n\tif ( ammonum == ( ammo_t )11 ) {\n\t\treturn "ammo_railgun";\n\t}\n'''
w=replace_exact(w,old,new,'Railgun ammo index->name')
old='''\tif ( ammonum == ( ammo_t )10 ) {\n\t\treturn "Lightning Ammo";\n\t}\n'''
new='''\tif ( ammonum == ( ammo_t )10 ) {\n\t\treturn "Lightning Ammo";\n\t}\n\tif ( ammonum == ( ammo_t )11 ) {\n\t\treturn "Railgun Ammo";\n\t}\n'''
w=replace_exact(w,old,new,'Railgun ammo pickup name')

# Native Railgun hitscan. Keep Doom 3's weapon script only as a state/animation shim;
# gameplay, trace, damage and Raven BSE presentation are source-owned here.
launch_anchor='''\tif ( weaponDef && weaponDef->dict.GetBool( "q4_darkmatter_runtime" ) ) {\n\t\tQ4BSE_StopEntityEffects( this );\n\t\tStopSound( SND_CHANNEL_VOICE, false );\n\t\tspawnArgs.Set( "_q4_dmg_core_mode", "0" );\n\t\tspawnArgs.Set( "_q4_dmg_core_request", "-1" );\n\t}\n\n\tif ( !projectileDict.GetNumKeyVals() ) {\n'''
rail_branch='''\tif ( weaponDef && weaponDef->dict.GetBool( "q4_darkmatter_runtime" ) ) {\n\t\tQ4BSE_StopEntityEffects( this );\n\t\tStopSound( SND_CHANNEL_VOICE, false );\n\t\tspawnArgs.Set( "_q4_dmg_core_mode", "0" );\n\t\tspawnArgs.Set( "_q4_dmg_core_request", "-1" );\n\t}\n\n\t// Q4 V20A: Raven's Railgun is a source-driven hitscan weapon. The Doom 3\n\t// script calls launchProjectiles only to enter this native path.\n\tif ( weaponDef && weaponDef->dict.GetBool( "q4_railgun_runtime" ) ) {\n\t\tif ( !gameLocal.isClient ) {\n\t\t\tconst int ammoAvail = owner->inventory.HasAmmo( ammoType, ammoRequired );\n\t\t\tif ( !ammoAvail || ( clipSize != 0 && ammoClip <= 0 ) ) {\n\t\t\t\treturn;\n\t\t\t}\n\t\t\towner->inventory.UseAmmo( ammoType, ammoRequired );\n\t\t\tif ( clipSize && ammoRequired ) {\n\t\t\t\tammoClip--;\n\t\t\t}\n\t\t\towner->AddProjectilesFired( 1 );\n\t\t}\n\n\t\tif ( !silent_fire ) {\n\t\t\tgameLocal.AlertAI( owner );\n\t\t}\n\n\t\trenderEntity.shaderParms[ SHADERPARM_DIVERSITY ] = gameLocal.random.CRandomFloat();\n\t\trenderEntity.shaderParms[ SHADERPARM_TIMEOFFSET ] = -MS2SEC( gameLocal.realClientTime );\n\t\tif ( worldModel.GetEntity() ) {\n\t\t\tworldModel.GetEntity()->SetShaderParm( SHADERPARM_DIVERSITY, renderEntity.shaderParms[ SHADERPARM_DIVERSITY ] );\n\t\t\tworldModel.GetEntity()->SetShaderParm( SHADERPARM_TIMEOFFSET, renderEntity.shaderParms[ SHADERPARM_TIMEOFFSET ] );\n\t\t}\n\n\t\tidVec3 railOrigin;\n\t\tidMat3 railAxis;\n\t\tif ( !GetQ4PresentedJointTransform( flashJointView, railOrigin, railAxis ) ) {\n\t\t\trailOrigin = playerViewOrigin;\n\t\t\trailAxis = playerViewAxis;\n\t\t}\n\n\t\tconst float railRange = weaponDef->dict.GetFloat( "q4_railgun_range", "40000" );\n\t\ttrace_t railTrace;\n\t\tconst idVec3 railTraceStart = playerViewOrigin;\n\t\tconst idVec3 railTraceEnd = railTraceStart + playerViewAxis[0] * railRange;\n\t\tgameLocal.clip.TracePoint( railTrace, railTraceStart, railTraceEnd, MASK_SHOT_RENDERMODEL, owner );\n\n\t\tidVec3 railDir = railTrace.endpos - railOrigin;\n\t\tif ( railDir.Normalize() < 0.001f ) {\n\t\t\trailDir = playerViewAxis[0];\n\t\t}\n\t\tconst idMat3 railFxAxis = railDir.ToMat3();\n\n\t\tconst char *railMuzzleFx = weaponDef->dict.GetString( "fx_muzzleflash" );\n\t\tif ( railMuzzleFx && railMuzzleFx[0] ) {\n\t\t\tQ4BSE_PlayEffectAxis( railMuzzleFx, railOrigin, railAxis );\n\t\t}\n\t\tconst char *railTrailFx = weaponDef->dict.GetString( "fx_path" );\n\t\tif ( railTrailFx && railTrailFx[0] ) {\n\t\t\tQ4BSE_PlayEffectBetween( railTrailFx, railOrigin, railTrace.endpos, railFxAxis );\n\t\t}\n\n\t\tif ( railTrace.fraction < 1.0f ) {\n\t\t\tidEntity *railHit = gameLocal.GetTraceEntity( railTrace );\n\t\t\tif ( !gameLocal.isClient && railHit && railHit->fl.takedamage ) {\n\t\t\t\trailHit->Damage( owner, owner, railDir, weaponDef->dict.GetString( "def_damage" ), 1.0f, railTrace.c.id );\n\t\t\t}\n\n\t\t\tconst char *impactFx = NULL;\n\t\t\tif ( railHit && railHit->spawnArgs.GetBool( "bleed" ) ) {\n\t\t\t\timpactFx = weaponDef->dict.GetString( "fx_impact_flesh" );\n\t\t\t} else if ( railTrace.c.material ) {\n\t\t\t\tint surfaceType = railTrace.c.material->GetSurfaceType();\n\t\t\t\tif ( surfaceType == SURFTYPE_NONE ) {\n\t\t\t\t\tsurfaceType = GetDefaultSurfaceType();\n\t\t\t\t}\n\t\t\t\tconst char *surfaceName = gameLocal.sufaceTypeNames[ surfaceType ];\n\t\t\t\timpactFx = weaponDef->dict.GetString( va( "fx_impact_%s", surfaceName ) );\n\t\t\t}\n\t\t\tif ( !impactFx || !impactFx[0] ) {\n\t\t\t\timpactFx = weaponDef->dict.GetString( "fx_impact" );\n\t\t\t}\n\t\t\tif ( impactFx && impactFx[0] ) {\n\t\t\t\tidVec3 impactNormal = railTrace.c.normal;\n\t\t\t\tif ( impactNormal.Normalize() < 0.001f ) impactNormal = -railDir;\n\t\t\t\tQ4BSE_PlayEffectAxis( impactFx, railTrace.endpos, impactNormal.ToMat3() );\n\t\t\t}\n\t\t}\n\n\t\tif ( kick_endtime < gameLocal.realClientTime ) kick_endtime = gameLocal.realClientTime;\n\t\tkick_endtime += muzzle_kick_time;\n\t\tif ( kick_endtime > gameLocal.realClientTime + muzzle_kick_maxtime ) {\n\t\t\tkick_endtime = gameLocal.realClientTime + muzzle_kick_maxtime;\n\t\t}\n\t\tif ( !lightOn ) {\n\t\t\tMuzzleFlashLight();\n\t\t}\n\t\towner->WeaponFireFeedback( &weaponDef->dict );\n\t\tweaponSmokeStartTime = gameLocal.realClientTime;\n\t\treturn;\n\t}\n\n\tif ( !projectileDict.GetNumKeyVals() ) {\n'''
w=replace_exact(w,launch_anchor,rail_branch,'native Railgun launch branch')

# Compile the compatibility weapon state object independently; stock doom_main and
# all stock weapon scripts remain untouched.
program_anchor='''\t// load the default script\n\tif ( defaultScript && *defaultScript ) {\n\t\tCompileFile( defaultScript );\n\t}\n\n\tFinishCompilation();\n'''
program_new='''\t// load the default script\n\tif ( defaultScript && *defaultScript ) {\n\t\tCompileFile( defaultScript );\n\t}\n\n\t// Q4 V20A: Doom 3 host-side state/animation shim for the source-driven Railgun.\n\tCompileFile( "script/weapon_railgun.script" );\n\n\tFinishCompilation();\n'''
s=replace_exact(s,program_anchor,program_new,'Railgun compatibility script loader')

for needle in [
    'spawnArgs.Set( "def_weapon13", "weapon_railgun" )',
    'spawnArgs.Set( "max_ammo_railgun", "35" )',
    '"weapon_rocketlauncher",\n\t\t"weapon_railgun",\n\t\t"weapon_chainsaw"',
    'animPrefix = "plasmagun";',
]:
    if needle not in p: raise SystemExit('V20A Player verification missing '+needle)
for needle in [
    'ammoname, "ammo_railgun"', 'return ( ammo_t )11;', 'return "ammo_railgun";',
    'q4_railgun_runtime', 'Q4BSE_PlayEffectBetween( railTrailFx', 'weaponDef->dict.GetString( "def_damage" )'
]:
    if needle not in w: raise SystemExit('V20A Weapon verification missing '+needle)
if 'CompileFile( "script/weapon_railgun.script" );' not in s:
    raise SystemExit('V20A Script_Program verification failed')

PLAYER.write_text(p,encoding='utf-8')
WEAPON.write_text(w,encoding='utf-8')
PROGRAM.write_text(s,encoding='utf-8')
print('Q4BSE V20A native Railgun patch PASS')
