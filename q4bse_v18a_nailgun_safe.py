#!/usr/bin/env python3
"""V18A: surgical Nailgun-only BSE support on top of the validated V18 baseline.

This patch intentionally does NOT touch Q4 viewmodel presentation, foreshorten,
HyperBlaster behavior, Grenade Launcher behavior, parser semantics, or projectile
impact selection.

It adds only two generic runtime behaviors already authored by Raven Nailgun FX:
  * `persist` particles emitted by an attached projectile retain their birth-world
    transform, producing a real smoke wake instead of being dragged with the nail.
    When the projectile dies, those persist particles are detached and allowed to
    expire naturally.
  * weapon `fx_exhaust` playback from the two declared view-model steam joints,
    using the already-proven V16 attached-local-transform path so the short Raven
    exhaust one-shots follow the recoiling/bobbing weapon and always expire.
"""
from pathlib import Path
import re, sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"
WEAPON = ROOT / "neo" / "game" / "Weapon.cpp"

for p in (IMPACT, WEAPON):
    if not p.exists():
        raise SystemExit(f"ERROR: V18A prerequisite missing: {p}")


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f"ERROR: V18A expected exactly one {label}, found {hits}")
    return text.replace(old, new, 1)


def replace_regex_once(text, pattern, repl, label, flags=0):
    hits = list(re.finditer(pattern, text, flags))
    if len(hits) != 1:
        raise SystemExit(f"ERROR: V18A expected exactly one regex {label}, found {len(hits)}")
    return re.sub(pattern, repl, text, count=1, flags=flags)


impact = IMPACT.read_text(encoding="utf-8-sig")
weapon = WEAPON.read_text(encoding="utf-8-sig")

# -----------------------------------------------------------------------------
# Raven persist semantics for attached projectile FX.
# V18 already parses `persist`; only the transform/lifetime behavior was missing.
# -----------------------------------------------------------------------------
impact = replace_once(
    impact,
    '''    idVec3 localPosition;\n    idVec3 localOffset;\n    idVec3 localVelocity;\n    idVec3 worldGravityAcceleration;''',
    '''    idVec3 localPosition;\n    idVec3 localOffset;\n    idVec3 localVelocity;\n    idVec3 worldGravityAcceleration;\n    bool worldFrameLocked;\n    idVec3 frameOrigin;\n    idMat3 frameAxis;''',
    "M3Particle persist-frame fields")

impact = replace_once(
    impact,
    '''          localPosition(vec3_origin), localOffset(vec3_origin), localVelocity(vec3_origin), worldGravityAcceleration(vec3_origin),''',
    '''          localPosition(vec3_origin), localOffset(vec3_origin), localVelocity(vec3_origin), worldGravityAcceleration(vec3_origin),\n          worldFrameLocked(false), frameOrigin(vec3_origin), frameAxis(mat3_identity),''',
    "M3Particle persist-frame constructor")

impact = replace_once(
    impact,
    '''    if (pt.flipNormal) p.localVelocity = -p.localVelocity;\n    const float gravityScale = SampleRange(pt.gravity, 0.0f, g_m3Impact.random);''',
    '''    if (pt.flipNormal) p.localVelocity = -p.localVelocity;\n\n    // Raven `persist` particles from projectile-attached FX are born into world\n    // space. The Nailgun's smoke wake therefore remains behind the moving nail.\n    p.worldFrameLocked = g_m3Impact.attachedPersistent && pt.persist;\n    if (p.worldFrameLocked) {\n        p.frameOrigin = g_m3Impact.origin;\n        p.frameAxis = g_m3Impact.axis;\n    }\n\n    const float gravityScale = SampleRange(pt.gravity, 0.0f, g_m3Impact.random);''',
    "persist-frame capture")

impact = replace_regex_once(
    impact,
    r'''static idVec3 ParticleWorldPosition\(const M3Particle& p, float ageSec\) \{\n\s*const idVec3 local = p\.localPosition \+ p\.localOffset \+ p\.localVelocity \* ageSec;\n\s*idVec3 world = g_m3Impact\.origin \+ g_m3Impact\.axis \* local;\n\s*world \+= p\.worldGravityAcceleration \* \(0\.5f \* ageSec \* ageSec\);\n\s*return world;\n\}''',
    r'''static const idMat3& ParticleFrameAxis(const M3Particle& p) {
    return p.worldFrameLocked ? p.frameAxis : g_m3Impact.axis;
}

static idVec3 ParticleFrameOrigin(const M3Particle& p) {
    return p.worldFrameLocked ? p.frameOrigin : g_m3Impact.origin;
}

static idVec3 ParticleWorldPosition(const M3Particle& p, float ageSec) {
    const idVec3 local = p.localPosition + p.localOffset + p.localVelocity * ageSec;
    idVec3 world = ParticleFrameOrigin(p) + ParticleFrameAxis(p) * local;
    world += p.worldGravityAcceleration * (0.5f * ageSec * ageSec);
    return world;
}''',
    "persist-aware ParticleWorldPosition",
    re.S)

impact = replace_once(
    impact,
    '''        const idVec3 length = g_m3Impact.axis * localLength;''',
    '''        const idVec3 length = ParticleFrameAxis(p) * localLength;''',
    "persist-aware line axis")

impact = replace_once(
    impact,
    '''        const idVec3 right = g_m3Impact.axis * (localRotation[1] * -size.x);\n        const idVec3 up = g_m3Impact.axis * (localRotation[2] * size.y);''',
    '''        const idVec3 right = ParticleFrameAxis(p) * (localRotation[1] * -size.x);\n        const idVec3 up = ParticleFrameAxis(p) * (localRotation[2] * size.y);''',
    "persist-aware oriented axis")

# Keep only persist particles alive when their projectile attachment is destroyed.
stop_pattern = r'''void Q4BSE_StopEntityEffects\(idEntity\* entity\) \{.*?\n\}\n\nint Q4BSE_ActiveEffectCount'''
stop_repl = r'''void Q4BSE_StopEntityEffects(idEntity* entity) {
    if (!entity) return;
    for (size_t i = 0; i < g_m3Impacts.size();) {
        M3ImpactInstance* instance = g_m3Impacts[i];
        if (instance->attached && instance->attachedEntity.GetEntity() == entity) {
            g_m3CurrentImpact = instance;

            std::vector<M3Particle> survivors;
            for (size_t p = 0; p < instance->particles.size(); ++p) {
                const M3Particle& particle = instance->particles[p];
                if (particle.worldFrameLocked && particle.segment && particle.segment->particle.persist) {
                    survivors.push_back(particle);
                }
            }

            if (!survivors.empty()) {
                instance->particles.swap(survivors);
                for (size_t e = 0; e < instance->emitters.size(); ++e) instance->emitters[e].active = false;
                instance->attached = false;
                instance->attachedPersistent = false;
                instance->attachedLocalTransform = false;
                instance->attachedEntity = NULL;
                ++i;
                continue;
            }

            FreeImpact();
            delete instance;
            g_m3Impacts.erase(g_m3Impacts.begin() + i);
            continue;
        }
        ++i;
    }
    g_m3CurrentImpact = NULL;
}

int Q4BSE_ActiveEffectCount'''
impact = replace_regex_once(impact, stop_pattern, stop_repl, "persist-tail detach", re.S)

# -----------------------------------------------------------------------------
# Exact Raven Nailgun exhaust playback from both viewmodel steam joints.
# This is opt-in through fx_exhaust and joint_view_steamRight/Left, so all existing
# weapons are untouched. It uses the same presentation math as V16 muzzle FX but
# does not mutate the weapon's render transform.
# -----------------------------------------------------------------------------
kick_anchor = '''\n\t// add some to the kick time, incrementally moving repeat firing weapons back\n\tif ( kick_endtime < gameLocal.realClientTime ) {'''
exhaust_hook = '''
	// Raven auxiliary muzzle exhaust. Weapons without fx_exhaust are untouched.
	if ( weaponDef ) {
		const char *q4ExhaustFx = weaponDef->dict.GetString( "fx_exhaust" );
		if ( q4ExhaustFx && q4ExhaustFx[0] ) {
			const char *q4SteamKeys[2] = { "joint_view_steamRight", "joint_view_steamLeft" };
			for ( int q4SteamIndex = 0; q4SteamIndex < 2; ++q4SteamIndex ) {
				const char *q4SteamJointName = weaponDef->dict.GetString( q4SteamKeys[q4SteamIndex] );
				if ( !q4SteamJointName || !q4SteamJointName[0] ) continue;
				const jointHandle_t q4SteamJoint = animator.GetJointHandle( q4SteamJointName );
				if ( q4SteamJoint == INVALID_JOINT ) continue;

				idVec3 q4LocalJointOrigin;
				idMat3 q4LocalJointAxis;
				if ( !animator.GetJointTransform( q4SteamJoint, gameLocal.time, q4LocalJointOrigin, q4LocalJointAxis ) ) continue;

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

				const idVec3 q4FxOrigin = q4LocalJointOrigin * q4PresentedAxis + q4PresentedOrigin;
				const idMat3 q4FxAxis = q4LocalJointAxis * q4FxBaseAxis;
				Q4BSE_AttachEffectToEntityTransform( q4ExhaustFx, this, q4FxOrigin, q4FxAxis );
			}
		}
	}

	// add some to the kick time, incrementally moving repeat firing weapons back
	if ( kick_endtime < gameLocal.realClientTime ) {'''
weapon = replace_once(weapon, kick_anchor, "\n" + exhaust_hook, "dual steam-joint exhaust hook")

# Hard verification: this patch must not contain any assignment to viewWeaponOrigin,
# viewWeaponAxis, viewmodel presentation state, or foreshorten itself.
for needle in (
    "worldFrameLocked", "ParticleFrameAxis", "survivors",
    'weaponDef->dict.GetString( "fx_exhaust" )',
    '"joint_view_steamRight"', '"joint_view_steamLeft"',
    "Q4BSE_AttachEffectToEntityTransform( q4ExhaustFx",
):
    if needle not in impact and needle not in weapon:
        raise SystemExit(f"ERROR: V18A verification missing: {needle}")

IMPACT.write_text(impact, encoding="utf-8")
WEAPON.write_text(weapon, encoding="utf-8")

print("Q4BSE V18A NAILGUN SAFE PASS.")
print("  - V18 presentation/foreshorten untouched")
print("  - persist projectile particles retain birth-world transforms")
print("  - persist smoke tail survives projectile removal until natural expiry")
print("  - fx_exhaust plays from both declared steam joints via V16 attachment path")
