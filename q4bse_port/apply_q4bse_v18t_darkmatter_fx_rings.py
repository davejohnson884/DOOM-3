#!/usr/bin/env python3
'''V18T: Quake 4 Dark Matter Gun visual/runtime parity pass.

Runs after V18S. Adds only opt-in/generic capabilities needed by the Q4 Dark
Matter Gun BFG-slot port:
  * Raven electricity particle primitive parsing/rendering
  * Dark Matter sphere-domain sampling (Rocket sphere behavior retained)
  * authored particle acceleration and animated offset support
  * persistent entity-local weapon core FX API + path-scoped stop API
  * opt-in Dark Matter viewmodel ring rotation and core/core_start lifecycle

Travelling Dark Matter radius damage/suction is deliberately NOT implemented in
this pass. Existing accepted Q4 weapon behavior is unchanged unless the weapon
carries q4_darkmatter_runtime 1 or an effect uses the newly-supported primitive.
'''

from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PARSER_H = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4FxParser.h'
PARSER_CPP = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4FxParser.cpp'
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
HEADER = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.h'
WEAPON = ROOT / 'neo' / 'game' / 'Weapon.cpp'

for p in (PARSER_H, PARSER_CPP, IMPACT, HEADER, WEAPON):
    if not p.exists():
        raise SystemExit(f'ERROR: V18T prerequisite missing: {p}')

ph = PARSER_H.read_text(encoding='utf-8-sig')
pc = PARSER_CPP.read_text(encoding='utf-8-sig')
impact = IMPACT.read_text(encoding='utf-8-sig')
header = HEADER.read_text(encoding='utf-8-sig')
weapon = WEAPON.read_text(encoding='utf-8-sig')

def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V18T expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)

# Parser: electricity + jitter metadata.
ph = replace_once(
    ph,
    '''    std::string material;
    bool generatedNormal;''',
    '''    std::string material;
    std::vector<float> jitterSize;
    std::string jitterTable;
    bool generatedNormal;''',
    'electricity parser fields')

pc = replace_once(
    pc,
    '''        if (ts.peek() == "linearSpacing") { ts.get(); d.linearSpacing = true; continue; }''',
    '''        if (ts.peek() == "linearSpacing") { ts.get(); d.linearSpacing = true; continue; }
        if (ts.peek() == "attenuate") { ts.get(); continue; }''',
    'attenuate domain modifier')

pc = replace_once(
    pc,
    '''        else if (k == "material") p.material = ts.get();
        else if (k == "generatedNormal") p.generatedNormal = true;''',
    '''        else if (k == "material") p.material = ts.get();
        else if (k == "fork") { (void)ToFloat(ts.get()); }
        else if (k == "jitterRate") { (void)ToFloat(ts.get()); }
        else if (k == "jitterSize") {
            p.jitterSize.clear();
            p.jitterSize.push_back(ToFloat(ts.get()));
            while (ts.accept(",")) { p.jitterSize.push_back(ToFloat(ts.get())); }
        }
        else if (k == "jitterTable") p.jitterTable = ts.get();
        else if (k == "generatedNormal") p.generatedNormal = true;''',
    'electricity particle keywords')

pc = replace_once(
    pc,
    '''    return s == "sprite" || s == "line" || s == "oriented" || s == "decal" || s == "model" || s == "trail" || s == "light";''',
    '''    return s == "sprite" || s == "line" || s == "oriented" || s == "decal" || s == "model" || s == "trail" || s == "light" || s == "electricity";''',
    'electricity primitive registration')

# Runtime particle state.
impact = replace_once(
    impact,
    '''    idVec3 localOffset;
    idVec3 localVelocity;''',
    '''    idVec3 localOffset;
    idVec3 localOffsetEnd;
    idVec3 localVelocity;
    idVec3 localAcceleration;''',
    'particle acceleration/offset fields')

impact = replace_once(
    impact,
    '''localPosition(vec3_origin), localOffset(vec3_origin), localVelocity(vec3_origin),''',
    '''localPosition(vec3_origin), localOffset(vec3_origin), localOffsetEnd(vec3_origin), localVelocity(vec3_origin), localAcceleration(vec3_origin),''',
    'particle acceleration/offset constructor')

impact = replace_once(
    impact,
    '''g_m3Impact.effectPath.find("effects/weapons/rocketlauncher/") != std::string::npos) {''',
    '''(g_m3Impact.effectPath.find("effects/weapons/rocketlauncher/") != std::string::npos ||
              g_m3Impact.effectPath.find("effects/weapons/dmg/") != std::string::npos)) {''',
    'Dark Matter sphere sampler scope')

impact = replace_once(
    impact,
    '''    if (pt.primitive != "sprite" && pt.primitive != "line" && pt.primitive != "oriented") return false;''',
    '''    if (pt.primitive != "sprite" && pt.primitive != "line" && pt.primitive != "oriented" && pt.primitive != "electricity") return false;''',
    'electricity particle spawn filter')

impact = replace_once(
    impact,
    '''    SampleVec3Domain(FindDomain(pt.start, "offset"), p.localOffset, g_m3Impact.random, NULL);
    SampleVec3Domain(FindDomain(pt.start, "velocity"), p.localVelocity, g_m3Impact.random, NULL);''',
    '''    SampleVec3Domain(FindDomain(pt.start, "offset"), p.localOffset, g_m3Impact.random, NULL);
    p.localOffsetEnd = p.localOffset;
    SampleVec3Domain(FindDomain(pt.end, "offset"), p.localOffsetEnd, g_m3Impact.random, NULL);
    ApplyRelative(FindDomain(pt.end, "offset"), p.localOffset, p.localOffsetEnd);
    SampleVec3Domain(FindDomain(pt.start, "velocity"), p.localVelocity, g_m3Impact.random, NULL);
    SampleVec3Domain(FindDomain(pt.start, "acceleration"), p.localAcceleration, g_m3Impact.random, NULL);''',
    'offset/acceleration sampling')

impact = replace_once(
    impact,
    '''    if (transformByNormal) p.localVelocity = generatedNormal.ToMat3() * p.localVelocity;
    if (pt.flipNormal) p.localVelocity = -p.localVelocity;''',
    '''    if (transformByNormal) {
        const idMat3 generatedAxis = generatedNormal.ToMat3();
        p.localVelocity = generatedAxis * p.localVelocity;
        p.localAcceleration = generatedAxis * p.localAcceleration;
    }
    if (pt.flipNormal) {
        p.localVelocity = -p.localVelocity;
        p.localAcceleration = -p.localAcceleration;
    }''',
    'generated-normal acceleration transform')

old_line_size = '''    if (pt.primitive == "line") {'''
if impact.count(old_line_size) < 1:
    raise SystemExit('ERROR: V18T missing line-like size sampling anchor')
impact = impact.replace(
    old_line_size,
    '''    if (pt.primitive == "line" || pt.primitive == "electricity") {''',
    1)

old_pos_pattern = re.compile(r'''static idVec3 ParticleWorldPosition\(const M3Particle& p, float ageSec\) \{.*?\n\}''', re.S)
m = old_pos_pattern.search(impact)
if not m:
    raise SystemExit('ERROR: V18T could not find ParticleWorldPosition')
new_pos = '''static idVec3 ParticleWorldPosition(const M3Particle& p, float ageSec) {
    idVec3 localOffset = p.localOffset;
    if (p.segment && p.durationSec > M3_EPSILON) {
        const q4bse::ParticleTemplate& pt = p.segment->particle;
        const q4bse::Domain* offsetMotion = FindDomain(pt.motion, "offset");
        if (offsetMotion) {
            const float life = Clamp01(ageSec / p.durationSec);
            localOffset = EvalVec3(p.localOffset, p.localOffsetEnd, offsetMotion, life);
        }
    }
    const idVec3 local = p.localPosition + localOffset + p.localVelocity * ageSec +
                         p.localAcceleration * (0.5f * ageSec * ageSec);
    idVec3 world;
    if (p.persistWorld) {
        world = p.worldSpawnOrigin + p.worldSpawnAxis * local;
    } else {
        world = g_m3Impact.origin + g_m3Impact.axis * local;
    }
    world += p.worldGravityAcceleration * (0.5f * ageSec * ageSec);
    return world;
}'''
impact = impact[:m.start()] + new_pos + impact[m.end():]

line_anchor = '''    if (pt.primitive == "oriented") {'''
line_anchor_index = impact.rfind(line_anchor)
if line_anchor_index < 0:
    raise SystemExit('ERROR: V18T oriented render anchor not found')
electricity_render = r'''    if (pt.primitive == "electricity") {
        const float width = idMath::Fabs(EvalFloat(p.sizeStart.x, p.sizeEnd.x, FindDomain(pt.motion, "size"), life));
        const idVec3 localLength = EvalVec3(p.lengthStart, p.lengthEnd, FindDomain(pt.motion, "length"), life);
        const idVec3 worldLength = g_m3Impact.axis * localLength;
        const idVec3 end = worldPos + worldLength;
        idVec3 boltDir = end - worldPos;
        const float boltLen = boltDir.Normalize();
        if (boltLen <= M3_EPSILON) return false;

        idVec3 jitterA, jitterB;
        boltDir.NormalVectors(jitterA, jitterB);
        float jitterAmpA = 0.0f;
        float jitterAmpB = 0.0f;
        if (!pt.jitterSize.empty()) {
            jitterAmpA = idMath::Fabs(pt.jitterSize.size() > 1 ? pt.jitterSize[1] : pt.jitterSize[0]);
            jitterAmpB = idMath::Fabs(pt.jitterSize.size() > 2 ? pt.jitterSize[2] : pt.jitterSize[0]);
        }

        enum { Q4_ELEC_STEPS = 6, Q4_ELEC_VERTS = (Q4_ELEC_STEPS + 1) * 2, Q4_ELEC_INDEXES = Q4_ELEC_STEPS * 6 };
        idVec3 centers[Q4_ELEC_STEPS + 1];
        idVec3 points[Q4_ELEC_VERTS];
        float uv[Q4_ELEC_VERTS * 2];
        int indexes[Q4_ELEC_INDEXES];

        const float seed = (float)(p.segmentIndex * 17 + idMath::FtoiFast(p.birthSec * 1000.0f) * 3);
        for (int i = 0; i <= Q4_ELEC_STEPS; ++i) {
            const float t = (float)i / (float)Q4_ELEC_STEPS;
            centers[i] = worldPos + (end - worldPos) * t;
            if (i > 0 && i < Q4_ELEC_STEPS) {
                const float edge = idMath::Sin(idMath::PI * t);
                const float phase = seed * 0.173f + (float)i * 2.417f;
                centers[i] += jitterA * (idMath::Sin(phase) * jitterAmpA * 0.42f * edge);
                centers[i] += jitterB * (idMath::Cos(phase * 1.37f) * jitterAmpB * 0.42f * edge);
            }
        }
        for (int i = 0; i <= Q4_ELEC_STEPS; ++i) {
            idVec3 tangent;
            if (i == 0) tangent = centers[1] - centers[0];
            else if (i == Q4_ELEC_STEPS) tangent = centers[i] - centers[i - 1];
            else tangent = centers[i + 1] - centers[i - 1];
            if (tangent.LengthSqr() > M3_EPSILON) tangent.NormalizeFast(); else tangent = boltDir;
            idVec3 toView = viewOrigin - centers[i];
            idVec3 side = tangent.Cross(toView);
            if (side.LengthSqr() > M3_EPSILON) side.NormalizeFast(); else side = viewAxis[1];
            side *= width;
            points[i * 2 + 0] = centers[i] + side;
            points[i * 2 + 1] = centers[i] - side;
            const float u = (float)i / (float)Q4_ELEC_STEPS;
            uv[(i * 2 + 0) * 2 + 0] = u; uv[(i * 2 + 0) * 2 + 1] = 0.0f;
            uv[(i * 2 + 1) * 2 + 0] = u; uv[(i * 2 + 1) * 2 + 1] = 1.0f;
        }
        for (int i = 0; i < Q4_ELEC_STEPS; ++i) {
            const int v = i * 2;
            const int k = i * 6;
            indexes[k + 0] = v + 0; indexes[k + 1] = v + 1; indexes[k + 2] = v + 3;
            indexes[k + 3] = v + 0; indexes[k + 4] = v + 3; indexes[k + 5] = v + 2;
        }
        return AddSurface(model, pt, points, uv, Q4_ELEC_VERTS, indexes, Q4_ELEC_INDEXES, color);
    }
'''
impact = impact[:line_anchor_index] + electricity_render + impact[line_anchor_index:]

# Persistent local-transform weapon FX API.
header_lines = header.splitlines(True)
api_line_indexes = [i for i, line in enumerate(header_lines) if 'Q4BSE_AttachEffectToEntityTransform' in line]
if len(api_line_indexes) != 1:
    raise SystemExit(f'ERROR: V18T persistent attachment declaration anchor count={len(api_line_indexes)}')
api_i = api_line_indexes[0]
header_lines.insert(api_i + 1,
    'bool Q4BSE_AttachPersistentEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis);\n'
    'void Q4BSE_StopEntityEffectPath(idEntity* entity, const char* fxPath);\n')
header = ''.join(header_lines)

attach_marker = '''void Q4BSE_StopEntityEffects(idEntity* entity) {'''
if impact.count(attach_marker) != 1:
    raise SystemExit(f'ERROR: V18T StopEntityEffects anchor count={impact.count(attach_marker)}')
new_api_impl = r'''bool Q4BSE_AttachPersistentEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis) {
    if (!g_m3Initialized || !gameRenderWorld || !fxPath || !fxPath[0] || !entity || !entity->GetPhysics()) return false;
    M3CachedEffect* cached = GetOrLoadEffect(fxPath);
    if (!cached) return false;
    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), worldOrigin, worldAxis, entity, true, true);
}

void Q4BSE_StopEntityEffectPath(idEntity* entity, const char* fxPath) {
    if (!entity || !fxPath || !fxPath[0]) return;
    for (size_t i = 0; i < g_m3Impacts.size();) {
        M3ImpactInstance* instance = g_m3Impacts[i];
        if (instance->attached && instance->attachedEntity.GetEntity() == entity &&
            !idStr::Icmp(instance->effectPath.c_str(), fxPath)) {
            g_m3CurrentImpact = instance;
            FreeImpact();
            delete instance;
            g_m3Impacts.erase(g_m3Impacts.begin() + i);
            continue;
        }
        ++i;
    }
    g_m3CurrentImpact = NULL;
}

'''
impact = impact.replace(attach_marker, new_api_impl + attach_marker, 1)

# Weapon-side Dark Matter ring/core lifecycle. Private spawnargs avoid ABI changes.
weapon_anchor = '''	// only show the surface in player view
	renderEntity.allowSurfaceInViewID = owner->entityNumber+1;'''
if weapon.count(weapon_anchor) != 1:
    raise SystemExit(f'ERROR: V18T weapon presentation anchor count={weapon.count(weapon_anchor)}')

weapon_block = r'''	// Q4 V18T: Dark Matter Gun procedural ring/core presentation.
	if ( weaponDef && weaponDef->dict.GetBool( "q4_darkmatter_runtime" ) ) {
		idAnimBlend *q4DmgAnim = animator.CurrentAnim( ANIMCHANNEL_ALL );
		const char *q4DmgAnimName = q4DmgAnim ? q4DmgAnim->AnimName() : "";
		const bool q4DmgReloading = q4DmgAnimName && !idStr::Icmp( q4DmgAnimName, "reload" );
		const bool q4DmgIdle = q4DmgAnimName && !idStr::Icmp( q4DmgAnimName, "idle" );
		const bool q4DmgRingsShouldRun = q4DmgReloading || q4DmgIdle;

		int q4DmgLastRingTime = spawnArgs.GetInt( "_q4_dmg_ring_last_time", "0" );
		if ( q4DmgLastRingTime <= 0 ) q4DmgLastRingTime = gameLocal.time;
		float q4DmgDt = ( gameLocal.time - q4DmgLastRingTime ) * 0.001f;
		if ( q4DmgDt < 0.0f ) q4DmgDt = 0.0f;
		if ( q4DmgDt > 0.050f ) q4DmgDt = 0.050f;
		spawnArgs.Set( "_q4_dmg_ring_last_time", va( "%d", gameLocal.time ) );

		if ( q4DmgRingsShouldRun ) {
			float q4DmgSpeedScale = 1.0f;
			if ( q4DmgReloading && q4DmgAnim ) {
				const float q4ChargeDuration = weaponDef->dict.GetFloat( "chargeDuration", "4" );
				float q4RampTime = q4ChargeDuration * 0.5f;
				if ( q4RampTime < 0.001f ) q4RampTime = 0.001f;
				const float q4ReloadElapsed = ( gameLocal.time - q4DmgAnim->GetStartTime() ) * 0.001f;
				q4DmgSpeedScale = q4ReloadElapsed / q4RampTime;
				if ( q4DmgSpeedScale < 0.0f ) q4DmgSpeedScale = 0.0f;
				if ( q4DmgSpeedScale > 1.0f ) q4DmgSpeedScale = 1.0f;
			}

			static const char *q4RingNames[3] = { "outer", "middle", "inner" };
			for ( int q4Ring = 0; q4Ring < 3; ++q4Ring ) {
				const char *q4JointName = weaponDef->dict.GetString( va( "ring_%s_joint", q4RingNames[q4Ring] ) );
				if ( !q4JointName || !q4JointName[0] ) continue;
				const jointHandle_t q4Joint = animator.GetJointHandle( q4JointName );
				if ( q4Joint == INVALID_JOINT ) continue;
				const idAngles q4Velocity = weaponDef->dict.GetAngles( va( "ring_%s_velocity", q4RingNames[q4Ring] ), "0 0 0" );
				const idAngles q4AnglesOld = spawnArgs.GetAngles( va( "_q4_dmg_ring_%s_angles", q4RingNames[q4Ring] ), "0 0 0" );
				idAngles q4AnglesNew = q4AnglesOld;
				q4AnglesNew.pitch += q4Velocity.pitch * q4DmgSpeedScale * q4DmgDt;
				q4AnglesNew.yaw   += q4Velocity.yaw   * q4DmgSpeedScale * q4DmgDt;
				q4AnglesNew.roll  += q4Velocity.roll  * q4DmgSpeedScale * q4DmgDt;
				animator.SetJointAxis( q4Joint, JOINTMOD_LOCAL, q4AnglesNew.ToMat3() );
				spawnArgs.Set( va( "_q4_dmg_ring_%s_angles", q4RingNames[q4Ring] ),
					va( "%f %f %f", q4AnglesNew.pitch, q4AnglesNew.yaw, q4AnglesNew.roll ) );
			}
			spawnArgs.Set( "_q4_dmg_rings_active", "1" );
		} else if ( spawnArgs.GetBool( "_q4_dmg_rings_active" ) ) {
			static const char *q4RingNames[3] = { "outer", "middle", "inner" };
			for ( int q4Ring = 0; q4Ring < 3; ++q4Ring ) {
				const char *q4JointName = weaponDef->dict.GetString( va( "ring_%s_joint", q4RingNames[q4Ring] ) );
				const jointHandle_t q4Joint = ( q4JointName && q4JointName[0] ) ? animator.GetJointHandle( q4JointName ) : INVALID_JOINT;
				if ( q4Joint != INVALID_JOINT ) animator.ClearJoint( q4Joint );
				spawnArgs.Set( va( "_q4_dmg_ring_%s_angles", q4RingNames[q4Ring] ), "0 0 0" );
			}
			spawnArgs.Set( "_q4_dmg_rings_active", "0" );
		}

		const int q4DesiredCoreMode = q4DmgReloading ? 1 : ( q4DmgIdle ? 2 : 0 );
		const int q4CurrentCoreMode = spawnArgs.GetInt( "_q4_dmg_core_mode", "0" );
		if ( q4DesiredCoreMode != q4CurrentCoreMode ) {
			const char *q4CoreStartFx = weaponDef->dict.GetString( "fx_core_start" );
			const char *q4CoreFx = weaponDef->dict.GetString( "fx_core" );
			if ( q4CoreStartFx && q4CoreStartFx[0] ) Q4BSE_StopEntityEffectPath( this, q4CoreStartFx );
			if ( q4CoreFx && q4CoreFx[0] ) Q4BSE_StopEntityEffectPath( this, q4CoreFx );
			StopSound( SND_CHANNEL_VOICE, false );

			if ( q4DesiredCoreMode != 0 ) {
				const char *q4CoreJointName = weaponDef->dict.GetString( "joint_core" );
				const jointHandle_t q4CoreJoint = ( q4CoreJointName && q4CoreJointName[0] ) ? animator.GetJointHandle( q4CoreJointName ) : INVALID_JOINT;
				const char *q4ChosenCoreFx = ( q4DesiredCoreMode == 1 ) ? q4CoreStartFx : q4CoreFx;
				if ( q4CoreJoint != INVALID_JOINT && q4ChosenCoreFx && q4ChosenCoreFx[0] ) {
					idVec3 q4LocalCoreOrigin;
					idMat3 q4LocalCoreAxis;
					if ( animator.GetJointTransform( q4CoreJoint, gameLocal.time, q4LocalCoreOrigin, q4LocalCoreAxis ) ) {
						idVec3 q4PresentedOrigin = viewWeaponOrigin;
						idMat3 q4PresentedAxis = viewWeaponAxis;
						idMat3 q4FxBaseAxis = viewWeaponAxis;
						const char *q4ViewStyleName = weaponDef->dict.GetString( "def_viewStyle" );
						if ( q4ViewStyleName && q4ViewStyleName[0] ) {
							const idDeclEntityDef *q4ViewStyleDef = gameLocal.FindEntityDef( q4ViewStyleName, false );
							if ( q4ViewStyleDef ) {
								const idVec3 q4ViewOffset = q4ViewStyleDef->dict.GetVector( "viewoffset", "0 0 0" );
								const idAngles q4ViewAngles = q4ViewStyleDef->dict.GetAngles( "viewangles", "0 0 0" );
								const float q4Foreshorten = weaponDef->dict.GetFloat( "foreshorten", "1" );
								q4PresentedOrigin += q4ViewOffset * viewWeaponAxis;
								q4FxBaseAxis = q4ViewAngles.ToMat3() * viewWeaponAxis;
								q4PresentedAxis = q4FxBaseAxis;
								q4PresentedAxis[0] *= q4Foreshorten;
							}
						}
						const idVec3 q4CoreOrigin = q4LocalCoreOrigin * q4PresentedAxis + q4PresentedOrigin;
						const idMat3 q4CoreAxis = q4LocalCoreAxis * q4FxBaseAxis;
						Q4BSE_AttachPersistentEffectToEntityTransform( q4ChosenCoreFx, this, q4CoreOrigin, q4CoreAxis );
						StartSound( "snd_rings", SND_CHANNEL_VOICE, 0, false, NULL );
					}
				}
			}
			spawnArgs.Set( "_q4_dmg_core_mode", va( "%d", q4DesiredCoreMode ) );
		}
	}

'''
weapon = weapon.replace(weapon_anchor, weapon_block + weapon_anchor, 1)

combined = ph + pc + impact + header + weapon
for required in (
    '"electricity"', 'jitterSize', 'pt.primitive == "electricity"',
    'effects/weapons/dmg/', 'localAcceleration',
    'Q4BSE_AttachPersistentEffectToEntityTransform',
    'Q4BSE_StopEntityEffectPath', 'q4_darkmatter_runtime',
    'ring_%s_velocity', 'fx_core_start',
):
    if required not in combined:
        raise SystemExit(f'ERROR: V18T verification missing: {required}')

PARSER_H.write_text(ph, encoding='utf-8')
PARSER_CPP.write_text(pc, encoding='utf-8')
IMPACT.write_text(impact, encoding='utf-8')
HEADER.write_text(header, encoding='utf-8')
WEAPON.write_text(weapon, encoding='utf-8')

print('Q4BSE V18T DARK MATTER FX/RINGS PASS.')
print('  - Raven electricity primitive parsed and rendered as a jagged bolt ribbon')
print('  - Dark Matter sphere domains use the proven sphere sampler')
print('  - start acceleration + animated offset are evaluated')
print('  - persistent joint-local weapon core/core_start FX API added')
print('  - Dark Matter ring joints rotate and reload ramps to full authored speed')
print('  - travelling suction/radius damage intentionally NOT added')
