#!/usr/bin/env python3
'''V18P: Quake 4 Rocket Launcher manual guidance + Strogg laser designator.

Runs AFTER V18O. This is deliberately opt-in and additive:
  * q4_manual_guide on a projectile makes it steer toward the owning player's
    current crosshair trace only while BUTTON_ZOOM is held.
  * q4_guided_laser on a weapon renders a thin muzzle-to-trace beam and a tiny
    surface-aligned Strogg target glyph at the trace hit point.
  * BUTTON_ZOOM remains the input transport, but opted-in guide weapons suppress
    Doom 3's camera zoom so right-click behaves as a true alt-fire/designator.

No existing Q4BSE impact/muzzle/trail/explosion behavior is changed.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
WEAPON_H = ROOT / 'neo' / 'game' / 'Weapon.h'
WEAPON_CPP = ROOT / 'neo' / 'game' / 'Weapon.cpp'
PROJECTILE_CPP = ROOT / 'neo' / 'game' / 'Projectile.cpp'
PLAYER_CPP = ROOT / 'neo' / 'game' / 'Player.cpp'

for p in (WEAPON_H, WEAPON_CPP, PROJECTILE_CPP, PLAYER_CPP):
    if not p.exists():
        raise SystemExit(f'ERROR: V18P prerequisite missing: {p}')

weapon_h = WEAPON_H.read_text(encoding='utf-8-sig')
weapon = WEAPON_CPP.read_text(encoding='utf-8-sig')
projectile = PROJECTILE_CPP.read_text(encoding='utf-8-sig')
player = PLAYER_CPP.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V18P expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Weapon API + transient render state.
# ---------------------------------------------------------------------------
weapon_h = replace_once(
    weapon_h,
    '''\tint\t\t\t\t\t\tGetZoomFov( void );''',
    '''\tint\t\t\t\t\t\tGetZoomFov( void );\n\tbool\t\t\t\t\t\tIsQ4GuidedLaserWeapon( void ) const;''',
    'Weapon.h public guide query')

weapon_h = replace_once(
    weapon_h,
    '''\t// view weapon gui light\n\trenderLight_t\t\t\t\tguiLight;\n\tint\t\t\t\t\t\tguiLightHandle;''',
    '''\t// view weapon gui light\n\trenderLight_t\t\t\t\tguiLight;\n\tint\t\t\t\t\t\tguiLightHandle;\n\n\t// Q4 V18P: transient manual-guidance designator visuals. These are renderer\n\t// handles only; they are recreated after loads and never alter weapon state.\n\trenderEntity_t\t\t\t\tq4GuideBeam;\n\tint\t\t\t\t\t\tq4GuideBeamHandle;\n\trenderEntity_t\t\t\t\tq4GuideMarker;\n\tint\t\t\t\t\t\tq4GuideMarkerHandle;''',
    'Weapon.h guide render fields')

weapon_h = replace_once(
    weapon_h,
    '''\tvoid\t\t\t\t\t\tUpdateFlashPosition( void );''',
    '''\tvoid\t\t\t\t\t\tUpdateFlashPosition( void );\n\tvoid\t\t\t\t\t\tUpdateQ4GuideLaser( void );\n\tvoid\t\t\t\t\t\tFreeQ4GuideLaser( void );''',
    'Weapon.h guide helpers')


# Constructor: initialize transient render handles before Clear() can touch them.
weapon = replace_once(
    weapon,
    '''\tmemset( &nozzleGlow, 0, sizeof( nozzleGlow ) );''',
    '''\tmemset( &nozzleGlow, 0, sizeof( nozzleGlow ) );\n\tmemset( &q4GuideBeam, 0, sizeof( q4GuideBeam ) );\n\tmemset( &q4GuideMarker, 0, sizeof( q4GuideMarker ) );''',
    'weapon constructor guide memset')

weapon = replace_once(
    weapon,
    '''\tnozzleGlowHandle\t\t= -1;\n\tmodelDefHandle\t\t\t= -1;''',
    '''\tnozzleGlowHandle\t\t= -1;\n\tq4GuideBeamHandle\t\t= -1;\n\tq4GuideMarkerHandle\t= -1;\n\tmodelDefHandle\t\t\t= -1;''',
    'weapon constructor guide handles')

weapon = replace_once(
    weapon,
    '''void idWeapon::Clear( void ) {\n\tCancelEvents( &EV_Weapon_Clear );''',
    '''void idWeapon::Clear( void ) {\n\tCancelEvents( &EV_Weapon_Clear );\n\tFreeQ4GuideLaser();''',
    'weapon Clear guide cleanup')


# Public query used by Player.cpp to suppress normal camera zoom on this weapon.
zoom_impl_anchor = '''int\tidWeapon::GetZoomFov( void ) {\n\treturn zoomFov;\n}\n'''
zoom_impl_new = zoom_impl_anchor + '''\n/*\n================\nidWeapon::IsQ4GuidedLaserWeapon\n================\n*/\nbool idWeapon::IsQ4GuidedLaserWeapon( void ) const {\n\treturn weaponDef && weaponDef->dict.GetBool( "q4_guided_laser" );\n}\n'''
weapon = replace_once(weapon, zoom_impl_anchor, zoom_impl_new, 'weapon guide public query impl')


# Render helper: actual muzzle beam + surface-aligned Strogg glyph.
laser_impl = r'''
/*
================
idWeapon::FreeQ4GuideLaser
================
*/
void idWeapon::FreeQ4GuideLaser( void ) {
	if ( gameRenderWorld ) {
		if ( q4GuideBeamHandle != -1 ) {
			gameRenderWorld->FreeEntityDef( q4GuideBeamHandle );
			q4GuideBeamHandle = -1;
		}
		if ( q4GuideMarkerHandle != -1 ) {
			gameRenderWorld->FreeEntityDef( q4GuideMarkerHandle );
			q4GuideMarkerHandle = -1;
		}
	} else {
		q4GuideBeamHandle = -1;
		q4GuideMarkerHandle = -1;
	}
}

/*
================
idWeapon::UpdateQ4GuideLaser

The trace is authored from the actual player view so the endpoint is exactly
where the crosshair points. The visible beam begins at the animated muzzle,
then terminates at that same guidance point. On a real surface, a small custom
plane is aligned to the hit normal and carries the Strogg target glyph.
================
*/
void idWeapon::UpdateQ4GuideLaser( void ) {
	if ( !owner || !weaponDef || !weaponDef->dict.GetBool( "q4_guided_laser" ) ||
		 disabled || status == WP_HOLSTERED || IsHidden() ||
		 !( owner->usercmd.buttons & BUTTON_ZOOM ) ) {
		FreeQ4GuideLaser();
		return;
	}

	const float range = weaponDef->dict.GetFloat( "q4_guide_range", "10000" );
	const float width = weaponDef->dict.GetFloat( "q4_guide_beam_width", "0.70" );
	const char* beamMaterialName = weaponDef->dict.GetString( "mtr_q4_guide_beam", "q4rl/guide_beam" );
	const char* markerMaterialName = weaponDef->dict.GetString( "mtr_q4_guide_marker", "q4rl/guide_marker" );
	const char* markerModelName = weaponDef->dict.GetString( "model_q4_guide_marker", "models/weapons/rocketlauncher/q4_guide_marker.ase" );

	trace_t tr;
	const idVec3 traceStart = owner->firstPersonViewOrigin;
	const idVec3 traceEnd = traceStart + owner->firstPersonViewAxis[0] * range;
	gameLocal.clip.TracePoint( tr, traceStart, traceEnd, MASK_SHOT_RENDERMODEL, owner );

	idVec3 beamStart;
	idMat3 beamAxis;
	if ( flashJointView == INVALID_JOINT || !GetGlobalJointTransform( true, flashJointView, beamStart, beamAxis ) ) {
		beamStart = viewWeaponOrigin + viewWeaponAxis[0] * 16.0f;
		beamAxis = viewWeaponAxis;
	}

	if ( q4GuideBeamHandle == -1 ) {
		memset( &q4GuideBeam, 0, sizeof( q4GuideBeam ) );
		q4GuideBeam.hModel = renderModelManager->FindModel( "_BEAM" );
		q4GuideBeam.customShader = declManager->FindMaterial( beamMaterialName );
		q4GuideBeam.noShadow = true;
		q4GuideBeam.noSelfShadow = true;
		q4GuideBeam.allowSurfaceInViewID = owner->entityNumber + 1;
		q4GuideBeam.shaderParms[ SHADERPARM_RED ] = 1.0f;
		q4GuideBeam.shaderParms[ SHADERPARM_GREEN ] = 1.0f;
		q4GuideBeam.shaderParms[ SHADERPARM_BLUE ] = 1.0f;
		q4GuideBeam.shaderParms[ SHADERPARM_ALPHA ] = 1.0f;
		q4GuideBeam.shaderParms[ SHADERPARM_BEAM_WIDTH ] = width;
		q4GuideBeamHandle = gameRenderWorld->AddEntityDef( &q4GuideBeam );
	}

	q4GuideBeam.origin = beamStart;
	q4GuideBeam.axis = mat3_identity;
	q4GuideBeam.shaderParms[ SHADERPARM_BEAM_WIDTH ] = width;
	q4GuideBeam.shaderParms[ SHADERPARM_BEAM_END_X ] = tr.endpos.x;
	q4GuideBeam.shaderParms[ SHADERPARM_BEAM_END_Y ] = tr.endpos.y;
	q4GuideBeam.shaderParms[ SHADERPARM_BEAM_END_Z ] = tr.endpos.z;
	gameRenderWorld->UpdateEntityDef( q4GuideBeamHandle, &q4GuideBeam );

	// The target glyph only exists when the designator actually touches a surface.
	if ( tr.fraction >= 1.0f ) {
		if ( q4GuideMarkerHandle != -1 ) {
			gameRenderWorld->FreeEntityDef( q4GuideMarkerHandle );
			q4GuideMarkerHandle = -1;
		}
		return;
	}

	idVec3 normal = tr.c.normal;
	if ( normal.Normalize() < 0.001f ) {
		normal = -owner->firstPersonViewAxis[0];
	}

	idMat3 markerAxis;
	markerAxis[0] = normal;
	markerAxis[2] = owner->firstPersonViewAxis[2] - normal * ( owner->firstPersonViewAxis[2] * normal );
	if ( markerAxis[2].Normalize() < 0.001f ) {
		normal.NormalVectors( markerAxis[1], markerAxis[2] );
	} else {
		markerAxis[1] = markerAxis[2].Cross( markerAxis[0] );
		markerAxis[1].Normalize();
	}

	if ( q4GuideMarkerHandle == -1 ) {
		memset( &q4GuideMarker, 0, sizeof( q4GuideMarker ) );
		q4GuideMarker.hModel = renderModelManager->FindModel( markerModelName );
		q4GuideMarker.customShader = declManager->FindMaterial( markerMaterialName );
		q4GuideMarker.noShadow = true;
		q4GuideMarker.noSelfShadow = true;
		q4GuideMarker.allowSurfaceInViewID = owner->entityNumber + 1;
		q4GuideMarker.shaderParms[ SHADERPARM_RED ] = 1.0f;
		q4GuideMarker.shaderParms[ SHADERPARM_GREEN ] = 1.0f;
		q4GuideMarker.shaderParms[ SHADERPARM_BLUE ] = 1.0f;
		q4GuideMarker.shaderParms[ SHADERPARM_ALPHA ] = 1.0f;
		q4GuideMarkerHandle = gameRenderWorld->AddEntityDef( &q4GuideMarker );
	}

	q4GuideMarker.origin = tr.endpos + normal * 0.35f;
	q4GuideMarker.axis = markerAxis;
	gameRenderWorld->UpdateEntityDef( q4GuideMarkerHandle, &q4GuideMarker );
}

'''

present_anchor = '''/*\n================\nidWeapon::PresentWeapon\n================\n*/\nvoid idWeapon::PresentWeapon( bool showViewModel ) {'''
weapon = replace_once(
    weapon,
    present_anchor,
    laser_impl + present_anchor,
    'guide laser implementation insertion')

weapon = replace_once(
    weapon,
    '''\tif ( status != WP_READY && sndHum ) {\n\t\tStopSound( SND_CHANNEL_BODY, false );\n\t}\n\n\tUpdateSound();''',
    '''\tif ( status != WP_READY && sndHum ) {\n\t\tStopSound( SND_CHANNEL_BODY, false );\n\t}\n\n\t// Q4 V18P: the designator is a presentation-only layer. It is updated after\n\t// the weapon animation/joints so its origin follows the real muzzle exactly.\n\tif ( showViewModel ) {\n\t\tUpdateQ4GuideLaser();\n\t} else {\n\t\tFreeQ4GuideLaser();\n\t}\n\n\tUpdateSound();''',
    'PresentWeapon guide laser update')


# ---------------------------------------------------------------------------
# Manual guided rocket: use the exact same view trace while BUTTON_ZOOM is held.
# Nothing happens to ordinary projectiles because the spawnarg is opt-in.
# ---------------------------------------------------------------------------
projectile_anchor = '''void idProjectile::Think( void ) {\n\n\tif ( thinkFlags & TH_THINK ) {'''
projectile_new = '''void idProjectile::Think( void ) {\n\n\t// Q4 V18P: manual crosshair guidance. The rocket keeps its authored speed;\n\t// only its direction is progressively bent toward the designator endpoint.\n\t// Releasing BUTTON_ZOOM immediately stops steering and preserves the current\n\t// flight vector, matching the intended hold-to-guide interaction.\n\tif ( state == LAUNCHED && spawnArgs.GetBool( "q4_manual_guide" ) &&\n\t\t owner.GetEntity() && owner.GetEntity()->IsType( idPlayer::Type ) ) {\n\t\tidPlayer* guidePlayer = static_cast<idPlayer*>( owner.GetEntity() );\n\t\tif ( guidePlayer->usercmd.buttons & BUTTON_ZOOM ) {\n\t\t\tconst float guideRange = spawnArgs.GetFloat( "q4_guide_range", "10000" );\n\t\t\tconst float turnRate = spawnArgs.GetFloat( "q4_guide_turn_rate", "260" );\n\t\t\ttrace_t guideTrace;\n\t\t\tconst idVec3 guideStart = guidePlayer->firstPersonViewOrigin;\n\t\t\tconst idVec3 guideEnd = guideStart + guidePlayer->firstPersonViewAxis[0] * guideRange;\n\t\t\tgameLocal.clip.TracePoint( guideTrace, guideStart, guideEnd, MASK_SHOT_RENDERMODEL, guidePlayer );\n\n\t\t\tidVec3 velocity = physicsObj.GetLinearVelocity();\n\t\t\tconst float projectileSpeed = velocity.Normalize();\n\t\t\tidVec3 desired = guideTrace.endpos - physicsObj.GetOrigin();\n\t\t\tif ( projectileSpeed > 1.0f && desired.Normalize() > 0.001f ) {\n\t\t\t\tconst float dot = idMath::ClampFloat( -1.0f, 1.0f, velocity * desired );\n\t\t\t\tconst float angleDeg = RAD2DEG( idMath::ACos( dot ) );\n\t\t\t\tconst float maxTurnDeg = turnRate * MS2SEC( gameLocal.GetMSec() );\n\t\t\t\tconst float frac = ( angleDeg > maxTurnDeg && angleDeg > 0.001f ) ? ( maxTurnDeg / angleDeg ) : 1.0f;\n\t\t\t\tidVec3 newDir = velocity * ( 1.0f - frac ) + desired * frac;\n\t\t\t\tif ( newDir.Normalize() > 0.001f ) {\n\t\t\t\t\tphysicsObj.SetLinearVelocity( newDir * projectileSpeed );\n\t\t\t\t\tidMat3 q4GuideAxis = newDir.ToMat3();\n\t\t\t\t\tif ( !spawnArgs.GetBool( "q4_projectile_forward_x" ) ) {\n\t\t\t\t\t\tidVec3 tmp = q4GuideAxis[2];\n\t\t\t\t\t\tq4GuideAxis[2] = q4GuideAxis[0];\n\t\t\t\t\t\tq4GuideAxis[0] = -tmp;\n\t\t\t\t\t}\n\t\t\t\t\tphysicsObj.SetAxis( q4GuideAxis );\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n\n\tif ( thinkFlags & TH_THINK ) {'''
projectile = replace_once(projectile, projectile_anchor, projectile_new, 'manual guide Think hook')


# ---------------------------------------------------------------------------
# BUTTON_ZOOM becomes a true alt-fire/designator input on opted-in weapons,
# rather than also narrowing the camera FOV.
# ---------------------------------------------------------------------------
zoom_input_old = '''\t// zooming\n\tif ( ( usercmd.buttons ^ oldCmd.buttons ) & BUTTON_ZOOM ) {\n\t\tif ( ( usercmd.buttons & BUTTON_ZOOM ) && weapon.GetEntity() ) {\n\t\t\tzoomFov.Init( gameLocal.time, 200.0f, CalcFov( false ), weapon.GetEntity()->GetZoomFov() );\n\t\t} else {\n\t\t\tzoomFov.Init( gameLocal.time, 200.0f, zoomFov.GetCurrentValue( gameLocal.time ), DefaultFov() );\n\t\t}\n\t}'''
zoom_input_new = '''\t// zooming. Q4 V18P guide weapons reuse BUTTON_ZOOM as alt-fire, so they\n\t// deliberately keep the normal camera FOV while the designator is held.\n\tif ( ( usercmd.buttons ^ oldCmd.buttons ) & BUTTON_ZOOM ) {\n\t\tif ( ( usercmd.buttons & BUTTON_ZOOM ) && weapon.GetEntity() &&\n\t\t\t !weapon.GetEntity()->IsQ4GuidedLaserWeapon() ) {\n\t\t\tzoomFov.Init( gameLocal.time, 200.0f, CalcFov( false ), weapon.GetEntity()->GetZoomFov() );\n\t\t} else {\n\t\t\tzoomFov.Init( gameLocal.time, 200.0f, zoomFov.GetCurrentValue( gameLocal.time ), DefaultFov() );\n\t\t}\n\t}'''
player = replace_once(player, zoom_input_old, zoom_input_new, 'Player BUTTON_ZOOM guide suppression')

fov_old = '''\t\tfov = ( honorZoom && usercmd.buttons & BUTTON_ZOOM ) && weapon.GetEntity() ? weapon.GetEntity()->GetZoomFov() : DefaultFov();'''
fov_new = '''\t\tfov = ( honorZoom && ( usercmd.buttons & BUTTON_ZOOM ) && weapon.GetEntity() &&\n\t\t\t !weapon.GetEntity()->IsQ4GuidedLaserWeapon() ) ? weapon.GetEntity()->GetZoomFov() : DefaultFov();'''
player = replace_once(player, fov_old, fov_new, 'Player CalcFov guide suppression')


combined = weapon_h + weapon + projectile + player
for required in (
    'IsQ4GuidedLaserWeapon',
    'UpdateQ4GuideLaser',
    'FreeQ4GuideLaser',
    'q4_guided_laser',
    'q4_manual_guide',
    'q4_guide_turn_rate',
    'SHADERPARM_BEAM_END_X',
    'model_q4_guide_marker',
    'BUTTON_ZOOM',
    'q4_projectile_forward_x',
):
    if required not in combined:
        raise SystemExit(f'ERROR: V18P verification missing: {required}')

# V18O/BSE must still be present; this patch is not allowed to replace it.
for required in (
    'q4_projectile_forward_x',
    'Q4BSE_AttachEffectToEntity',
):
    if required not in projectile:
        raise SystemExit(f'ERROR: V18P cumulative prerequisite disappeared from Projectile.cpp: {required}')

WEAPON_H.write_text(weapon_h, encoding='utf-8')
WEAPON_CPP.write_text(weapon, encoding='utf-8')
PROJECTILE_CPP.write_text(projectile, encoding='utf-8')
PLAYER_CPP.write_text(player, encoding='utf-8')

print('Q4BSE V18P ROCKET GUIDANCE / STROGG DESIGNATOR PASS.')
print('  - hold BUTTON_ZOOM to cast muzzle laser and surface target glyph')
print('  - opted-in rockets steer toward the exact same crosshair trace endpoint')
print('  - release stops steering immediately; existing flight vector continues')
print('  - guide weapons suppress Doom 3 camera zoom while alt-fire is held')
print('  - all prior Rocket Launcher/BSE visuals and gameplay remain untouched')
