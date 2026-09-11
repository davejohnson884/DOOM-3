#!/usr/bin/env python3
"""Overlay the source-integrated M3 HyperBlaster impact runtime after M1 integration."""
from pathlib import Path
import base64
import sys
import zlib

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
HERE = Path(__file__).resolve().parent
ENCODED = HERE / "source_m3" / "Q4BSEDoom3.cpp.zlib.b64"
DEST = ROOT / "neo" / "game" / "q4bse" / "Q4BSEDoom3.cpp"
IMPACT = ROOT / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"

if not ENCODED.exists():
    raise SystemExit(f"ERROR: missing M3 source payload: {ENCODED}")
if not DEST.exists():
    raise SystemExit(f"ERROR: M1 integration must run first; missing {DEST}")
if not IMPACT.exists():
    raise SystemExit(f"ERROR: M1 integration must copy M3 impact source first; missing {IMPACT}")

try:
    packed = base64.b64decode(ENCODED.read_text(encoding="ascii").strip(), validate=True)
    source = zlib.decompress(packed)
except Exception as exc:
    raise SystemExit(f"ERROR: could not decode M3 source payload: {exc}")

if b'q4bse_m3_impact' not in source or b'Q4BSE M3' not in source:
    raise SystemExit("ERROR: decoded M3 source failed sanity check")

# Stamp the exact retail diagnostic build into q4bse_status.
status_marker = b'common->Printf("Q4BSE source-integrated M3 status:\\n");'
status_replacement = status_marker + b'\n    common->Printf("  build fingerprint: V8 VISUAL_TRACE\\n");'
if source.count(status_marker) != 1:
    raise SystemExit(f"ERROR: expected exactly one M3 status marker, found {source.count(status_marker)}")
source = source.replace(status_marker, status_replacement, 1)
DEST.write_bytes(source)

impact_text = IMPACT.read_text(encoding="utf-8-sig")

def replace_once(text, old, new, label):
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f"ERROR: V8 instrumentation expected one {label} marker, found {hits}")
    return text.replace(old, new, 1)

# Architecture decision: BSE owns the Raven visual FX.  Audio will be played later by
# Doom 3's normal projectile/DEF sound path (snd_<surface>, snd_metal, snd_impact).
# The Raven sound segment remains parsed for fidelity/ordering, but M3 performs no sound API calls.
sound_start_marker = "static void PlaySoundSegment(const q4bse::Segment& segment) {"
sound_end_marker = "static void ProjectDecalSegment(const q4bse::Segment& segment) {"
sound_start = impact_text.find(sound_start_marker)
sound_end = impact_text.find(sound_end_marker, sound_start + 1)
if sound_start < 0 or sound_end < 0 or sound_end <= sound_start:
    raise SystemExit("ERROR: could not locate M3 PlaySoundSegment block for V8 replacement")

new_sound = '''static void PlaySoundSegment(const q4bse::Segment& segment) {
    // V8 architecture: Q4BSE interprets visuals only.  The eventual HyperBlaster
    // projectile DEF will own impact audio through Doom 3's native sound system.
    common->Printf("Q4BSE M3 TRACE: sound segment parsed/ignored by BSE: %s\\n",
                   segment.soundShader.empty() ? "<empty>" : segment.soundShader.c_str());
}

'''
impact_text = impact_text[:sound_start] + new_sound + impact_text[sound_end:]

# Trace the exact world-decal API boundary.  The previous retail crash happened after the
# decal summary and before M3 PLAY, so we need to know whether ProjectDecalOntoWorld returns.
decal_call = "    gameRenderWorld->ProjectDecalOntoWorld(winding, projectionOrigin, true, depth, material, gameLocal.time);"
decal_trace = '''    common->Printf("Q4BSE M3 TRACE: decal ProjectDecalOntoWorld BEGIN\\n");
    gameRenderWorld->ProjectDecalOntoWorld(winding, projectionOrigin, true, depth, material, gameLocal.time);
    common->Printf("Q4BSE M3 TRACE: decal ProjectDecalOntoWorld END\\n");'''
impact_text = replace_once(impact_text, decal_call, decal_trace, "ProjectDecalOntoWorld")

# Segment-by-segment tracing.
segment_marker = "        const q4bse::Segment& segment = g_m3ImpactEffect.segments[i];"
segment_trace = segment_marker + '''
        common->Printf("Q4BSE M3 TRACE: segment %d BEGIN type=%s name=%s\\n", i,
                       segment.type.c_str(), segment.name.empty() ? "<unnamed>" : segment.name.c_str());'''
impact_text = replace_once(impact_text, segment_marker, segment_trace, "segment loop")

impact_text = replace_once(
    impact_text,
    '        if (segment.type == "sound") { PlaySoundSegment(segment); continue; }',
    '''        if (segment.type == "sound") {
            PlaySoundSegment(segment);
            common->Printf("Q4BSE M3 TRACE: segment %d END sound-skipped\\n", i);
            continue;
        }''',
    "sound segment dispatch")

impact_text = replace_once(
    impact_text,
    '        if (segment.type == "decal") { ProjectDecalSegment(segment); continue; }',
    '''        if (segment.type == "decal") {
            common->Printf("Q4BSE M3 TRACE: segment %d decal dispatch BEGIN\\n", i);
            ProjectDecalSegment(segment);
            common->Printf("Q4BSE M3 TRACE: segment %d decal dispatch END\\n", i);
            continue;
        }''',
    "decal segment dispatch")

spawner_marker = '''        if (segment.type == "spawner") {
            const int count = SampleSpawnerCount(segment);
            for (int p = 0; p < count; ++p) SpawnParticleForSegment(i, 0.0f);
            continue;
        }'''
spawner_trace = '''        if (segment.type == "spawner") {
            const int count = SampleSpawnerCount(segment);
            common->Printf("Q4BSE M3 TRACE: segment %d spawner count=%d BEGIN\\n", i, count);
            for (int p = 0; p < count; ++p) {
                if (!SpawnParticleForSegment(i, 0.0f)) {
                    common->Warning("Q4BSE M3 TRACE: segment %d particle %d spawn failed", i, p);
                }
            }
            common->Printf("Q4BSE M3 TRACE: segment %d spawner END totalParticles=%d\\n", i, (int)g_m3Impact.particles.size());
            continue;
        }'''
impact_text = replace_once(impact_text, spawner_marker, spawner_trace, "spawner block")

emitter_marker = '''        if (segment.type == "emitter") {
            M3EmitterState& emitter = g_m3Impact.emitters[i];
            const float rate = SampleRange(segment.count, 0.0f, g_m3Impact.random);
            emitter.active = rate > M3_EPSILON;
            emitter.endSec = SampleRange(segment.duration, 0.0f, g_m3Impact.random);
            emitter.nextSpawnSec = 0.0f;
            emitter.intervalSec = rate > M3_EPSILON ? 1.0f / rate : 1.0f;
            if (emitter.intervalSec < 0.002f) emitter.intervalSec = 0.002f;
        }'''
emitter_trace = '''        if (segment.type == "emitter") {
            M3EmitterState& emitter = g_m3Impact.emitters[i];
            const float rate = SampleRange(segment.count, 0.0f, g_m3Impact.random);
            emitter.active = rate > M3_EPSILON;
            emitter.endSec = SampleRange(segment.duration, 0.0f, g_m3Impact.random);
            emitter.nextSpawnSec = 0.0f;
            emitter.intervalSec = rate > M3_EPSILON ? 1.0f / rate : 1.0f;
            if (emitter.intervalSec < 0.002f) emitter.intervalSec = 0.002f;
            common->Printf("Q4BSE M3 TRACE: segment %d emitter configured rate=%.3f end=%.3f interval=%.4f active=%d\\n",
                           i, rate, emitter.endSec, emitter.intervalSec, emitter.active ? 1 : 0);
            continue;
        }
        common->Printf("Q4BSE M3 TRACE: segment %d END unhandled type=%s\\n", i, segment.type.c_str());'''
impact_text = replace_once(impact_text, emitter_marker, emitter_trace, "emitter block")

# StartImpactAt checkpoint tracing.  These markers bracket every remaining engine-facing
# operation before the final M3 PLAY line.
start_marker = '''static bool StartImpactAt(const idVec3& origin, const idVec3& normal) {
    if (!g_m3ImpactLoaded || !gameRenderWorld || !renderModelManager) return false;
    FreeImpact();'''
start_trace = '''static bool StartImpactAt(const idVec3& origin, const idVec3& normal) {
    if (!g_m3ImpactLoaded || !gameRenderWorld || !renderModelManager) return false;
    common->Printf("Q4BSE M3 TRACE: StartImpactAt BEGIN\\n");
    common->Printf("Q4BSE M3 TRACE: FreeImpact BEGIN\\n");
    FreeImpact();
    common->Printf("Q4BSE M3 TRACE: FreeImpact END\\n");'''
impact_text = replace_once(impact_text, start_marker, start_trace, "StartImpactAt entry")

impact_text = replace_once(
    impact_text,
    '''    g_m3Impact.model = renderModelManager->AllocModel();
    if (!g_m3Impact.model) { g_m3Impact.active = false; return false; }
    StartAllSegments();
    ServiceEmitters(0.0f);''',
    '''    common->Printf("Q4BSE M3 TRACE: AllocModel BEGIN\\n");
    g_m3Impact.model = renderModelManager->AllocModel();
    if (!g_m3Impact.model) { g_m3Impact.active = false; return false; }
    common->Printf("Q4BSE M3 TRACE: AllocModel END\\n");
    common->Printf("Q4BSE M3 TRACE: StartAllSegments BEGIN\\n");
    StartAllSegments();
    common->Printf("Q4BSE M3 TRACE: StartAllSegments END particles=%d\\n", (int)g_m3Impact.particles.size());
    common->Printf("Q4BSE M3 TRACE: ServiceEmitters(0) BEGIN\\n");
    ServiceEmitters(0.0f);
    common->Printf("Q4BSE M3 TRACE: ServiceEmitters(0) END particles=%d\\n", (int)g_m3Impact.particles.size());''',
    "AllocModel/start segments")

impact_text = replace_once(
    impact_text,
    '''    RebuildImpactModel(0.0f);
    g_m3Impact.entityHandle = gameRenderWorld->AddEntityDef(&g_m3Impact.renderEntity);''',
    '''    common->Printf("Q4BSE M3 TRACE: RebuildImpactModel(0) BEGIN\\n");
    RebuildImpactModel(0.0f);
    common->Printf("Q4BSE M3 TRACE: RebuildImpactModel(0) END surfaces=%d\\n", g_m3Impact.model ? g_m3Impact.model->NumSurfaces() : -1);
    common->Printf("Q4BSE M3 TRACE: AddEntityDef BEGIN\\n");
    g_m3Impact.entityHandle = gameRenderWorld->AddEntityDef(&g_m3Impact.renderEntity);
    common->Printf("Q4BSE M3 TRACE: AddEntityDef END handle=%d\\n", g_m3Impact.entityHandle);''',
    "Rebuild/AddEntityDef")

# Make the ready banner reflect the architecture we are actually validating.
old_ready = 'if (g_m3ImpactLoaded) common->Printf("Q4BSE M3 READY: q4bse_m3_impact executes sound + decal + sprite + line + emitter + oriented segments\\n");'
new_ready = 'if (g_m3ImpactLoaded) common->Printf("Q4BSE M3 V8 READY: visual BSE runtime = decal + sprite + line + emitter + oriented; sound delegated to Doom 3 projectile DEF path\\n");'
impact_text = replace_once(impact_text, old_ready, new_ready, "M3 ready banner")

# Hard architecture/safety gates.  M3 must not own Doom 3 audio in this branch anymore.
for forbidden in ("->UpdateEmitter(", "AllocSoundEmitter(", "StartSoundShader(", "->StartSound("):
    if forbidden in impact_text:
        raise SystemExit(f"ERROR: forbidden BSE-owned sound call remains in Q4BSEImpactM3.cpp: {forbidden}")

# Sanity-check that the critical V8 trace markers made it into the final source.
for required in (
    "Q4BSE M3 TRACE: decal ProjectDecalOntoWorld BEGIN",
    "Q4BSE M3 TRACE: decal ProjectDecalOntoWorld END",
    "Q4BSE M3 TRACE: StartAllSegments BEGIN",
    "Q4BSE M3 TRACE: RebuildImpactModel(0) BEGIN",
    "Q4BSE M3 TRACE: AddEntityDef BEGIN",
):
    if required not in impact_text:
        raise SystemExit(f"ERROR: missing V8 trace marker: {required}")

IMPACT.write_text(impact_text, encoding="utf-8")

print(f"Q4BSE M3 overlay applied: {len(source)} bytes -> {DEST}")
print("Q4BSE M3 V8 fingerprint applied: VISUAL_TRACE.")
print("Q4BSE M3 architecture applied: Raven sound segments parsed but audio delegated to Doom 3 projectile DEF path.")
print("Q4BSE M3 V8 tracing applied around segment dispatch, decal projection, model rebuild, and AddEntityDef.")
print("Q4BSE M3 V8 sound safety gates PASS: no BSE-owned Doom 3 sound calls remain.")
print("Architecture remains one ordinary source-built gamex86.dll; no wrapper or binary hook.")
