#!/usr/bin/env python3
'''V18I: native Raven Blaster BSE presentation on the existing Doom 3 weapon slot.

Runs after V18H. Adds only generic BSE capabilities needed by the Q4 Blaster:
  * Q4BSE_PlayEffectBetween() for Raven line effects whose length domain uses
    `useEndOrigin` (the original blaster/trail.fx);
  * normal-vs-charged muzzle FX selection from the pre-created projectile tag
    `q4_bse_charged`;
  * optional weapon `fx_path` playback from the presentation-correct muzzle joint
    to the real 10,000-unit trace endpoint for uncharged shots.

The existing projectile BSE lifecycle remains authoritative for charged fx_fly and
all fx_impact* effects. V18H / Nailgun impact ownership is not changed.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
HEADER = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.h'
IMPACT = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
WEAPON = ROOT / 'neo' / 'game' / 'Weapon.cpp'

for p in (HEADER, IMPACT, WEAPON):
    if not p.exists():
        raise SystemExit(f'ERROR: V18I prerequisite missing: {p}')

header = HEADER.read_text(encoding='utf-8-sig')
impact = IMPACT.read_text(encoding='utf-8-sig')
weapon = WEAPON.read_text(encoding='utf-8-sig')


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V18I expected exactly one {label}, found {hits}')
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# Public BSE endpoint API.
# ---------------------------------------------------------------------------
old_api = '''bool Q4BSE_PlayEffect(const char* fxPath, const idVec3& origin, const idVec3& normal);
bool Q4BSE_PlayEffectAxis(const char* fxPath, const idVec3& origin, const idMat3& axis);
bool Q4BSE_AttachEffectToEntity(const char* fxPath, idEntity* entity);'''
new_api = '''bool Q4BSE_PlayEffect(const char* fxPath, const idVec3& origin, const idVec3& normal);
bool Q4BSE_PlayEffectAxis(const char* fxPath, const idVec3& origin, const idMat3& axis);
bool Q4BSE_PlayEffectBetween(const char* fxPath, const idVec3& origin, const idVec3& endOrigin, const idMat3& axis);
bool Q4BSE_AttachEffectToEntity(const char* fxPath, idEntity* entity);'''
header = replace_once(header, old_api, new_api, 'BSE public API block')

# A transient endpoint is sufficient: useEndOrigin is resolved while the effect's
# one-shot particles are created in StartAllSegments().
impact_anchor = '''static bool g_m3Initialized = false;
static std::vector<M3ImpactInstance*> g_m3Impacts;'''
impact_new = '''static bool g_m3Initialized = false;
static bool g_m3UseEndOrigin = false;
static idVec3 g_m3EndOrigin = vec3_origin;
static std::vector<M3ImpactInstance*> g_m3Impacts;'''
impact = replace_once(impact, impact_anchor, impact_new, 'transient endpoint globals')

# V14 already added localOffset. Resolve Raven's useEndOrigin after normal authored
# length sampling. Convert the world-space endpoint into the current effect's local
# basis so the existing line renderer remains untouched.
old_length = '''    const q4bse::Domain* startLength = FindDomain(pt.start, "length");
    const q4bse::Domain* endLength = FindDomain(pt.end, "length");
    SampleVec3Domain(startLength, p.lengthStart, g_m3Impact.random, NULL);
    SampleVec3Domain(endLength, p.lengthEnd, g_m3Impact.random, NULL);
    ApplyRelative(endLength, p.lengthStart, p.lengthEnd);
    if (transformByNormal) {'''
new_length = '''    const q4bse::Domain* startLength = FindDomain(pt.start, "length");
    const q4bse::Domain* endLength = FindDomain(pt.end, "length");
    SampleVec3Domain(startLength, p.lengthStart, g_m3Impact.random, NULL);
    SampleVec3Domain(endLength, p.lengthEnd, g_m3Impact.random, NULL);
    ApplyRelative(endLength, p.lengthStart, p.lengthEnd);

    if (startLength && startLength->useEndOrigin && g_m3UseEndOrigin) {
        const idVec3 endpointLocal = g_m3Impact.axis.Transpose() * (g_m3EndOrigin - g_m3Impact.origin);
        p.lengthStart = endpointLocal - p.localPosition - p.localOffset;
        p.lengthEnd = p.lengthStart;
    }

    if (transformByNormal) {'''
impact = replace_once(impact, old_length, new_length, 'useEndOrigin length resolution')

old_axis_api = '''bool Q4BSE_PlayEffectAxis(const char* fxPath, const idVec3& origin, const idMat3& axis) {
    if (!g_m3Initialized || !gameRenderWorld || !fxPath || !fxPath[0]) return false;
    M3CachedEffect* cached = GetOrLoadEffect(fxPath);
    if (!cached) return false;
    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), origin, axis, NULL);
}

bool Q4BSE_AttachEffectToEntity(const char* fxPath, idEntity* entity) {'''
new_axis_api = '''bool Q4BSE_PlayEffectAxis(const char* fxPath, const idVec3& origin, const idMat3& axis) {
    if (!g_m3Initialized || !gameRenderWorld || !fxPath || !fxPath[0]) return false;
    M3CachedEffect* cached = GetOrLoadEffect(fxPath);
    if (!cached) return false;
    return StartEffectAtAxis(&cached->effect, cached->path.c_str(), origin, axis, NULL);
}

bool Q4BSE_PlayEffectBetween(const char* fxPath, const idVec3& origin, const idVec3& endOrigin, const idMat3& axis) {
    if (!g_m3Initialized || !gameRenderWorld || !fxPath || !fxPath[0]) return false;
    M3CachedEffect* cached = GetOrLoadEffect(fxPath);
    if (!cached) return false;

    g_m3UseEndOrigin = true;
    g_m3EndOrigin = endOrigin;
    const bool started = StartEffectAtAxis(&cached->effect, cached->path.c_str(), origin, axis, NULL);
    g_m3UseEndOrigin = false;
    g_m3EndOrigin = vec3_origin;
    return started;
}

bool Q4BSE_AttachEffectToEntity(const char* fxPath, idEntity* entity) {'''
impact = replace_once(impact, old_axis_api, new_axis_api, 'PlayEffectBetween implementation')

# ---------------------------------------------------------------------------
# Weapon integration. The charged script pre-creates the same projectile and tags
# it before launch, so the game DLL can choose Raven's charged muzzle FX without
# adding a new Doom 3 script event.
# ---------------------------------------------------------------------------
old_muzzle_select = '''\t\tconst char *q4MuzzleFx = weaponDef->dict.GetString( "fx_muzzleflash" );
\t\tif ( q4MuzzleFx && *q4MuzzleFx && flashJointView != INVALID_JOINT ) {'''
new_muzzle_select = '''\t\tconst bool q4BseChargedShot = projectileEnt && projectileEnt->spawnArgs.GetBool( "q4_bse_charged" );
\t\tconst char *q4MuzzleFx = q4BseChargedShot
\t\t\t? weaponDef->dict.GetString( "fx_chargedflash" )
\t\t\t: weaponDef->dict.GetString( "fx_muzzleflash" );
\t\tif ( q4MuzzleFx && *q4MuzzleFx && flashJointView != INVALID_JOINT ) {'''
weapon = replace_once(weapon, old_muzzle_select, new_muzzle_select, 'normal/charged muzzle selection')

old_play = '''\t\t\t\tQ4BSE_PlayEffectAxis( q4MuzzleFx, q4FxOrigin, q4FxAxis );
\t\t\t}
\t\t}
\t}

\t// add some to the kick time, incrementally moving repeat firing weapons back'''
new_play = '''\t\t\t\tQ4BSE_PlayEffectAxis( q4MuzzleFx, q4FxOrigin, q4FxAxis );

\t\t\t\t// Original Q4 Blaster normal fire is a hitscan visualized with
\t\t\t\t// effects/weapons/blaster/trail.fx. That FX uses useEndOrigin, so
\t\t\t\t// trace once from the exact presented barrel joint and hand the real
\t\t\t\t// endpoint to the BSE runtime. Charged shots are physical projectiles
\t\t\t\t// and deliberately skip this path effect.
\t\t\t\tconst char *q4PathFx = weaponDef->dict.GetString( "fx_path" );
\t\t\t\tif ( !q4BseChargedShot && q4PathFx && *q4PathFx ) {
\t\t\t\t\tconst float q4PathRange = weaponDef->dict.GetFloat( "q4_bse_path_range", "10000" );
\t\t\t\t\ttrace_t q4PathTrace;
\t\t\t\t\tconst idVec3 q4PathEnd = q4FxOrigin + playerViewAxis[0] * q4PathRange;
\t\t\t\t\tgameLocal.clip.TracePoint( q4PathTrace, q4FxOrigin, q4PathEnd, MASK_SHOT_RENDERMODEL, owner );
\t\t\t\t\tQ4BSE_PlayEffectBetween( q4PathFx, q4FxOrigin, q4PathTrace.endpos, q4FxAxis );
\t\t\t\t}
\t\t\t}
\t\t}
\t}

\t// add some to the kick time, incrementally moving repeat firing weapons back'''
weapon = replace_once(weapon, old_play, new_play, 'Blaster path playback')

for required in (
    'Q4BSE_PlayEffectBetween',
    'startLength->useEndOrigin',
    'g_m3Impact.axis.Transpose()',
    'projectileEnt->spawnArgs.GetBool( "q4_bse_charged" )',
    'weaponDef->dict.GetString( "fx_chargedflash" )',
    'weaponDef->dict.GetString( "fx_path" )',
    'q4_bse_path_range',
):
    combined = header + impact + weapon
    if required not in combined:
        raise SystemExit(f'ERROR: V18I verification missing: {required}')

# V18I must not disturb the accepted Nailgun ownership model.
for forbidden in (
    '!q4UseD3ImpactVisuals && ( q4bseImpactFx && *q4bseImpactFx )',
    'const bool q4UseD3ImpactVisuals = spawnArgs.GetBool( "q4UseD3ImpactVisuals" );',
):
    if forbidden in impact or forbidden in weapon:
        raise SystemExit(f'ERROR: V18I found stale V18G ownership override: {forbidden}')

HEADER.write_text(header, encoding='utf-8')
IMPACT.write_text(impact, encoding='utf-8')
WEAPON.write_text(weapon, encoding='utf-8')

print('Q4BSE V18I BLASTER NATIVE BSE PASS.')
print('  - Raven useEndOrigin line FX supported')
print('  - normal Blaster trail uses real presented barrel -> trace endpoint')
print('  - normal/charged Raven muzzle FX selected from projectile tag')
print('  - charged projectile fx_fly remains on existing attached BSE lifecycle')
print('  - projectile fx_impact ownership and V18H Nailgun behavior unchanged')
