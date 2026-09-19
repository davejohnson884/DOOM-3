#!/usr/bin/env python3
'''V18V: Dark Matter core lock, sprite geometry, and corner-contact detonation.

Runs after V18U.  Scoped to the Dark Matter/BFG port unless a generic API is
being extended.  No travelling suction/radius-damage loop is added.

Changes:
  * joint-driven Dark Matter core FX are externally world-transform driven, so
    the BSE frame service no longer overwrites the exact inner_ring transform
    with the weapon entity's coarser physics transform;
  * Dark Matter sprite quads use proper four-corner billboard geometry instead
    of the older diamond/bow-tie approximation used by the generic bridge;
  * Dark Matter projectile uses Doom 3 MASK_SOLID each Think, matching Raven's
    Q4 MASK_DMGSOLID intent as closely as Doom 3 supports;
  * if a glancing contact numerically stops the zero-gravity projectile without
    delivering a useful detonation callback, a short bounds trace recovers the
    real contact and routes it back through normal Collide().
'''

from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
HEADER = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.h'
WEAPON = ROOT / 'neo' / 'game' / 'Weapon.cpp'
PROJECTILE = ROOT / 'neo' / 'game' / 'Projectile.cpp'

for p in (IMPACT, HEADER, WEAPON, PROJECTILE):
    if not p.exists():
        raise SystemExit(f'ERROR: V18V prerequisite missing: {p}')

impact = IMPACT.read_text(encoding='utf-8-sig')
header = HEADER.read_text(encoding='utf-8-sig')
weapon = WEAPON.read_text(encoding='utf-8-sig')
projectile = PROJECTILE.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V18V expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# BSE instance state: externally-driven attachments keep their owner lifetime
# association, but their world transform is supplied directly by the weapon.
# ---------------------------------------------------------------------------
impact = replace_once(
    impact,
    '''    bool attachedPersistent;
    bool attachedLocalTransform;
    idEntityPtr<idEntity> attachedEntity;''',
    '''    bool attachedPersistent;
    bool attachedLocalTransform;
    bool attachedExternalTransform;
    idEntityPtr<idEntity> attachedEntity;''',
    'external-transform instance field')

impact = replace_once(
    impact,
    '''attached(false), attachedPersistent(false), attachedLocalTransform(false), attachedLocalOrigin(vec3_origin),''',
    '''attached(false), attachedPersistent(false), attachedLocalTransform(false), attachedExternalTransform(false), attachedLocalOrigin(vec3_origin),''',
    'external-transform constructor init')

# Public API.
header = replace_once(
    header,
    '''bool Q4BSE_AttachPersistentEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis);
bool Q4BSE_UpdateEntityEffectTransform(idEntity* entity, const char* fxPath, const idVec3& worldOrigin, const idMat3& worldAxis);''',
    '''bool Q4BSE_AttachPersistentEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis);
bool Q4BSE_AttachDrivenEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis, bool persistent);
bool Q4BSE_UpdateEntityEffectTransform(idEntity* entity, const char* fxPath, const idVec3& worldOrigin, const idMat3& worldAxis);''',
    'driven-effect API declaration')

api_anchor = '''bool Q4BSE_UpdateEntityEffectTransform(idEntity* entity, const char* fxPath, const idVec3& worldOrigin, const idMat3& worldAxis) {'''
if impact.count(api_anchor) != 1:
    raise SystemExit(f'ERROR: V18V driven API insertion anchor count={impact.count(api_anchor)}')

driven_impl = r'''bool Q4BSE_AttachDrivenEffectToEntityTransform(const char* fxPath, idEntity* entity, const idVec3& worldOrigin, const idMat3& worldAxis, bool persistent) {
    if (!g_m3Initialized || !gameRenderWorld || !fxPath || !fxPath[0] || !entity || !entity->GetPhysics()) return false;
    M3CachedEffect* cached = GetOrLoadEffect(fxPath);
    if (!cached) return false;

    if (!StartEffectAtAxis(&cached->effect, cached->path.c_str(), worldOrigin, worldAxis, entity, persistent, false)) {
        return false;
    }

    if (!g_m3Impacts.empty()) {
        M3ImpactInstance* instance = g_m3Impacts.back();
        if (instance->attached && instance->attachedEntity.GetEntity() == entity &&
            !idStr::Icmp(instance->effectPath.c_str(), fxPath)) {
            instance->attachedExternalTransform = true;
            instance->attachedLocalTransform = false;
            instance->origin = worldOrigin;
            instance->axis = worldAxis;
        }
    }
    return true;
}

'''
impact = impact.replace(api_anchor, driven_impl + api_anchor, 1)

# Update API: external attachments receive exact world transform and are not
# converted back through the weapon physics basis.
old_update_body = '''        instance->attachedLocalOrigin = (worldOrigin - attachedOrigin) * attachedAxisTranspose;
        instance->attachedLocalAxis = worldAxis * attachedAxisTranspose;
        instance->attachedLocalTransform = true;
        instance->origin = worldOrigin;
        instance->axis = worldAxis;
        updated = true;'''
new_update_body = '''        if (instance->attachedExternalTransform) {
            instance->origin = worldOrigin;
            instance->axis = worldAxis;
        } else {
            instance->attachedLocalOrigin = (worldOrigin - attachedOrigin) * attachedAxisTranspose;
            instance->attachedLocalAxis = worldAxis * attachedAxisTranspose;
            instance->attachedLocalTransform = true;
            instance->origin = worldOrigin;
            instance->axis = worldAxis;
        }
        updated = true;'''
impact = replace_once(impact, old_update_body, new_update_body, 'external transform update path')

# Frame attachment service: do not overwrite a joint-driven world transform.
old_frame_attach = '''            if (g_m3Impact.attachedLocalTransform) {
                const idVec3 attachedOrigin = attached->GetPhysics()->GetOrigin();
                const idMat3 attachedAxis = attached->GetPhysics()->GetAxis();
                g_m3Impact.origin = attachedOrigin + g_m3Impact.attachedLocalOrigin * attachedAxis;
                g_m3Impact.axis = g_m3Impact.attachedLocalAxis * attachedAxis;
            } else {
                g_m3Impact.origin = attached->GetPhysics()->GetOrigin();
                idVec3 forward = attached->GetPhysics()->GetLinearVelocity();
                if (forward.LengthSqr() > M3_EPSILON) {
                    forward.NormalizeFast();
                    g_m3Impact.axis = forward.ToMat3();
                }
            }'''
new_frame_attach = '''            if (g_m3Impact.attachedExternalTransform) {
                // Exact world transform is refreshed by the owning weapon from
                // the live animated joint every presentation frame.
            } else if (g_m3Impact.attachedLocalTransform) {
                const idVec3 attachedOrigin = attached->GetPhysics()->GetOrigin();
                const idMat3 attachedAxis = attached->GetPhysics()->GetAxis();
                g_m3Impact.origin = attachedOrigin + g_m3Impact.attachedLocalOrigin * attachedAxis;
                g_m3Impact.axis = g_m3Impact.attachedLocalAxis * attachedAxis;
            } else {
                g_m3Impact.origin = attached->GetPhysics()->GetOrigin();
                idVec3 forward = attached->GetPhysics()->GetLinearVelocity();
                if (forward.LengthSqr() > M3_EPSILON) {
                    forward.NormalizeFast();
                    g_m3Impact.axis = forward.ToMat3();
                }
            }'''
impact = replace_once(impact, old_frame_attach, new_frame_attach, 'external transform frame ownership')

# ---------------------------------------------------------------------------
# Dark Matter-only sprite billboard correction.
# The old M3 bridge used four axis points, producing diamond/square artifacts.
# Preserve accepted weapons and correct only effects/weapons/dmg/.
# ---------------------------------------------------------------------------
sprite_pat = re.compile(
    r'(if \\(pt\\.primitive == "sprite"\\) \\{.*?'
    r'const idVec3 right = .*?;\\n'
    r'\\s*const idVec3 up = .*?;\\n)'
    r'\\s*idVec3 points\\[4\\] = \\{[^\\n]+\\};\\n'
    r'(\\s*return AddSurface\\(model, pt, points, st, 4, idx, 6, color\\);)',
    re.S)
sprite_hits = list(sprite_pat.finditer(impact))
if len(sprite_hits) != 1:
    marker = 'pt.primitive == "sprite"'
    pos = impact.find(marker)
    context = impact[max(0, pos - 500):min(len(impact), pos + 1800)] if pos >= 0 else '<sprite marker not found>'
    print('V18V DEBUG SPRITE CONTEXT BEGIN')
    print(context)
    print('V18V DEBUG SPRITE CONTEXT END')
    raise SystemExit(f'ERROR: V18V sprite render branch count={len(sprite_hits)}')
sprite_repl = r'''\\1        idVec3 points[4];
        if (g_m3Impact.effectPath.find("effects/weapons/dmg/") != std::string::npos) {
            points[0] = worldPos - right - up;
            points[1] = worldPos - right + up;
            points[2] = worldPos + right + up;
            points[3] = worldPos + right - up;
        } else {
            // Preserve the already-accepted legacy bridge presentation for
            // previously locked weapons.
            points[0] = worldPos - right;
            points[1] = worldPos - up;
            points[2] = worldPos + right;
            points[3] = worldPos + up;
        }
\\2'''
impact = sprite_pat.sub(sprite_repl, impact, count=1)

# ---------------------------------------------------------------------------
# Weapon: use externally driven FX for both charge-up and persistent idle core.
# ---------------------------------------------------------------------------
weapon = replace_once(
    weapon,
    '''							Q4BSE_AttachEffectToEntityTransform( q4ChosenCoreFx, this, q4CoreOrigin, q4CoreAxis );''',
    '''							Q4BSE_AttachDrivenEffectToEntityTransform( q4ChosenCoreFx, this, q4CoreOrigin, q4CoreAxis, false );''',
    'core_start driven joint attachment')

weapon = replace_once(
    weapon,
    '''							Q4BSE_AttachPersistentEffectToEntityTransform( q4ChosenCoreFx, this, q4CoreOrigin, q4CoreAxis );''',
    '''							Q4BSE_AttachDrivenEffectToEntityTransform( q4ChosenCoreFx, this, q4CoreOrigin, q4CoreAxis, true );''',
    'idle core driven joint attachment')

# ---------------------------------------------------------------------------
# Projectile: Raven rvDarkMatterProjectile sets MASK_DMGSOLID immediately before
# the base projectile Think. Doom 3 has no LARGESHOTCLIP content, so MASK_SOLID
# is the closest exact world-solid equivalent.
# Also recover a rare glancing-contact rest state by tracing the projectile
# bounds through the contact and routing the real trace through Collide().
# ---------------------------------------------------------------------------
think_anchor = '''void idProjectile::Think( void ) {

	if ( thinkFlags & TH_THINK ) {'''
think_new = '''void idProjectile::Think( void ) {

	const bool q4DarkMatterProjectile = spawnArgs.GetBool( "q4_darkmatter_projectile" );
	idVec3 q4DarkMatterPrePhysicsVelocity = vec3_origin;
	if ( q4DarkMatterProjectile ) {
		q4DarkMatterPrePhysicsVelocity = physicsObj.GetLinearVelocity();
		physicsObj.SetClipMask( MASK_SOLID );
	}

	if ( thinkFlags & TH_THINK ) {'''
projectile = replace_once(projectile, think_anchor, think_new, 'Dark Matter pre-physics clip mask')

run_anchor = '''	// run physics
	RunPhysics();

	Present();'''
run_new = '''	// run physics
	RunPhysics();

	// A zero-gravity Dark Matter shot should never naturally come to rest.  If
	// a glancing corner contact leaves the rigid body stopped without a normal
	// projectile detonation callback, recover the actual solid contact and feed
	// it back through the ordinary Collide() path.
	if ( q4DarkMatterProjectile && state == LAUNCHED &&
		physicsObj.GetLinearVelocity().LengthSqr() < 25.0f ) {
		idVec3 q4ImpactVelocity = q4DarkMatterPrePhysicsVelocity;
		if ( q4ImpactVelocity.LengthSqr() < 25.0f ) {
			q4ImpactVelocity = physicsObj.GetAxis()[2] * spawnArgs.GetFloat( "q4_darkmatter_speed", "250" );
		}
		idVec3 q4ImpactDir = q4ImpactVelocity;
		if ( q4ImpactDir.LengthSqr() > 0.001f ) {
			q4ImpactDir.NormalizeFast();
			trace_t q4ContactTrace;
			const idVec3 q4Origin = physicsObj.GetOrigin();
			const idVec3 q4Start = q4Origin - q4ImpactDir * 12.0f;
			const idVec3 q4End = q4Origin + q4ImpactDir * 12.0f;
			if ( gameLocal.clip.TraceBounds( q4ContactTrace, q4Start, q4End,
				physicsObj.GetBounds(), MASK_SOLID, owner.GetEntity() ) ) {
				Collide( q4ContactTrace, q4ImpactVelocity );
			}
		}
	}

	Present();'''
projectile = replace_once(projectile, run_anchor, run_new, 'Dark Matter corner-contact recovery')

combined = impact + header + weapon + projectile
for required in (
    'attachedExternalTransform',
    'Q4BSE_AttachDrivenEffectToEntityTransform',
    'effects/weapons/dmg/',
    'worldPos - right - up',
    'q4_darkmatter_projectile',
    'physicsObj.SetClipMask( MASK_SOLID )',
    'TraceBounds( q4ContactTrace',
):
    if required not in combined:
        raise SystemExit(f'ERROR: V18V verification missing: {required}')

IMPACT.write_text(impact, encoding='utf-8')
HEADER.write_text(header, encoding='utf-8')
WEAPON.write_text(weapon, encoding='utf-8')
PROJECTILE.write_text(projectile, encoding='utf-8')

print('Q4BSE V18V DARK MATTER CORE/SPRITE/COLLISION PASS.')
print('  - core FX world transform is owned directly by the live inner_ring joint')
print('  - Dark Matter sprite billboard geometry corrected without touching locked weapons')
print('  - Dark Matter projectile uses MASK_SOLID like Raven MASK_DMGSOLID intent')
print('  - stopped glancing contacts recover a real bounds trace and detonate normally')
print('  - travelling suction/radius damage still intentionally NOT implemented')
