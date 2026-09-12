#!/usr/bin/env python3
"""V18: extend the source-integrated Raven BSE bridge for the Quake 4 grenade launcher.

Runs after V17.

Adds only generic BSE semantics required by the retail grenade launcher FX plus
Quake 4's fuse-detonation playback path:
  * segment start delays (muzzle smoke / delayed explosion particles)
  * parser support for linearSpacing, generatedLine, persist, shake metadata
  * exact delayed emitter/spawner scheduling using Raven's authored count rates
  * decal rotation passed through Doom 3's native world projection helper
  * fuse explosion selection matching Q4 PlayDetonateEffect:
      ground -> fx_impact_<material> / fx_impact
      midair -> fx_detonate

The already-validated HyperBlaster rendering and attachment behavior is left
untouched. BSE sound segments remain Doom 3-owned/disabled as before.
"""

from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PARSER_H = ROOT / "neo" / "game" / "q4bse" / "Q4FxParser.h"
PARSER_CPP = ROOT / "neo" / "game" / "q4bse" / "Q4FxParser.cpp"
IMPACT = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"
PROJECTILE = ROOT / "neo" / "game" / "Projectile.cpp"

for p in (PARSER_H, PARSER_CPP, IMPACT, PROJECTILE):
    if not p.exists():
        raise SystemExit(f"ERROR: V18 prerequisite missing: {p}")


def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f"ERROR: V18 expected exactly one {label}, found {hits}")
    return text.replace(old, new, 1)


def replace_regex_once(text, pattern, repl, label, flags=0):
    hits = list(re.finditer(pattern, text, flags))
    if len(hits) != 1:
        raise SystemExit(f"ERROR: V18 expected exactly one regex {label}, found {len(hits)}")
    return re.sub(pattern, repl, text, count=1, flags=flags)


ph = PARSER_H.read_text(encoding="utf-8-sig")
pc = PARSER_CPP.read_text(encoding="utf-8-sig")
impact = IMPACT.read_text(encoding="utf-8-sig")
projectile = PROJECTILE.read_text(encoding="utf-8-sig")

# -----------------------------------------------------------------------------
# Parser data: retain the Raven flags/timing instead of rejecting the whole FX.
# -----------------------------------------------------------------------------
ph = replace_once(
    ph,
    '''    bool surface;\n    bool relative;\n    bool useEndOrigin;''',
    '''    bool surface;\n    bool relative;\n    bool useEndOrigin;\n    bool linearSpacing;''',
    "Domain linearSpacing field")
ph = replace_once(
    ph,
    '''    Domain() : surface(false), relative(false), useEndOrigin(false), hasEnvelopeOffset(false), envelopeOffset(0.0f) {}''',
    '''    Domain() : surface(false), relative(false), useEndOrigin(false), linearSpacing(false), hasEnvelopeOffset(false), envelopeOffset(0.0f) {}''',
    "Domain constructor")
ph = replace_once(
    ph,
    '''    bool generatedNormal;\n    bool generatedOriginNormal;\n    bool flipNormal;''',
    '''    bool generatedNormal;\n    bool generatedOriginNormal;\n    bool generatedLine;\n    bool persist;\n    bool flipNormal;''',
    "particle Raven flags")
ph = replace_once(
    ph,
    '''    ParticleTemplate() : generatedNormal(false), generatedOriginNormal(false), flipNormal(false) {}''',
    '''    ParticleTemplate() : generatedNormal(false), generatedOriginNormal(false), generatedLine(false), persist(false), flipNormal(false) {}''',
    "ParticleTemplate constructor")
ph = replace_once(
    ph,
    '''    Range count;\n    Range duration;\n    float detail;\n    bool locked;\n    bool constant;''',
    '''    Range count;\n    Range start;\n    Range duration;\n    Range attenuation;\n    float detail;\n    bool locked;\n    bool constant;\n    bool attenuateEmitter;''',
    "segment timing fields")
ph = replace_once(
    ph,
    '''    Segment() : detail(1.0f), locked(false), constant(false), hasParticle(false) {}''',
    '''    Segment() : detail(1.0f), locked(false), constant(false), attenuateEmitter(false), hasParticle(false) {}''',
    "Segment constructor")

pc = replace_once(
    pc,
    '''        if (ts.peek() == "relative") { ts.get(); d.relative = true; continue; }\n        // Raven spawn domains may opt into the effect's end-origin coordinate.''',
    '''        if (ts.peek() == "relative") { ts.get(); d.relative = true; continue; }\n        if (ts.peek() == "linearSpacing") { ts.get(); d.linearSpacing = true; continue; }\n        // Raven spawn domains may opt into the effect's end-origin coordinate.''',
    "linearSpacing domain modifier")
pc = replace_once(
    pc,
    '''        else if (k == "generatedOriginNormal") p.generatedOriginNormal = true;\n        else if (k == "flipNormal") p.flipNormal = true;''',
    '''        else if (k == "generatedOriginNormal") p.generatedOriginNormal = true;\n        else if (k == "generatedLine") p.generatedLine = true;\n        else if (k == "persist") p.persist = true;\n        else if (k == "flipNormal") p.flipNormal = true;''',
    "generatedLine/persist particle flags")
pc = replace_once(
    pc,
    '''        if (k == "count") s.count = ParseRange(ts);\n        else if (k == "duration") s.duration = ParseRange(ts);\n        else if (k == "detail") s.detail = ToFloat(ts.get());\n        else if (k == "locked") s.locked = true;\n        else if (k == "constant") s.constant = true;''',
    '''        if (k == "count") s.count = ParseRange(ts);\n        else if (k == "start") s.start = ParseRange(ts);\n        else if (k == "duration") s.duration = ParseRange(ts);\n        else if (k == "attenuation") s.attenuation = ParseRange(ts);\n        else if (k == "detail") s.detail = ToFloat(ts.get());\n        else if (k == "locked") s.locked = true;\n        else if (k == "constant") s.constant = true;\n        else if (k == "attenuateEmitter") s.attenuateEmitter = true;''',
    "segment start/attenuation parsing")
pc = replace_once(
    pc,
    '''        else if (k == "spawner" || k == "emitter" || k == "sound" || k == "decal" ||\n                 k == "effect" || k == "trail" || k == "light" || k == "delay") {''',
    '''        else if (k == "spawner" || k == "emitter" || k == "sound" || k == "decal" ||\n                 k == "effect" || k == "trail" || k == "light" || k == "delay" || k == "shake") {''',
    "shake effect segment parsing")
pc = replace_once(
    pc,
    '''    if (d.useEndOrigin) os << " useEndOrigin";''',
    '''    if (d.useEndOrigin) os << " useEndOrigin";\n    if (d.linearSpacing) os << " linearSpacing";''',
    "DumpEffect linearSpacing")
pc = replace_once(
    pc,
    '''        if (s.count.valid) os << " count=" << RangeStr(s.count);\n        if (s.duration.valid) os << " duration=" << RangeStr(s.duration);''',
    '''        if (s.count.valid) os << " count=" << RangeStr(s.count);\n        if (s.start.valid) os << " start=" << RangeStr(s.start);\n        if (s.duration.valid) os << " duration=" << RangeStr(s.duration);''',
    "DumpEffect segment start")

# -----------------------------------------------------------------------------
# Runtime scheduling. Raven emitter count is particles/second; the proven M3
# runtime already uses that rule. We only add each segment's authored start time.
# -----------------------------------------------------------------------------
start_pattern = r'''static void StartAllSegments\(void\) \{.*?\n\}\n\nstatic void ServiceEmitters\(float elapsedSec\) \{'''
start_repl = r'''static void StartAllSegments(void) {
    if (!g_m3CurrentImpact || !g_m3Impact.effect) return;
    g_m3Impact.emitters.clear();
    g_m3Impact.emitters.resize(g_m3Impact.effect->segments.size());
    for (int i = 0; i < (int)g_m3Impact.effect->segments.size(); ++i) {
        const q4bse::Segment& segment = g_m3Impact.effect->segments[i];
        if (segment.type == "sound") { PlaySoundSegment(segment); continue; }
        if (segment.type == "shake") { continue; } // camera shake stays game-owned
        if (segment.type == "decal") { ProjectDecalSegment(segment); continue; }
        if (segment.type == "spawner") {
            const int count = SampleSpawnerCount(segment);
            const float birthSec = SampleRange(segment.start, 0.0f, g_m3Impact.random);
            for (int p = 0; p < count; ++p) SpawnParticleForSegment(i, birthSec);
            continue;
        }
        if (segment.type == "emitter") {
            M3EmitterState& emitter = g_m3Impact.emitters[i];
            const float rate = SampleRange(segment.count, 0.0f, g_m3Impact.random);
            const float startSec = SampleRange(segment.start, 0.0f, g_m3Impact.random);
            const float durationSec = SampleRange(segment.duration, 0.0f, g_m3Impact.random);
            emitter.active = rate > M3_EPSILON && durationSec > 0.0f;
            emitter.endSec = startSec + durationSec;
            emitter.nextSpawnSec = startSec;
            emitter.intervalSec = rate > M3_EPSILON ? 1.0f / rate : 1.0f;
            if (emitter.intervalSec < 0.002f) emitter.intervalSec = 0.002f;
        }
    }
}

static void ServiceEmitters(float elapsedSec) {'''
impact = replace_regex_once(impact, start_pattern, start_repl, "delayed BSE segment scheduling", re.S)

# -----------------------------------------------------------------------------
# Decals: keep V17's HyperBlaster layer bridge, but pass Raven's random rotate
# domain into Doom 3's native ProjectDecal(angleDegrees) path for grenade burns.
# -----------------------------------------------------------------------------
decal_pattern = r'''static void ProjectDecalSegment\(const q4bse::Segment& segment\) \{.*?\n\}\n\nstatic int SampleSpawnerCount'''
decal_repl = r'''static void ProjectDecalSegment(const q4bse::Segment& segment) {
    if (!gameRenderWorld || !declManager || !segment.hasParticle) return;
    const q4bse::ParticleTemplate& pt = segment.particle;
    if (pt.material.empty()) return;

    idVec2 size(16.0f, 16.0f);
    SampleVec2Domain(FindDomain(pt.start, "size"), size, g_m3Impact.random);
    float decalSize = idMath::Fabs(size.x);
    if (idMath::Fabs(size.y) > decalSize) decalSize = idMath::Fabs(size.y);
    if (decalSize < 1.0f) decalSize = 1.0f;

    float decalRotate = 0.0f;
    SampleFloatDomain(FindDomain(pt.start, "rotate"), decalRotate, g_m3Impact.random);
    const float decalAngleDegrees = decalRotate * 360.0f;

    idVec3 normal = g_m3Impact.axis[0];
    if (normal.LengthSqr() <= M3_EPSILON) normal.Set(1.0f, 0.0f, 0.0f);
    normal.NormalizeFast();

    // V17 Q4-only HyperBlaster DecalLife translation remains intact.
    if (!idStr::Icmp(pt.material.c_str(), "gfx/effects/decals/blaster_wall_mark3")) {
        static const char* q4WallMarkLayers[] = {
            "gfx/effects/decals/q4hb_blaster_wall_hot1",
            "gfx/effects/decals/q4hb_blaster_wall_hot2",
            "gfx/effects/decals/q4hb_blaster_wall_scorch"
        };
        for (int i = 0; i < 3; ++i) {
            const idMaterial* layerMaterial = declManager->FindMaterial(q4WallMarkLayers[i], false);
            if (!layerMaterial) {
                common->Warning("Q4BSE: translated decal material not found: %s", q4WallMarkLayers[i]);
                continue;
            }
            gameLocal.ProjectDecal(g_m3Impact.origin, -normal, 8.0f, true,
                                   decalSize, q4WallMarkLayers[i], decalAngleDegrees);
        }
        return;
    }

    const idMaterial* material = declManager->FindMaterial(pt.material.c_str(), false);
    if (!material) {
        common->Warning("Q4BSE: decal material not found: %s", pt.material.c_str());
        return;
    }
    gameLocal.ProjectDecal(g_m3Impact.origin, -normal, 8.0f, true,
                           decalSize, pt.material.c_str(), decalAngleDegrees);
}

static int SampleSpawnerCount'''
impact = replace_regex_once(impact, decal_pattern, decal_repl, "rotated native BSE decal projection", re.S)

# -----------------------------------------------------------------------------
# Quake 4 fuse detonation semantics. Normal projectile collisions already reach
# the generic V13 fx_impact hook only after Doom 3 has decided the hit detonates,
# so grenade bounces remain untouched. Fuse events need Q4's ground-vs-midair
# selection explicitly because stock Doom 3 has no PlayDetonateEffect method.
# -----------------------------------------------------------------------------
event_pattern = r'''void idProjectile::Event_Explode\( void \) \{\n\ttrace_t collision;\n\n\tmemset\( &collision, 0, sizeof\( collision \) \);\n\tcollision\.endAxis = GetPhysics\(\)->GetAxis\(\);\n\tcollision\.endpos = GetPhysics\(\)->GetOrigin\(\);\n\tcollision\.c\.point = GetPhysics\(\)->GetOrigin\(\);\n\tcollision\.c\.normal\.Set\( 0, 0, 1 \);\n\tAddDefaultDamageEffect\( collision, collision\.c\.normal \);\n\tExplode\( collision, NULL \);\n\}'''
event_repl = r'''void idProjectile::Event_Explode( void ) {
    trace_t collision;

    memset( &collision, 0, sizeof( collision ) );
    collision.endAxis = GetPhysics()->GetAxis();
    collision.endpos = GetPhysics()->GetOrigin();
    collision.c.point = GetPhysics()->GetOrigin();
    collision.c.normal.Set( 0, 0, 1 );

    bool q4bsePlayedDetonation = false;
    const char *q4bseDetonateFx = spawnArgs.GetString( "fx_detonate" );
    if ( q4bseDetonateFx && q4bseDetonateFx[0] ) {
        idVec3 q4FxDir = -GetPhysics()->GetGravity();
        if ( q4FxDir.LengthSqr() <= 0.000001f ) {
            q4FxDir = -GetPhysics()->GetLinearVelocity();
        }
        if ( q4FxDir.LengthSqr() <= 0.000001f ) {
            q4FxDir.Set( 0, 0, 1 );
        } else {
            q4FxDir.NormalizeFast();
        }

        const char *q4bseFxPath = q4bseDetonateFx;
        if ( spawnArgs.GetBool( "detonateTestGroundMaterial" ) ) {
            idVec3 gravityDir = GetPhysics()->GetGravity();
            if ( gravityDir.LengthSqr() > 0.000001f ) {
                gravityDir.NormalizeFast();
                trace_t groundTrace;
                memset( &groundTrace, 0, sizeof( groundTrace ) );
                const idVec3 start = GetPhysics()->GetOrigin();
                const idVec3 end = start + gravityDir * 8.0f;
                gameLocal.clip.Translation( groundTrace, start, end,
                    GetPhysics()->GetClipModel(), GetPhysics()->GetAxis(),
                    GetPhysics()->GetClipMask(), this );
                if ( groundTrace.fraction < 1.0f && groundTrace.c.material ) {
                    idEntity *groundEnt = NULL;
                    if ( groundTrace.c.entityNum >= 0 && groundTrace.c.entityNum < MAX_GENTITIES ) {
                        groundEnt = gameLocal.entities[ groundTrace.c.entityNum ];
                    }
                    const char *groundFx = Q4BSE_SelectProjectileImpactFx( spawnArgs, groundTrace, groundEnt );
                    if ( groundFx && groundFx[0] ) {
                        q4bseFxPath = groundFx;
                    }
                }
            }
        }

        q4bsePlayedDetonation = Q4BSE_PlayEffectAxis(
            q4bseFxPath, GetPhysics()->GetOrigin(), q4FxDir.ToMat3() );
    }

    // Preserve stock Doom 3 fallback only for projectiles that do not own a
    // Raven fuse detonation or if the Raven declaration failed to load.
    if ( !q4bsePlayedDetonation ) {
        AddDefaultDamageEffect( collision, collision.c.normal );
    }
    Explode( collision, NULL );
}'''
projectile = replace_regex_once(projectile, event_pattern, event_repl, "Q4 fuse detonation Event_Explode", re.S)

# Verification gates.
for required in (
    "linearSpacing",
    "generatedLine",
    'k == "shake"',
    'k == "start"',
):
    if required not in ph + pc:
        raise SystemExit(f"ERROR: V18 parser verification missing: {required}")

for required in (
    "const float birthSec = SampleRange(segment.start, 0.0f",
    "emitter.nextSpawnSec = startSec",
    "decalAngleDegrees",
):
    if required not in impact:
        raise SystemExit(f"ERROR: V18 runtime verification missing: {required}")

for required in (
    'spawnArgs.GetString( "fx_detonate" )',
    'detonateTestGroundMaterial',
    'Q4BSE_SelectProjectileImpactFx',
    'Q4BSE_PlayEffectAxis',
):
    if required not in projectile:
        raise SystemExit(f"ERROR: V18 projectile verification missing: {required}")

PARSER_H.write_text(ph, encoding="utf-8")
PARSER_CPP.write_text(pc, encoding="utf-8")
IMPACT.write_text(impact, encoding="utf-8")
PROJECTILE.write_text(projectile, encoding="utf-8")

print("Q4BSE V18 GRENADE LAUNCHER BSE PASS.")
print("  - Raven segment start delays accepted and serviced")
print("  - linearSpacing / generatedLine / shake syntax no longer rejects GL FX")
print("  - grenade decals preserve authored random rotation")
print("  - fuse detonation mirrors Q4: ground material impact FX, otherwise detonate FX")
print("  - ordinary grenade bounces remain non-detonating and do not spawn BSE impacts")
