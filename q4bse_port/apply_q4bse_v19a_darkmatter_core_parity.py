#!/usr/bin/env python3
'''V19A: Dark Matter in-gun core BSE parity reset.

Runs after V18Z. This is intentionally scoped to the Dark Matter CORE/CoreStart
viewmodel effects. Projectile fly/impact/collision/suction are untouched.

The reset is based on Raven/openQ4 BSE behavior rather than further visual
guessing:

1) CORE LIFECYCLE IS EVENT DRIVEN
   Doom 3's weapon script already calls weaponReloading() exactly when Raven's
   State_Reload would call StartRings(true), and weaponReady() when Idle begins.
   Those events now request core_start / idle core explicitly. Firing stops the
   core immediately from Event_LaunchProjectiles, mirroring Raven StopRings()
   before Attack(). The old per-frame animation-name core state machine is
   removed; procedural ring rotation remains intact.

2) CORE BSE GEOMETRY IS EFFECT-LOCAL
   Raven BSE builds particle vertices in effect-local space and lets the owning
   render effect origin/axis transform them. Our bridge historically baked core
   vertices into world space and then applied Doom 3 weaponDepthHack to a
   separate identity entity. That can center the effect yet distort its apparent
   size/orientation. Core/core_start now render in local BSE coordinates with the
   live inner_ring transform on renderEntity, matching rvSegment::Render's owner
   transform model. The V18Y first-person weaponDepthHack is retained.

3) CORE_START IS A TRUE ONE-SHOT
   Reload starts retail fx_core_start once. Reload -> idle layers the persistent
   retail fx_core without killing the one-shot tail, matching Raven StartRings.

No projectile code is changed by this patch.
'''

from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
WEAPON = ROOT / 'neo' / 'game' / 'Weapon.cpp'

for p in (IMPACT, WEAPON):
    if not p.exists():
        raise SystemExit(f'ERROR: V19A prerequisite missing: {p}')

impact = IMPACT.read_text(encoding='utf-8-sig')
weapon = WEAPON.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V19A expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# CORE BSE LOCAL RENDER MODE
# ---------------------------------------------------------------------------
impact = replace_once(
    impact,
    '''    bool attachedPersistent;
    bool attachedLocalTransform;
    idEntityPtr<idEntity> attachedEntity;''',
    '''    bool attachedPersistent;
    bool attachedLocalTransform;
    bool q4ViewLocalGeometry;
    idEntityPtr<idEntity> attachedEntity;''',
    'core local-geometry field')

impact = replace_once(
    impact,
    '''attached(false), attachedPersistent(false), attachedLocalTransform(false), attachedLocalOrigin(vec3_origin),''',
    '''attached(false), attachedPersistent(false), attachedLocalTransform(false), q4ViewLocalGeometry(false), attachedLocalOrigin(vec3_origin),''',
    'core local-geometry constructor')

# Identify only retail Dark Matter core/core_start attachments. Muzzle and all
# projectile effects keep the existing bridge path.
effect_path_anchor = '''    g_m3Impact.effectPath = effectPath ? effectPath : "<unnamed>";'''
effect_path_new = effect_path_anchor + '''
    g_m3Impact.q4ViewLocalGeometry = attachedEntity != NULL && effectPath != NULL &&
        attachedEntity->spawnArgs.GetBool( "q4_darkmatter_runtime" ) &&
        strstr(effectPath, "effects/weapons/dmg/core") != NULL;'''
impact = replace_once(impact, effect_path_anchor, effect_path_new, 'core effect-local mode selection')

# Locked core particles remain in effect-local coordinates. Gravity is irrelevant
# to these authored core effects, so return before world-space conversion.
world_anchor = '''    idVec3 world;
    if (p.persistWorld) {'''
world_new = '''    if (g_m3Impact.q4ViewLocalGeometry) {
        return local;
    }

    idVec3 world;
    if (p.persistWorld) {'''
impact = replace_once(impact, world_anchor, world_new, 'core local particle position')

# Line length is authored in effect-local coordinates.
line_old = '''        const idVec3 length = g_m3Impact.axis * localLength;
        const idVec3 end = worldPos + length;'''
line_new = '''        const idVec3 length = g_m3Impact.q4ViewLocalGeometry ? localLength : (g_m3Impact.axis * localLength);
        const idVec3 end = worldPos + length;'''
impact = replace_once(impact, line_old, line_new, 'core local line length')

# Electricity is line-like and follows the same owner-local rule.
elec_old = '''        const idVec3 worldLength = g_m3Impact.axis * localLength;
        const idVec3 end = worldPos + worldLength;'''
elec_new = '''        const idVec3 worldLength = g_m3Impact.q4ViewLocalGeometry ? localLength : (g_m3Impact.axis * localLength);
        const idVec3 end = worldPos + worldLength;'''
impact = replace_once(impact, elec_old, elec_new, 'core local electricity length')

# Oriented particles are also local to the effect owner.
orient_old = '''        const idVec3 right = g_m3Impact.axis * (localRotation[1] * -size.x);
        const idVec3 up = g_m3Impact.axis * (localRotation[2] * size.y);'''
orient_new = '''        const idMat3 q4RenderAxis = g_m3Impact.q4ViewLocalGeometry ? mat3_identity : g_m3Impact.axis;
        const idVec3 right = q4RenderAxis * (localRotation[1] * -size.x);
        const idVec3 up = q4RenderAxis * (localRotation[2] * size.y);'''
impact = replace_once(impact, orient_old, orient_new, 'core local oriented plane')

# Raven rvSegment::Render transforms camera axes/origin into the effect owner's
# local basis before billboarding. Do the same for the core.
rebuild_old = '''    int rendered = 0;
    for (size_t i = 0; i < g_m3Impact.particles.size(); ++i) {
        if (RenderParticle(g_m3Impact.model, g_m3Impact.particles[i], elapsedSec,
                           player->firstPersonViewOrigin, player->firstPersonViewAxis)) ++rendered;
    }
    g_m3Impact.model->FinishSurfaces();
    if (g_m3Impact.entityHandle >= 0 && gameRenderWorld) gameRenderWorld->UpdateEntityDef(g_m3Impact.entityHandle, &g_m3Impact.renderEntity);'''

rebuild_new = '''    idVec3 q4RenderViewOrigin = player->firstPersonViewOrigin;
    idMat3 q4RenderViewAxis = player->firstPersonViewAxis;

    if (g_m3Impact.q4ViewLocalGeometry) {
        const idMat3 q4OwnerAxisTranspose = g_m3Impact.axis.Transpose();
        q4RenderViewOrigin = q4OwnerAxisTranspose * (player->firstPersonViewOrigin - g_m3Impact.origin);
        q4RenderViewAxis[0] = q4OwnerAxisTranspose * player->firstPersonViewAxis[0];
        q4RenderViewAxis[1] = q4OwnerAxisTranspose * player->firstPersonViewAxis[1];
        q4RenderViewAxis[2] = q4OwnerAxisTranspose * player->firstPersonViewAxis[2];

        // Dynamic BSE model vertices are now local to the live inner_ring.
        g_m3Impact.renderEntity.origin = g_m3Impact.origin;
        g_m3Impact.renderEntity.axis = g_m3Impact.axis;
    } else {
        g_m3Impact.renderEntity.origin = vec3_origin;
        g_m3Impact.renderEntity.axis = mat3_identity;
    }

    int rendered = 0;
    for (size_t i = 0; i < g_m3Impact.particles.size(); ++i) {
        if (RenderParticle(g_m3Impact.model, g_m3Impact.particles[i], elapsedSec,
                           q4RenderViewOrigin, q4RenderViewAxis)) ++rendered;
    }
    g_m3Impact.model->FinishSurfaces();
    if (g_m3Impact.entityHandle >= 0 && gameRenderWorld) gameRenderWorld->UpdateEntityDef(g_m3Impact.entityHandle, &g_m3Impact.renderEntity);'''
impact = replace_once(impact, rebuild_old, rebuild_new, 'Raven owner-local core render basis')


# ---------------------------------------------------------------------------
# EVENT-DRIVEN RAVEN CORE LIFECYCLE
# ---------------------------------------------------------------------------
# Remove V18T/V18U/V18Z's polled core transition/update section while retaining
# all ring-joint rotation code above it.
core_poll_pattern = re.compile(
    r'\n\t\tconst int q4DesiredCoreMode = q4DmgReloading \? 1 : \( q4DmgIdle \? 2 : 0 \);.*?'
    r'\n\t\}\n\n\t// only show the surface in player view',
    re.S)
hits = list(core_poll_pattern.finditer(weapon))
if len(hits) != 1:
    raise SystemExit(f'ERROR: V19A polled core block count={len(hits)}')
weapon = core_poll_pattern.sub(
    '\n\t}\n\n\t// only show the surface in player view',
    weapon, count=1)


# Script event edges map directly to Raven's weapon states.
weapon = replace_once(
    weapon,
    '''void idWeapon::Event_WeaponReady( void ) {
	status = WP_READY;''',
    '''void idWeapon::Event_WeaponReady( void ) {
	status = WP_READY;
	if ( weaponDef && weaponDef->dict.GetBool( "q4_darkmatter_runtime" ) ) {
		// Raven State_Idle -> StartRings(false).
		spawnArgs.Set( "_q4_dmg_core_request", "2" );
	}''',
    'Dark Matter idle core request')

weapon = replace_once(
    weapon,
    '''void idWeapon::Event_WeaponReloading( void ) {
	status = WP_RELOAD;
}''',
    '''void idWeapon::Event_WeaponReloading( void ) {
	status = WP_RELOAD;
	if ( weaponDef && weaponDef->dict.GetBool( "q4_darkmatter_runtime" ) ) {
		// Raven State_Reload -> StartRings(true).
		spawnArgs.Set( "_q4_dmg_core_request", "1" );
	}
}''',
    'Dark Matter recharge request')

weapon = replace_once(
    weapon,
    '''void idWeapon::Event_WeaponLowering( void ) {
	status = WP_LOWERING;''',
    '''void idWeapon::Event_WeaponLowering( void ) {
	status = WP_LOWERING;
	if ( weaponDef && weaponDef->dict.GetBool( "q4_darkmatter_runtime" ) ) {
		spawnArgs.Set( "_q4_dmg_core_request", "0" );
	}''',
    'Dark Matter lower core stop request')

# Firing mirrors Raven StopRings() before Attack(). Do this before any new muzzle
# BSE gets spawned by the launch path.
launch_anchor = '''	if ( IsHidden() ) {
		return;
	}
'''
launch_new = launch_anchor + '''
	if ( weaponDef && weaponDef->dict.GetBool( "q4_darkmatter_runtime" ) ) {
		Q4BSE_StopEntityEffects( this );
		StopSound( SND_CHANNEL_VOICE, false );
		spawnArgs.Set( "_q4_dmg_core_mode", "0" );
		spawnArgs.Set( "_q4_dmg_core_request", "-1" );
	}
'''
weapon = replace_once(weapon, launch_anchor, launch_new, 'Dark Matter fire StopRings parity')


# Replace V18X/Y's final transform-only block with a request consumer at the
# exact final rendered inner_ring transform. This is the only place core FX are
# now created.
exact_pattern = re.compile(
    r'\t// Q4 V18X CORE-ONLY: refresh every attached Dark Matter core instance from.*?'
    r'\n\t\}\n\n(?=\t// present the model)',
    re.S)
hits = list(exact_pattern.finditer(weapon))
if len(hits) != 1:
    raise SystemExit(f'ERROR: V19A V18X/Y exact block count={len(hits)}')

exact_block = r'''	// Q4 V19A: Raven Dark Matter core lifecycle at the exact final presented
	// inner_ring transform. Creation and transform updates happen in the same
	// coordinate space as the rendered gyro.
	if ( q4PresentationActive && weaponDef && weaponDef->dict.GetBool( "q4_darkmatter_runtime" ) ) {
		const int q4CoreRequest = spawnArgs.GetInt( "_q4_dmg_core_request", "-1" );
		int q4CoreMode = spawnArgs.GetInt( "_q4_dmg_core_mode", "0" );
		const bool q4NeedCoreTransform = ( q4CoreMode != 0 ) || ( q4CoreRequest == 1 ) || ( q4CoreRequest == 2 );

		idVec3 q4CoreWorldOrigin = vec3_origin;
		idMat3 q4CoreWorldAxis = mat3_identity;
		bool q4HaveCoreTransform = false;

		if ( q4NeedCoreTransform ) {
			const char *q4CoreJointName = weaponDef->dict.GetString( "joint_core" );
			const jointHandle_t q4CoreJoint = ( q4CoreJointName && q4CoreJointName[0] )
				? animator.GetJointHandle( q4CoreJointName ) : INVALID_JOINT;
			if ( q4CoreJoint != INVALID_JOINT ) {
				idVec3 q4JointLocalOrigin;
				idMat3 q4JointLocalAxis;
				if ( animator.GetJointTransform( q4CoreJoint, gameLocal.time, q4JointLocalOrigin, q4JointLocalAxis ) ) {
					q4CoreWorldOrigin = q4JointLocalOrigin * renderEntity.axis + renderEntity.origin;

					idMat3 q4EffectBaseAxis = renderEntity.axis;
					const float q4Foreshorten = weaponDef->dict.GetFloat( "foreshorten", "1" );
					if ( idMath::Fabs( q4Foreshorten ) > 0.001f ) {
						q4EffectBaseAxis[0] *= ( 1.0f / q4Foreshorten );
					}
					q4CoreWorldAxis = q4JointLocalAxis * q4EffectBaseAxis;
					q4HaveCoreTransform = true;
				}
			}
		}

		if ( q4CoreRequest == 0 ) {
			Q4BSE_StopEntityEffects( this );
			StopSound( SND_CHANNEL_VOICE, false );
			q4CoreMode = 0;
			spawnArgs.Set( "_q4_dmg_core_mode", "0" );
			spawnArgs.Set( "_q4_dmg_core_request", "-1" );
		}
		else if ( q4HaveCoreTransform && q4CoreRequest == 1 ) {
			// Raven StartRings(true): old idle core is gone; one-shot charge begins.
			Q4BSE_StopEntityEffects( this );
			const char *q4CoreStartFx = weaponDef->dict.GetString( "fx_core_start" );
			if ( q4CoreStartFx && q4CoreStartFx[0] ) {
				Q4BSE_AttachEffectToEntityTransform( q4CoreStartFx, this, q4CoreWorldOrigin, q4CoreWorldAxis );
				Q4BSE_SetEntityEffectsViewWeaponMode( this, owner ? owner->entityNumber + 1 : 0 );
			}
			StartSound( "snd_rings", SND_CHANNEL_VOICE, 0, false, NULL );
			q4CoreMode = 1;
			spawnArgs.Set( "_q4_dmg_core_mode", "1" );
			spawnArgs.Set( "_q4_dmg_core_request", "-1" );
		}
		else if ( q4HaveCoreTransform && q4CoreRequest == 2 ) {
			// Raven StartRings(false): if we came from reload, preserve core_start's
			// natural tail and layer the looping idle core over it.
			if ( q4CoreMode != 1 ) {
				Q4BSE_StopEntityEffects( this );
			}
			const char *q4CoreFx = weaponDef->dict.GetString( "fx_core" );
			if ( q4CoreFx && q4CoreFx[0] ) {
				Q4BSE_AttachPersistentEffectToEntityTransform( q4CoreFx, this, q4CoreWorldOrigin, q4CoreWorldAxis );
				Q4BSE_SetEntityEffectsViewWeaponMode( this, owner ? owner->entityNumber + 1 : 0 );
			}
			if ( q4CoreMode == 0 ) {
				StartSound( "snd_rings", SND_CHANNEL_VOICE, 0, false, NULL );
			}
			q4CoreMode = 2;
			spawnArgs.Set( "_q4_dmg_core_mode", "2" );
			spawnArgs.Set( "_q4_dmg_core_request", "-1" );
		}

		if ( q4HaveCoreTransform && q4CoreMode != 0 ) {
			Q4BSE_UpdateEntityEffectsTransform( this, q4CoreWorldOrigin, q4CoreWorldAxis );
			Q4BSE_SetEntityEffectsViewWeaponMode( this, owner ? owner->entityNumber + 1 : 0 );
		}
	}

'''
weapon = exact_pattern.sub(exact_block, weapon, count=1)


combined = impact + weapon
for required in (
    'q4ViewLocalGeometry',
    'q4OwnerAxisTranspose',
    'g_m3Impact.renderEntity.origin = g_m3Impact.origin',
    'Raven State_Reload -> StartRings(true)',
    'Raven State_Idle -> StartRings(false)',
    'Q4 V19A: Raven Dark Matter core lifecycle',
    'Q4BSE_AttachEffectToEntityTransform( q4CoreStartFx',
    'Q4BSE_AttachPersistentEffectToEntityTransform( q4CoreFx',
):
    if required not in combined:
        raise SystemExit(f'ERROR: V19A verification missing: {required}')

# Strong negative gate: old polling state machine must be gone.
if 'const int q4DesiredCoreMode' in weapon:
    raise SystemExit('ERROR: V19A old polled core lifecycle still present')

IMPACT.write_text(impact, encoding='utf-8')
WEAPON.write_text(weapon, encoding='utf-8')

print('Q4BSE V19A DARK MATTER CORE PARITY RESET.')
print('  - core lifecycle driven by weaponReloading/weaponReady/fire events')
print('  - retail core_start starts once and naturally overlaps idle core tail')
print('  - core/core_start geometry rendered in Raven effect-local owner space')
print('  - exact V18Y weaponDepthHack + live inner_ring placement retained')
print('  - projectile / impact / collision / suction untouched')
