#!/usr/bin/env python3
"""Promote the proven M3 Raven FX renderer from a single diagnostic instance into gameplay.

Runs after the V9 single-owner cleanup.  The goal is to keep the proven particle/render
semantics intact while changing ownership/lifetime and adding an ordinary Doom 3 projectile
integration point driven by Raven's original fx_impact* spawnargs.
"""
from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
IMPACT = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"
HEADER = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.h"
PROJECTILE = ROOT / "neo" / "game" / "Projectile.cpp"
DOOM3 = ROOT / "neo" / "game" / "q4bse" / "Q4BSEDoom3.cpp"

for path in (IMPACT, HEADER, PROJECTILE, DOOM3):
    if not path.exists():
        raise SystemExit(f"ERROR: required gameplay-integration source missing: {path}")


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f"ERROR: gameplay promotion expected one {label}, found {hits}")
    return text.replace(old, new, 1)


def replace_between(text, start_marker, end_marker, replacement, label):
    start = text.find(start_marker)
    end = text.find(end_marker, start + len(start_marker))
    if start < 0 or end < 0 or end <= start:
        raise SystemExit(f"ERROR: could not locate {label}")
    return text[:start] + replacement + text[end:]


impact = IMPACT.read_text(encoding="utf-8-sig")
header = HEADER.read_text(encoding="utf-8-sig")
projectile = PROJECTILE.read_text(encoding="utf-8-sig")
legacy = DOOM3.read_text(encoding="utf-8-sig")

# -----------------------------------------------------------------------------
# Public API: game code asks the BSE subsystem to play an FX declaration.
# -----------------------------------------------------------------------------
api_marker = "void Q4BSE_M3_Frame(int gameTimeMS);\n"
api_block = api_marker + "\n// Gameplay API.  Parsed FX declarations are cached; each call creates an independent\n// live runtime instance which services its own Raven-authored lifetime.\nbool Q4BSE_PlayEffect(const char* fxPath, const idVec3& origin, const idVec3& normal);\nint Q4BSE_ActiveEffectCount(void);\n"
header = replace_once(header, api_marker, api_block, "Q4BSE gameplay API header anchor")

# -----------------------------------------------------------------------------
# Instance data: retain the already-proven M3 particle state, add shared-decl identity.
# -----------------------------------------------------------------------------
impact = replace_once(
    impact,
    "struct M3ImpactInstance {\n    bool active;\n    idVec3 origin;",
    "struct M3ImpactInstance {\n    bool active;\n    const q4bse::Effect* effect;\n    std::string effectPath;\n    unsigned int serial;\n    idVec3 origin;",
    "M3ImpactInstance fields")
impact = replace_once(
    impact,
    ": active(false), origin(vec3_origin), axis(mat3_identity), startTimeMS(0),",
    ": active(false), effect(NULL), serial(0), origin(vec3_origin), axis(mat3_identity), startTimeMS(0),",
    "M3ImpactInstance constructor")
impact = replace_once(
    impact,
    "static const int M3_MAX_PARTICLES = 128;",
    "static const int M3_MAX_PARTICLES = 128;\nstatic const int M3_MAX_ACTIVE_EFFECTS = 256;",
    "active-effect safety budget")

old_globals = '''static bool g_m3Initialized = false;
static bool g_m3ImpactLoaded = false;
static q4bse::Effect g_m3ImpactEffect;
static M3ImpactInstance g_m3Impact;
static std::vector<M3EnvelopeTable> g_m3EnvelopeTables;'''
new_globals = '''struct M3CachedEffect {
    std::string path;
    q4bse::Effect effect;
};

static bool g_m3Initialized = false;
static bool g_m3ImpactLoaded = false;
static M3CachedEffect* g_m3DefaultImpact = NULL;
static std::vector<M3CachedEffect*> g_m3EffectCache;
static std::vector<M3ImpactInstance*> g_m3Impacts;
static M3ImpactInstance* g_m3CurrentImpact = NULL;
static unsigned int g_m3NextSerial = 0;
static std::vector<M3EnvelopeTable> g_m3EnvelopeTables;

// The renderer/evaluator functions below were proven with one M3 instance.  Keep those
// semantics unchanged and select the instance being serviced before entering them.
#define g_m3Impact (*g_m3CurrentImpact)'''
impact = replace_once(impact, old_globals, new_globals, "M3 globals")

# Cache parsed Raven declarations instead of reparsing for every projectile hit.
cache_code = '''static M3CachedEffect* GetOrLoadEffect(const char* path) {
    if (!path || !path[0]) return NULL;
    for (size_t i = 0; i < g_m3EffectCache.size(); ++i) {
        if (!idStr::Icmp(g_m3EffectCache[i]->path.c_str(), path)) return g_m3EffectCache[i];
    }
    M3CachedEffect* cached = new M3CachedEffect();
    cached->path = path;
    if (!LoadEffect(path, cached->effect)) {
        delete cached;
        return NULL;
    }
    g_m3EffectCache.push_back(cached);
    return cached;
}

static void ClearEffectCache(void) {
    for (size_t i = 0; i < g_m3EffectCache.size(); ++i) delete g_m3EffectCache[i];
    g_m3EffectCache.clear();
    g_m3DefaultImpact = NULL;
}

'''
impact = replace_once(impact, "static void ClearEnvelopeTables(void) { g_m3EnvelopeTables.clear(); }", cache_code + "static void ClearEnvelopeTables(void) { g_m3EnvelopeTables.clear(); }", "effect-cache insertion")

impact = impact.replace("g_m3ImpactEffect.segments", "g_m3Impact.effect->segments")
impact = impact.replace("g_m3ImpactEffect.name.c_str()", "g_m3Impact.effect ? g_m3Impact.effect->name.c_str() : g_m3Impact.effectPath.c_str()")

sound_block = '''static void PlaySoundSegment(const q4bse::Segment& segment) {
    (void)segment;
}

'''
impact = replace_between(impact, "static void PlaySoundSegment(const q4bse::Segment& segment) {", "static void ProjectDecalSegment(const q4bse::Segment& segment) {", sound_block, "PlaySoundSegment")
impact = impact.replace('    common->Printf("Q4BSE M3 TRACE: decal ProjectDecalOntoWorld BEGIN\\n");\n', '')
impact = impact.replace('    common->Printf("Q4BSE M3 TRACE: decal ProjectDecalOntoWorld END\\n");\n', '')

start_all = '''static void StartAllSegments(void) {
    if (!g_m3CurrentImpact || !g_m3Impact.effect) return;
    g_m3Impact.emitters.clear();
    g_m3Impact.emitters.resize(g_m3Impact.effect->segments.size());
    for (int i = 0; i < (int)g_m3Impact.effect->segments.size(); ++i) {
        const q4bse::Segment& segment = g_m3Impact.effect->segments[i];
        if (segment.type == "sound") { PlaySoundSegment(segment); continue; }
        if (segment.type == "decal") { ProjectDecalSegment(segment); continue; }
        if (segment.type == "spawner") {
            const int count = SampleSpawnerCount(segment);
            for (int p = 0; p < count; ++p) SpawnParticleForSegment(i, 0.0f);
            continue;
        }
        if (segment.type == "emitter") {
            M3EmitterState& emitter = g_m3Impact.emitters[i];
            const float rate = SampleRange(segment.count, 0.0f, g_m3Impact.random);
            emitter.active = rate > M3_EPSILON;
            emitter.endSec = SampleRange(segment.duration, 0.0f, g_m3Impact.random);
            emitter.nextSpawnSec = 0.0f;
            emitter.intervalSec = rate > M3_EPSILON ? 1.0f / rate : 1.0f;
            if (emitter.intervalSec < 0.002f) emitter.intervalSec = 0.002f;
        }
    }
}

'''
impact = replace_between(impact, "static void StartAllSegments(void) {", "static void ServiceEmitters(float elapsedSec) {", start_all, "StartAllSegments")
impact = impact.replace('g_m3Impact.model->InitEmpty("_q4bse_m3_impact");', 'g_m3Impact.model->InitEmpty(va("_q4bse_fx_%u", g_m3Impact.serial));')

free_all = '''
static void FreeAllImpacts(void) {
    for (size_t i = 0; i < g_m3Impacts.size(); ++i) {
        g_m3CurrentImpact = g_m3Impacts[i];
        FreeImpact();
        delete g_m3Impacts[i];
    }
    g_m3Impacts.clear();
    g_m3CurrentImpact = NULL;
}

'''
impact = replace_once(impact, "static bool RebuildImpactModel(float elapsedSec) {", free_all + "static bool RebuildImpactModel(float elapsedSec) {", "FreeAllImpacts insertion")

start_effect = '''static bool StartEffectAt(const q4bse::Effect* effect, const char* effectPath,
                          const idVec3& origin, const idVec3& normal) {
    if (!effect || !gameRenderWorld || !renderModelManager) return false;
    if ((int)g_m3Impacts.size() >= M3_MAX_ACTIVE_EFFECTS) {
        g_m3CurrentImpact = g_m3Impacts.front();
        FreeImpact();
        delete g_m3Impacts.front();
        g_m3Impacts.erase(g_m3Impacts.begin());
        g_m3CurrentImpact = NULL;
    }
    M3ImpactInstance* instance = new M3ImpactInstance();
    g_m3CurrentImpact = instance;
    g_m3Impact.active = true;
    g_m3Impact.effect = effect;
    g_m3Impact.effectPath = effectPath ? effectPath : "<unnamed>";
    g_m3Impact.serial = ++g_m3NextSerial;
    g_m3Impact.origin = origin;
    idVec3 n = normal;
    if (n.LengthSqr() <= M3_EPSILON) n.Set(1,0,0);
    n.NormalizeFast();
    g_m3Impact.axis = n.ToMat3();
    g_m3Impact.startTimeMS = gameLocal.time;
    g_m3Impact.random = M3Random(((unsigned int)gameLocal.time * 1664525u) ^ g_m3Impact.serial ^ 0x51ed270bu);
    g_m3Impact.model = renderModelManager->AllocModel();
    if (!g_m3Impact.model) { delete instance; g_m3CurrentImpact = NULL; return false; }
    StartAllSegments();
    ServiceEmitters(0.0f);
    memset(&g_m3Impact.renderEntity, 0, sizeof(g_m3Impact.renderEntity));
    g_m3Impact.renderEntity.hModel = g_m3Impact.model;
    g_m3Impact.renderEntity.origin = vec3_origin;
    g_m3Impact.renderEntity.axis = mat3_identity;
    g_m3Impact.renderEntity.noShadow = true;
    g_m3Impact.renderEntity.noSelfShadow = true;
    g_m3Impact.renderEntity.forceUpdate = 1;
    g_m3Impact.renderEntity.shaderParms[SHADERPARM_RED] = 1.0f;
    g_m3Impact.renderEntity.shaderParms[SHADERPARM_GREEN] = 1.0f;
    g_m3Impact.renderEntity.shaderParms[SHADERPARM_BLUE] = 1.0f;
    g_m3Impact.renderEntity.shaderParms[SHADERPARM_ALPHA] = 1.0f;
    RebuildImpactModel(0.0f);
    g_m3Impact.entityHandle = gameRenderWorld->AddEntityDef(&g_m3Impact.renderEntity);
    if (g_m3Impact.entityHandle < 0) { FreeImpact(); delete instance; g_m3CurrentImpact = NULL; return false; }
    g_m3Impacts.push_back(instance);
    g_m3CurrentImpact = NULL;
    return true;
}

'''
impact = replace_between(impact, "static bool StartImpactAt(", "static bool AnyEmitterActive(void) {", start_effect, "single-instance StartImpactAt")

cmd_block = '''static void Cmd_M3Impact(const idCmdArgs& args) {
    if (!g_m3DefaultImpact) { common->Warning("Q4BSE: default HyperBlaster impact is not loaded"); return; }
    if (!gameRenderWorld) { common->Warning("Q4BSE: load a map first"); return; }
    idPlayer* player = gameLocal.GetLocalPlayer();
    if (!player) { common->Warning("Q4BSE: no local player"); return; }
    const idVec3 start = player->firstPersonViewOrigin;
    const idVec3 end = start + player->firstPersonViewAxis[0] * 4096.0f;
    modelTrace_t trace;
    memset(&trace, 0, sizeof(trace));
    if (!gameRenderWorld->Trace(trace, start, end, 0.0f, true, true)) return;
    Q4BSE_PlayEffect(g_m3DefaultImpact->path.c_str(), trace.point + trace.normal * 0.15f, trace.normal);
}

'''
impact = replace_between(impact, "static void Cmd_M3Impact(const idCmdArgs& args) {", "static void Cmd_M3Status(const idCmdArgs& args) {", cmd_block, "diagnostic command")

status_block = '''static void Cmd_M3Status(const idCmdArgs& args) {
    int particleCount = 0;
    for (size_t i = 0; i < g_m3Impacts.size(); ++i) particleCount += (int)g_m3Impacts[i]->particles.size();
    common->Printf("Q4BSE gameplay runtime status:\\n");
    common->Printf("  cached Raven FX declarations: %d\\n", (int)g_m3EffectCache.size());
    common->Printf("  concurrent live FX instances: %d / %d\\n", (int)g_m3Impacts.size(), M3_MAX_ACTIVE_EFFECTS);
    common->Printf("  live runtime particles: %d\\n", particleCount);
    common->Printf("  projectile fx_impact integration: enabled\\n");
    common->Printf("  impact audio owner: Doom 3 projectile/DEF sound path\\n");
}

'''
impact = replace_between(impact, "static void Cmd_M3Status(const idCmdArgs& args) {", "} // anonymous namespace", status_block, "gameplay status command")

public_api = '''} // anonymous namespace

bool Q4BSE_PlayEffect(const char* fxPath, const idVec3& origin, const idVec3& normal) {
    if (!g_m3Initialized || !gameRenderWorld || !fxPath || !fxPath[0]) return false;
    M3CachedEffect* cached = GetOrLoadEffect(fxPath);
    if (!cached) return false;
    return StartEffectAt(&cached->effect, cached->path.c_str(), origin, normal);
}

int Q4BSE_ActiveEffectCount(void) {
    return (int)g_m3Impacts.size();
}

'''
impact = replace_once(impact, "} // anonymous namespace\n\nvoid Q4BSE_M3_Init(void)", public_api + "void Q4BSE_M3_Init(void)", "public gameplay API insertion")

# map/init lifecycle conversion
impact = impact.replace("g_m3ImpactLoaded = LoadEffect(M3_IMPACT_FX, g_m3ImpactEffect);", "g_m3DefaultImpact = GetOrLoadEffect(M3_IMPACT_FX);\n    g_m3ImpactLoaded = (g_m3DefaultImpact != NULL);")
impact = impact.replace("FreeImpact();\n    ClearEnvelopeTables();", "FreeAllImpacts();\n    ClearEffectCache();\n    ClearEnvelopeTables();")

# service every independent instance and retire dead ones
frame_start = impact.find("void Q4BSE_M3_Frame(int gameTimeMS) {")
if frame_start < 0:
    raise SystemExit("ERROR: Q4BSE_M3_Frame not found")
frame_end = impact.find("\n}", frame_start)
if frame_end < 0:
    raise SystemExit("ERROR: Q4BSE_M3_Frame end not found")
frame_end += 2
frame_block = '''void Q4BSE_M3_Frame(int gameTimeMS) {
    (void)gameTimeMS;
    for (size_t i = 0; i < g_m3Impacts.size();) {
        g_m3CurrentImpact = g_m3Impacts[i];
        const float elapsedSec = (gameLocal.time - g_m3Impact.startTimeMS) * 0.001f;
        ServiceEmitters(elapsedSec);
        RebuildImpactModel(elapsedSec);
        if (g_m3Impact.entityHandle >= 0) gameRenderWorld->UpdateEntityDef(g_m3Impact.entityHandle, &g_m3Impact.renderEntity);
        if (!g_m3Impact.particles.empty() || AnyEmitterActive()) {
            ++i;
            continue;
        }
        FreeImpact();
        delete g_m3Impacts[i];
        g_m3Impacts.erase(g_m3Impacts.begin() + i);
    }
    g_m3CurrentImpact = NULL;
}'''
impact = impact[:frame_start] + frame_block + impact[frame_end:]

# -----------------------------------------------------------------------------
# Projectile integration.  Keep Doom 3 damage and sound behavior; BSE owns visuals.
# -----------------------------------------------------------------------------
include_anchor = '#include "Projectile.h"\n'
if '#include "q4bse/Q4BSEImpactM3.h"' not in projectile:
    projectile = replace_once(projectile, include_anchor, include_anchor + '#include "q4bse/Q4BSEImpactM3.h"\n', "Projectile q4bse include")

helper = r'''
static const char* Q4BSE_SelectProjectileImpactFx( const idDict &projectileDef, const trace_t &collision, idEntity *hitEnt ) {
    const char* fx = NULL;
    idStr key;

    // Raven weapons often supply explicit flesh impact effects.  Preserve that preference
    // before falling back to material surface selection.
    if ( hitEnt && hitEnt->IsType( idActor::Type ) ) {
        if ( gameLocal.isMultiplayer ) {
            fx = projectileDef.GetString( "fx_impact_flesh_mp" );
            if ( *fx ) return fx;
        }
        fx = projectileDef.GetString( "fx_impact_flesh" );
        if ( *fx ) return fx;
    }

    const surfTypes_t surfaceType = collision.c.material ? collision.c.material->GetSurfaceType() : SURFTYPE_METAL;
    const char* surfaceName = gameLocal.sufaceTypeNames[surfaceType];

    if (gameLocal.isMultiplayer) {
        key = va("fx_impact_%s_mp", surfaceName);
        fx = projectileDef.GetString(key.c_str());
        if (*fx) return fx;
    }

    key = va("fx_impact_%s", surfaceName);
    fx = projectileDef.GetString(key.c_str());
    if (*fx) return fx;

    // Doom 3 calls this surface 'stone'; Raven weapon defs commonly split it into
    // rock/concrete.  Prefer the authored rock variant and then concrete.
    if ( surfaceType == SURFTYPE_STONE ) {
        fx = projectileDef.GetString( "fx_impact_rock" );
        if ( *fx ) return fx;
        fx = projectileDef.GetString( "fx_impact_concrete" );
        if ( *fx ) return fx;
    }

    fx = projectileDef.GetString( "fx_impact" );
    if ( *fx ) return fx;
    fx = projectileDef.GetString( "fx_impact_default" );
    if ( *fx ) return fx;
    return NULL;
}

'''
helper_anchor = "CLASS_DECLARATION( idEntity, idProjectile )"
if "Q4BSE_SelectProjectileImpactFx" not in projectile:
    projectile = replace_once(projectile, helper_anchor, helper + helper_anchor, "Projectile impact helper anchor")

# Inject BSE visual playback immediately after the collision point/normal are finalized and
# before Doom 3's existing impact/remove logic continues.
collide_marker = "bool idProjectile::Collide( const trace_t &collision, const idVec3 &velocity ) {"
ci = projectile.find(collide_marker)
if ci < 0:
    raise SystemExit("ERROR: idProjectile::Collide not found")
insert_anchor = "\tconst idMaterial *material = collision.c.material;"
ai = projectile.find(insert_anchor, ci)
if ai < 0:
    raise SystemExit("ERROR: projectile material anchor not found")
line_end = projectile.find("\n", ai)
playback = r'''
	const char* q4bseImpactFx = Q4BSE_SelectProjectileImpactFx( projectileDef, collision, gameLocal.entities[collision.c.entityNum] );
	if ( q4bseImpactFx && *q4bseImpactFx ) {
		Q4BSE_PlayEffect( q4bseImpactFx, collision.endpos + collision.c.normal * 0.15f, collision.c.normal );
	}
'''
projectile = projectile[:line_end+1] + playback + projectile[line_end+1:]

IMPACT.write_text(impact, encoding="utf-8")
HEADER.write_text(header, encoding="utf-8")
PROJECTILE.write_text(projectile, encoding="utf-8")

print("Q4BSE V10 GAMEPLAY promotion PASS.")
print("  - parsed Raven FX declarations are cached and shared")
print("  - every PlayEffect call creates an independent live effect instance")
print("  - simultaneous-effect safety budget: 256")
print("  - Doom 3 idProjectile::Collide consumes Raven fx_impact* spawnargs")
print("  - flesh/monster/surface/default selection enabled")
print("  - BSE owns visual FX; Doom 3 retains gameplay damage and sound ownership")
