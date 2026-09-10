#include "../../idlib/precompiled.h"
#pragma hdrstop

#include "../Game_local.h"

#ifdef snprintf
#undef snprintf
#endif
#ifdef _snprintf
#undef _snprintf
#endif
#ifdef vsnprintf
#undef vsnprintf
#endif
#ifdef _vsnprintf
#undef _vsnprintf
#endif
#ifdef min
#undef min
#endif
#ifdef max
#undef max
#endif

#include "Q4FxParser.h"
#include "Q4BSEImpactM3.h"

#include <string>
#include <vector>
#include <stdexcept>
#include <string.h>
#include <math.h>

namespace {

static const float M3_EPSILON = 0.000001f;
static const float M3_TWO_PI = 6.28318530717958647692f;
static const int M3_MAX_PARTICLES = 128;

struct M3EnvelopeTable {
    std::string name;
    bool valid;
    bool clamp;
    bool snap;
    std::vector<float> values;
    M3EnvelopeTable() : valid(false), clamp(false), snap(false) {}
};

struct M3Random {
    unsigned int state;
    M3Random() : state(0x6d2b79f5u) {}
    explicit M3Random(unsigned int seed) : state(seed ? seed : 0x6d2b79f5u) {}
    unsigned int NextU32() {
        unsigned int x = state;
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        state = x;
        return x;
    }
    float Unit() { return (float)(NextU32() & 0x00FFFFFFu) * (1.0f / 16777215.0f); }
    float Range(float lo, float hi) { return lo + (hi - lo) * Unit(); }
};

struct M3Particle {
    const q4bse::Segment* segment;
    int segmentIndex;
    float birthSec;
    float durationSec;
    idVec3 localPosition;
    idVec3 localVelocity;
    idVec3 worldGravityAcceleration;
    idVec2 sizeStart;
    idVec2 sizeEnd;
    idVec3 tintStart;
    idVec3 tintEnd;
    float fadeStart;
    float fadeEnd;
    idVec3 rotateStart;
    idVec3 rotateEnd;
    idVec3 lengthStart;
    idVec3 lengthEnd;
    M3Particle()
        : segment(NULL), segmentIndex(-1), birthSec(0.0f), durationSec(0.1f),
          localPosition(vec3_origin), localVelocity(vec3_origin), worldGravityAcceleration(vec3_origin),
          sizeStart(1.0f, 1.0f), sizeEnd(1.0f, 1.0f),
          tintStart(1.0f, 1.0f, 1.0f), tintEnd(0.0f, 0.0f, 0.0f),
          fadeStart(1.0f), fadeEnd(0.0f), rotateStart(vec3_origin), rotateEnd(vec3_origin),
          lengthStart(vec3_origin), lengthEnd(vec3_origin) {}
};

struct M3EmitterState {
    bool active;
    float endSec;
    float nextSpawnSec;
    float intervalSec;
    M3EmitterState() : active(false), endSec(0.0f), nextSpawnSec(0.0f), intervalSec(1.0f) {}
};

struct M3ImpactInstance {
    bool active;
    idVec3 origin;
    idMat3 axis;
    int startTimeMS;
    int entityHandle;
    idRenderModel* model;
    renderEntity_t renderEntity;
    std::vector<M3Particle> particles;
    std::vector<M3EmitterState> emitters;
    M3Random random;
    M3ImpactInstance()
        : active(false), origin(vec3_origin), axis(mat3_identity), startTimeMS(0),
          entityHandle(-1), model(NULL), random(0x6d2b79f5u) {
        memset(&renderEntity, 0, sizeof(renderEntity));
    }
};

static bool g_m3Initialized = false;
static bool g_m3ImpactLoaded = false;
static q4bse::Effect g_m3ImpactEffect;
static M3ImpactInstance g_m3Impact;
static std::vector<M3EnvelopeTable> g_m3EnvelopeTables;

static float Clamp01(float x) {
    if (x < 0.0f) return 0.0f;
    if (x > 1.0f) return 1.0f;
    return x;
}

static byte ToByte(float x) {
    x = Clamp01(x);
    int value = idMath::FtoiFast(x * 255.0f);
    if (value < 0) value = 0;
    if (value > 255) value = 255;
    return (byte)value;
}

static void SetVertexColor(idDrawVert& v, const idVec4& color, bool additive) {
    idVec4 c = color;
    c.w = Clamp01(c.w);
    // Raven BSE premultiplies RGB by alpha for additive stages.  This also fixes
    // the M2 vertexColor bridge where alpha was evaluated but never reached geometry.
    if (additive) {
        c.x *= c.w;
        c.y *= c.w;
        c.z *= c.w;
    }
    v.color[0] = ToByte(c.x);
    v.color[1] = ToByte(c.y);
    v.color[2] = ToByte(c.z);
    v.color[3] = ToByte(c.w);
}

static void SetDrawVert(idDrawVert& v, const idVec3& xyz, float s, float t,
                        const idVec4& color, bool additive) {
    v.Clear();
    v.xyz = xyz;
    v.st.Set(s, t);
    v.normal.Set(1.0f, 0.0f, 0.0f);
    v.tangents[0].Set(0.0f, 1.0f, 0.0f);
    v.tangents[1].Set(0.0f, 0.0f, 1.0f);
    SetVertexColor(v, color, additive);
}

static bool IsAdditive(const q4bse::ParticleTemplate& particle) { return particle.blend == "add"; }

static bool LoadEffect(const char* path, q4bse::Effect& out) {
    void* buffer = NULL;
    const int length = fileSystem->ReadFile(path, &buffer, NULL);
    if (length < 0 || buffer == NULL) {
        common->Warning("Q4BSE M3: VFS could not read %s", path);
        return false;
    }
    bool ok = false;
    try {
        q4bse::Parser parser;
        out = parser.Parse(std::string((const char*)buffer, (size_t)length), path);
        common->Printf("Q4BSE M3: parsed %s (%d bytes, %d segments)\n", path, length, (int)out.segments.size());
        ok = true;
    }
    catch (const std::exception& e) { common->Warning("Q4BSE M3: parse failure %s: %s", path, e.what()); }
    catch (...) { common->Warning("Q4BSE M3: parse failure %s: unknown exception", path); }
    fileSystem->FreeFile(buffer);
    return ok;
}

static void ClearEnvelopeTables(void) { g_m3EnvelopeTables.clear(); }

static bool ParseDeclTable(const idDecl* decl, M3EnvelopeTable& table, std::string& error) {
    if (!decl) { error = "null table declaration"; return false; }
    const int textLength = decl->GetTextLength();
    if (textLength <= 0) { error = std::string("empty table declaration: ") + decl->GetName(); return false; }
    char* text = new char[textLength + 1];
    decl->GetText(text);
    text[textLength] = '\0';
    idLexer lexer;
    lexer.LoadMemory(text, textLength, decl->GetFileName(), decl->GetLineNum());
    lexer.SetFlags(DECL_LEXER_FLAGS);
    bool ok = lexer.SkipUntilString("{");
    if (!ok) error = std::string("table has no opening brace: ") + decl->GetName();
    idToken token;
    while (ok && lexer.ReadToken(&token)) {
        if (token == "}") break;
        if (!token.Icmp("clamp")) { table.clamp = true; continue; }
        if (!token.Icmp("snap")) { table.snap = true; continue; }
        if (token == "{") {
            while (lexer.ReadToken(&token)) {
                if (token == "}") break;
                if (token == ",") continue;
                lexer.UnreadToken(&token);
                bool parseError = false;
                const float value = lexer.ParseFloat(&parseError);
                if (parseError) { error = std::string("non-numeric value in table ") + decl->GetName(); ok = false; break; }
                table.values.push_back(value);
            }
            continue;
        }
        error = std::string("unsupported token in table ") + decl->GetName() + ": " + token.c_str();
        ok = false;
    }
    delete[] text;
    if (ok && table.values.empty()) { error = std::string("table has no values: ") + decl->GetName(); ok = false; }
    return ok;
}

static M3EnvelopeTable* FindEnvelopeTable(const char* name, std::string& error) {
    if (!name || !name[0]) { error = "empty envelope table name"; return NULL; }
    for (size_t i = 0; i < g_m3EnvelopeTables.size(); ++i) {
        if (!idStr::Icmp(g_m3EnvelopeTables[i].name.c_str(), name)) {
            if (!g_m3EnvelopeTables[i].valid) { error = std::string("envelope table unavailable: ") + name; return NULL; }
            return &g_m3EnvelopeTables[i];
        }
    }
    M3EnvelopeTable cache;
    cache.name = name;
    const idDecl* decl = declManager ? declManager->FindType(DECL_TABLE, name, false) : NULL;
    if (!decl) { error = std::string("Raven envelope table not found: ") + name; g_m3EnvelopeTables.push_back(cache); return NULL; }
    if (!ParseDeclTable(decl, cache, error)) { g_m3EnvelopeTables.push_back(cache); return NULL; }
    cache.valid = true;
    g_m3EnvelopeTables.push_back(cache);
    return &g_m3EnvelopeTables.back();
}

static float TableLookup(const M3EnvelopeTable& table, float index) {
    const int domain = (int)table.values.size();
    if (domain <= 1) return domain == 1 ? table.values[0] : 1.0f;
    int base = 0;
    float frac = 0.0f;
    if (table.clamp) {
        index *= (float)(domain - 1);
        if (index <= 0.0f) return table.values[0];
        if (index >= (float)(domain - 1)) return table.values[domain - 1];
        base = idMath::FtoiFast(idMath::Floor(index));
        frac = index - (float)base;
    }
    else {
        index *= (float)domain;
        if (index < 0.0f) index += (float)domain * idMath::Ceil(-index / (float)domain);
        base = idMath::FtoiFast(idMath::Floor(index));
        frac = index - (float)base;
        base %= domain;
    }
    if (table.snap) return table.values[base];
    const int next = (base + 1) % domain;
    return table.values[base] * (1.0f - frac) + table.values[next] * frac;
}

static float EnvelopeWeight(const q4bse::Domain* motion, float normalizedLife) {
    float lookup = normalizedLife;
    if (!motion) return lookup;
    if (motion->hasEnvelopeOffset) lookup += motion->envelopeOffset;
    if (motion->envelope.empty() || !idStr::Icmp(motion->envelope.c_str(), "linear")) return Clamp01(lookup);
    std::string error;
    M3EnvelopeTable* table = FindEnvelopeTable(motion->envelope.c_str(), error);
    if (!table) {
        static bool warned = false;
        if (!warned) { common->Warning("Q4BSE M3: %s; falling back to linear", error.c_str()); warned = true; }
        return Clamp01(lookup);
    }
    return TableLookup(*table, lookup);
}

static float SampleRange(const q4bse::Range& range, float fallback, M3Random& random) {
    if (!range.valid) return fallback;
    if (range.min == range.max) return range.min;
    return random.Range(range.min, range.max);
}

static void DomainEndpoints(const q4bse::Domain& domain, int dims, float* mins, float* maxs) {
    for (int i = 0; i < dims; ++i) { mins[i] = 0.0f; maxs[i] = 0.0f; }
    const int count = (int)domain.values.size();
    if (count <= 0) return;
    if (domain.type == "point") {
        for (int i = 0; i < dims; ++i) {
            const int index = i < count ? i : count - 1;
            mins[i] = maxs[i] = domain.values[index];
        }
        return;
    }
    int half = count / 2;
    if (half <= 0) half = 1;
    for (int i = 0; i < dims; ++i) {
        const int loIndex = i < half ? i : half - 1;
        const int hiIndex = (i + half) < count ? (i + half) : loIndex;
        mins[i] = domain.values[loIndex];
        maxs[i] = domain.values[hiIndex];
    }
}

static void SampleDomain(const q4bse::Domain* domain, int dims, float* out,
                         M3Random& random, idVec3* generatedNormal) {
    if (!domain) return;
    float mins[3] = { 0,0,0 };
    float maxs[3] = { 0,0,0 };
    DomainEndpoints(*domain, dims, mins, maxs);
    if (domain->type == "point") {
        for (int i = 0; i < dims; ++i) out[i] = mins[i];
    }
    else if (domain->type == "line") {
        const float t = random.Unit();
        for (int i = 0; i < dims; ++i) out[i] = mins[i] + (maxs[i] - mins[i]) * t;
    }
    else if (domain->type == "box") {
        for (int i = 0; i < dims; ++i) out[i] = random.Range(mins[i], maxs[i]);
    }
    else if (domain->type == "cylinder" && dims >= 3) {
        const float t = random.Unit();
        const float phi = random.Range(0.0f, M3_TWO_PI);
        const float radial = domain->surface ? 1.0f : random.Unit();
        const float cy = 0.5f * (mins[1] + maxs[1]);
        const float cz = 0.5f * (mins[2] + maxs[2]);
        const float ry = 0.5f * (maxs[1] - mins[1]);
        const float rz = 0.5f * (maxs[2] - mins[2]);
        out[0] = mins[0] + (maxs[0] - mins[0]) * t;
        out[1] = cy + idMath::Cos(phi) * ry * radial;
        out[2] = cz + idMath::Sin(phi) * rz * radial;
    }
    else {
        for (int i = 0; i < dims; ++i) out[i] = mins[i];
    }
    if (generatedNormal && dims >= 3) {
        generatedNormal->Set(out[0], out[1], out[2]);
        if (generatedNormal->LengthSqr() > M3_EPSILON) generatedNormal->NormalizeFast();
        else generatedNormal->Set(1.0f, 0.0f, 0.0f);
    }
}

static const q4bse::Domain* FindDomain(const std::vector<std::pair<std::string, q4bse::Domain> >& domains, const char* name) {
    return q4bse::FindDomain(domains, name);
}

static void SampleVec2Domain(const q4bse::Domain* domain, idVec2& value, M3Random& random) {
    float out[2] = { value.x, value.y };
    SampleDomain(domain, 2, out, random, NULL);
    value.Set(out[0], out[1]);
}
static void SampleVec3Domain(const q4bse::Domain* domain, idVec3& value, M3Random& random, idVec3* normal) {
    float out[3] = { value.x, value.y, value.z };
    SampleDomain(domain, 3, out, random, normal);
    value.Set(out[0], out[1], out[2]);
}
static void SampleFloatDomain(const q4bse::Domain* domain, float& value, M3Random& random) {
    float out[1] = { value };
    SampleDomain(domain, 1, out, random, NULL);
    value = out[0];
}
static void ApplyRelative(const q4bse::Domain* d, float start, float& end) { if (d && d->relative) end += start; }
static void ApplyRelative(const q4bse::Domain* d, const idVec2& start, idVec2& end) { if (d && d->relative) end += start; }
static void ApplyRelative(const q4bse::Domain* d, const idVec3& start, idVec3& end) { if (d && d->relative) end += start; }
static idVec2 EvalVec2(const idVec2& a, const idVec2& b, const q4bse::Domain* motion, float life) {
    if (!motion) return a; const float w = EnvelopeWeight(motion, life); return a + (b - a) * w;
}
static idVec3 EvalVec3(const idVec3& a, const idVec3& b, const q4bse::Domain* motion, float life) {
    if (!motion) return a; const float w = EnvelopeWeight(motion, life); return a + (b - a) * w;
}
static float EvalFloat(float a, float b, const q4bse::Domain* motion, float life) {
    if (!motion) return a; const float w = EnvelopeWeight(motion, life); return a + (b - a) * w;
}

static bool SpawnParticleForSegment(int segmentIndex, float birthSec) {
    if (segmentIndex < 0 || segmentIndex >= (int)g_m3ImpactEffect.segments.size()) return false;
    if ((int)g_m3Impact.particles.size() >= M3_MAX_PARTICLES) return false;
    const q4bse::Segment& segment = g_m3ImpactEffect.segments[segmentIndex];
    if (!segment.hasParticle) return false;
    const q4bse::ParticleTemplate& pt = segment.particle;
    if (pt.primitive != "sprite" && pt.primitive != "line" && pt.primitive != "oriented") return false;

    M3Particle p;
    p.segment = &segment;
    p.segmentIndex = segmentIndex;
    p.birthSec = birthSec;
    p.durationSec = SampleRange(pt.duration, 0.1f, g_m3Impact.random);
    if (p.durationSec < 0.002f) p.durationSec = 0.002f;

    const q4bse::Domain* startPosition = FindDomain(pt.start, "position");
    idVec3 generatedNormal(1.0f, 0.0f, 0.0f);
    SampleVec3Domain(startPosition, p.localPosition, g_m3Impact.random,
                     (pt.generatedOriginNormal || pt.generatedNormal) ? &generatedNormal : NULL);
    SampleVec3Domain(FindDomain(pt.start, "velocity"), p.localVelocity, g_m3Impact.random, NULL);
    const bool transformByNormal = pt.generatedOriginNormal || pt.generatedNormal;
    if (transformByNormal) p.localVelocity = generatedNormal.ToMat3() * p.localVelocity;
    if (pt.flipNormal) p.localVelocity = -p.localVelocity;
    const float gravityScale = SampleRange(pt.gravity, 0.0f, g_m3Impact.random);
    p.worldGravityAcceleration = gameLocal.GetGravity() * gravityScale;

    p.sizeStart.Set(1.0f, 1.0f); p.sizeEnd.Set(1.0f, 1.0f);
    p.tintStart.Set(1.0f, 1.0f, 1.0f); p.tintEnd.Set(0.0f, 0.0f, 0.0f);
    p.fadeStart = 1.0f; p.fadeEnd = 0.0f;
    p.rotateStart.Zero(); p.rotateEnd.Zero(); p.lengthStart.Zero(); p.lengthEnd.Zero();

    const q4bse::Domain* startSize = FindDomain(pt.start, "size");
    const q4bse::Domain* endSize = FindDomain(pt.end, "size");
    if (pt.primitive == "line") {
        float a = p.sizeStart.x, b = p.sizeEnd.x;
        SampleFloatDomain(startSize, a, g_m3Impact.random);
        SampleFloatDomain(endSize, b, g_m3Impact.random);
        ApplyRelative(endSize, a, b);
        p.sizeStart.Set(a, a); p.sizeEnd.Set(b, b);
    } else {
        SampleVec2Domain(startSize, p.sizeStart, g_m3Impact.random);
        SampleVec2Domain(endSize, p.sizeEnd, g_m3Impact.random);
        ApplyRelative(endSize, p.sizeStart, p.sizeEnd);
    }

    const q4bse::Domain* startTint = FindDomain(pt.start, "tint");
    const q4bse::Domain* endTint = FindDomain(pt.end, "tint");
    SampleVec3Domain(startTint, p.tintStart, g_m3Impact.random, NULL);
    SampleVec3Domain(endTint, p.tintEnd, g_m3Impact.random, NULL);
    ApplyRelative(endTint, p.tintStart, p.tintEnd);

    const q4bse::Domain* startFade = FindDomain(pt.start, "fade");
    const q4bse::Domain* endFade = FindDomain(pt.end, "fade");
    SampleFloatDomain(startFade, p.fadeStart, g_m3Impact.random);
    SampleFloatDomain(endFade, p.fadeEnd, g_m3Impact.random);
    ApplyRelative(endFade, p.fadeStart, p.fadeEnd);

    const q4bse::Domain* startRotate = FindDomain(pt.start, "rotate");
    const q4bse::Domain* endRotate = FindDomain(pt.end, "rotate");
    if (pt.primitive == "oriented") {
        SampleVec3Domain(startRotate, p.rotateStart, g_m3Impact.random, NULL);
        SampleVec3Domain(endRotate, p.rotateEnd, g_m3Impact.random, NULL);
        ApplyRelative(endRotate, p.rotateStart, p.rotateEnd);
        p.rotateStart *= M3_TWO_PI; p.rotateEnd *= M3_TWO_PI;
    } else {
        float a = 0.0f, b = 0.0f;
        SampleFloatDomain(startRotate, a, g_m3Impact.random);
        SampleFloatDomain(endRotate, b, g_m3Impact.random);
        ApplyRelative(endRotate, a, b);
        p.rotateStart.Set(a * M3_TWO_PI, 0, 0); p.rotateEnd.Set(b * M3_TWO_PI, 0, 0);
    }

    const q4bse::Domain* startLength = FindDomain(pt.start, "length");
    const q4bse::Domain* endLength = FindDomain(pt.end, "length");
    SampleVec3Domain(startLength, p.lengthStart, g_m3Impact.random, NULL);
    SampleVec3Domain(endLength, p.lengthEnd, g_m3Impact.random, NULL);
    ApplyRelative(endLength, p.lengthStart, p.lengthEnd);
    if (transformByNormal) {
        const idMat3 normalAxis = generatedNormal.ToMat3();
        p.lengthStart = normalAxis * p.lengthStart;
        p.lengthEnd = normalAxis * p.lengthEnd;
    }
    if (pt.flipNormal) { p.lengthStart = -p.lengthStart; p.lengthEnd = -p.lengthEnd; }

    g_m3Impact.particles.push_back(p);
    return true;
}

static void PlaySoundSegment(const q4bse::Segment& segment) {
    if (!gameSoundWorld || !declManager || segment.soundShader.empty()) return;
    const idSoundShader* shader = declManager->FindSound(segment.soundShader.c_str(), false);
    if (!shader) { common->Warning("Q4BSE M3: sound shader not found: %s", segment.soundShader.c_str()); return; }
    idPlayer* player = gameLocal.GetLocalPlayer();
    idSoundEmitter* emitter = gameSoundWorld->AllocSoundEmitter();
    if (!emitter) return;
    emitter->UpdateEmitter(g_m3Impact.origin, player ? player->GetListenerId() : 0, NULL);
    emitter->StartSound(shader, SCHANNEL_ONE, 0.0f, 0, true);
    emitter->Free(false);
}

static void ProjectDecalSegment(const q4bse::Segment& segment) {
    if (!gameRenderWorld || !declManager || !segment.hasParticle) return;
    const q4bse::ParticleTemplate& pt = segment.particle;
    const idMaterial* material = declManager->FindMaterial(pt.material.c_str(), false);
    if (!material) { common->Warning("Q4BSE M3: decal material not found: %s", pt.material.c_str()); return; }
    idVec2 size(16.0f, 16.0f);
    float rotate = 0.0f;
    SampleVec2Domain(FindDomain(pt.start, "size"), size, g_m3Impact.random);
    SampleFloatDomain(FindDomain(pt.start, "rotate"), rotate, g_m3Impact.random);
    rotate *= M3_TWO_PI;
    float decalSize = idMath::Fabs(size.x);
    if (idMath::Fabs(size.y) > decalSize) decalSize = idMath::Fabs(size.y);
    if (decalSize < 1.0f) decalSize = 1.0f;
    const idVec3 normal = g_m3Impact.axis[0];
    idVec3 tangent0, tangent1;
    normal.NormalVectors(tangent0, tangent1);
    float s = 0.0f, c = 1.0f;
    idMath::SinCos(rotate, s, c);
    const idVec3 right = tangent0 * c + tangent1 * -s;
    const idVec3 up = tangent0 * -s + tangent1 * -c;
    const float depth = 8.0f;
    const idVec3 wo = g_m3Impact.origin + normal * depth;
    idFixedWinding winding;
    winding.Clear();
    winding += idVec5(wo + right * decalSize + up * decalSize, idVec2(1,1));
    winding += idVec5(wo - right * decalSize + up * decalSize, idVec2(0,1));
    winding += idVec5(wo - right * decalSize - up * decalSize, idVec2(0,0));
    winding += idVec5(wo + right * decalSize - up * decalSize, idVec2(1,0));
    const idVec3 projectionOrigin = g_m3Impact.origin - normal * depth;
    gameRenderWorld->ProjectDecalOntoWorld(winding, projectionOrigin, true, depth, material, gameLocal.time);
}

static int SampleSpawnerCount(const q4bse::Segment& segment) {
    if (!segment.count.valid) return 1;
    const float sampled = SampleRange(segment.count, 1.0f, g_m3Impact.random);
    int count = idMath::FtoiFast(idMath::Ceil(sampled));
    if (count < 0) count = 0;
    if (count > M3_MAX_PARTICLES) count = M3_MAX_PARTICLES;
    return count;
}

static void StartAllSegments(void) {
    g_m3Impact.emitters.clear();
    g_m3Impact.emitters.resize(g_m3ImpactEffect.segments.size());
    for (int i = 0; i < (int)g_m3ImpactEffect.segments.size(); ++i) {
        const q4bse::Segment& segment = g_m3ImpactEffect.segments[i];
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

static void ServiceEmitters(float elapsedSec) {
    const float future = elapsedSec + (1.0f / 60.0f);
    for (int i = 0; i < (int)g_m3Impact.emitters.size(); ++i) {
        M3EmitterState& emitter = g_m3Impact.emitters[i];
        if (!emitter.active) continue;
        while (emitter.nextSpawnSec < emitter.endSec && emitter.nextSpawnSec < future) {
            if (!SpawnParticleForSegment(i, emitter.nextSpawnSec)) { emitter.active = false; break; }
            emitter.nextSpawnSec += emitter.intervalSec;
        }
        if (emitter.nextSpawnSec >= emitter.endSec) emitter.active = false;
    }
}

static idVec3 ParticleWorldPosition(const M3Particle& p, float ageSec) {
    const idVec3 local = p.localPosition + p.localVelocity * ageSec;
    idVec3 world = g_m3Impact.origin + g_m3Impact.axis * local;
    world += p.worldGravityAcceleration * (0.5f * ageSec * ageSec);
    return world;
}

static bool AddSurface(idRenderModel* model, const q4bse::ParticleTemplate& pt,
                       const idVec3* points, const float* st, int pointCount,
                       const int* indexes, int indexCount, const idVec4& color) {
    if (!model || !declManager || pointCount <= 0 || indexCount <= 0) return false;
    const idMaterial* material = declManager->FindMaterial(pt.material.c_str(), false);
    if (!material) return false;
    srfTriangles_t* tri = model->AllocSurfaceTriangles(pointCount, indexCount);
    if (!tri || !tri->verts || !tri->indexes) return false;
    const bool additive = IsAdditive(pt);
    for (int i = 0; i < pointCount; ++i) SetDrawVert(tri->verts[i], points[i], st[i*2], st[i*2+1], color, additive);
    for (int i = 0; i < indexCount; ++i) tri->indexes[i] = indexes[i];
    tri->numVerts = pointCount;
    tri->numIndexes = indexCount;
    tri->generateNormals = false;
    modelSurface_t surface;
    surface.id = model->NumSurfaces();
    surface.shader = material;
    surface.geometry = tri;
    model->AddSurface(surface);
    return true;
}

static bool RenderParticle(idRenderModel* model, const M3Particle& p, float elapsedSec,
                           const idVec3& viewOrigin, const idMat3& viewAxis) {
    if (!p.segment) return false;
    const q4bse::ParticleTemplate& pt = p.segment->particle;
    const float age = elapsedSec - p.birthSec;
    if (age < 0.0f || age >= p.durationSec) return false;
    const float life = Clamp01(age / p.durationSec);
    const idVec3 tint = EvalVec3(p.tintStart, p.tintEnd, FindDomain(pt.motion, "tint"), life);
    const float fade = EvalFloat(p.fadeStart, p.fadeEnd, FindDomain(pt.motion, "fade"), life);
    if (fade <= 0.0f) return false;
    const idVec4 color(tint.x, tint.y, tint.z, fade);
    const idVec3 worldPos = ParticleWorldPosition(p, age);
    static const int idx[6] = {0,1,2,0,2,3};
    static const float st[8] = {0,0,0,1,1,1,1,0};

    if (pt.primitive == "sprite") {
        const idVec2 size = EvalVec2(p.sizeStart, p.sizeEnd, FindDomain(pt.motion, "size"), life);
        const float rotate = EvalFloat(p.rotateStart.x, p.rotateEnd.x, FindDomain(pt.motion, "rotate"), life);
        float s = 0.0f, c = 1.0f;
        idMath::SinCos(rotate, s, c);
        const idVec3 right = (viewAxis[1] * c - viewAxis[2] * s) * size.x;
        const idVec3 up = (viewAxis[1] * s + viewAxis[2] * c) * size.y;
        idVec3 points[4] = { worldPos - right, worldPos - up, worldPos + right, worldPos + up };
        return AddSurface(model, pt, points, st, 4, idx, 6, color);
    }
    if (pt.primitive == "line") {
        const float width = EvalFloat(p.sizeStart.x, p.sizeEnd.x, FindDomain(pt.motion, "size"), life);
        const idVec3 localLength = EvalVec3(p.lengthStart, p.lengthEnd, FindDomain(pt.motion, "length"), life);
        const idVec3 length = g_m3Impact.axis * localLength;
        const idVec3 end = worldPos + length;
        const idVec3 toView = viewOrigin - (worldPos + length * 0.5f);
        idVec3 side = length.Cross(toView);
        if (side.LengthSqr() > M3_EPSILON) side.NormalizeFast(); else side = viewAxis[1];
        side *= idMath::Fabs(width);
        idVec3 points[4] = { worldPos + side, worldPos - side, end - side, end + side };
        return AddSurface(model, pt, points, st, 4, idx, 6, color);
    }
    if (pt.primitive == "oriented") {
        const idVec2 size = EvalVec2(p.sizeStart, p.sizeEnd, FindDomain(pt.motion, "size"), life);
        const idVec3 rotate = EvalVec3(p.rotateStart, p.rotateEnd, FindDomain(pt.motion, "rotate"), life);
        const idAngles angles(RAD2DEG(rotate.x), RAD2DEG(rotate.y), RAD2DEG(rotate.z));
        const idMat3 localRotation = angles.ToMat3();
        const idVec3 right = g_m3Impact.axis * (localRotation[1] * -size.x);
        const idVec3 up = g_m3Impact.axis * (localRotation[2] * size.y);
        idVec3 points[4] = { worldPos - right, worldPos - up, worldPos + right, worldPos + up };
        return AddSurface(model, pt, points, st, 4, idx, 6, color);
    }
    return false;
}

static void FreeImpact(void) {
    if (gameRenderWorld && g_m3Impact.entityHandle >= 0) gameRenderWorld->FreeEntityDef(g_m3Impact.entityHandle);
    g_m3Impact.entityHandle = -1;
    if (g_m3Impact.model && renderModelManager) renderModelManager->FreeModel(g_m3Impact.model);
    g_m3Impact.model = NULL;
    g_m3Impact.particles.clear();
    g_m3Impact.emitters.clear();
    g_m3Impact.active = false;
}

static bool RebuildImpactModel(float elapsedSec) {
    if (!g_m3Impact.active || !g_m3Impact.model || !renderModelManager) return false;
    idPlayer* player = gameLocal.GetLocalPlayer();
    if (!player) return false;
    g_m3Impact.model->InitEmpty("_q4bse_m3_impact");
    int rendered = 0;
    for (size_t i = 0; i < g_m3Impact.particles.size(); ++i) {
        if (RenderParticle(g_m3Impact.model, g_m3Impact.particles[i], elapsedSec,
                           player->firstPersonViewOrigin, player->firstPersonViewAxis)) ++rendered;
    }
    g_m3Impact.model->FinishSurfaces();
    if (g_m3Impact.entityHandle >= 0 && gameRenderWorld) gameRenderWorld->UpdateEntityDef(g_m3Impact.entityHandle, &g_m3Impact.renderEntity);
    return rendered > 0;
}

static bool StartImpactAt(const idVec3& origin, const idVec3& normal) {
    if (!g_m3ImpactLoaded || !gameRenderWorld || !renderModelManager) return false;
    FreeImpact();
    g_m3Impact.active = true;
    g_m3Impact.origin = origin;
    idVec3 n = normal;
    if (n.LengthSqr() <= M3_EPSILON) n.Set(1,0,0);
    n.NormalizeFast();
    g_m3Impact.axis = n.ToMat3();
    g_m3Impact.startTimeMS = gameLocal.time;
    g_m3Impact.random = M3Random((unsigned int)gameLocal.time ^ 0x51ed270bu);
    g_m3Impact.model = renderModelManager->AllocModel();
    if (!g_m3Impact.model) { g_m3Impact.active = false; return false; }
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
    if (g_m3Impact.entityHandle < 0) { common->Warning("Q4BSE M3: AddEntityDef failed"); FreeImpact(); return false; }
    common->Printf("Q4BSE M3 PLAY: full %s at (%.1f %.1f %.1f), normal=(%.2f %.2f %.2f), particles=%d\n",
                   g_m3ImpactEffect.name.c_str(), origin.x, origin.y, origin.z, n.x, n.y, n.z, (int)g_m3Impact.particles.size());
    return true;
}

static bool AnyEmitterActive(void) {
    for (size_t i = 0; i < g_m3Impact.emitters.size(); ++i) if (g_m3Impact.emitters[i].active) return true;
    return false;
}
static bool AnyParticleAlive(float elapsedSec) {
    for (size_t i = 0; i < g_m3Impact.particles.size(); ++i) {
        const M3Particle& p = g_m3Impact.particles[i];
        if (elapsedSec >= p.birthSec && elapsedSec < p.birthSec + p.durationSec) return true;
    }
    return false;
}

static void Cmd_M3Impact(const idCmdArgs& args) {
    if (!g_m3ImpactLoaded) { common->Warning("Q4BSE M3: impact_default.fx is not loaded"); return; }
    if (!gameRenderWorld) { common->Warning("Q4BSE M3: load a map first"); return; }
    idPlayer* player = gameLocal.GetLocalPlayer();
    if (!player) { common->Warning("Q4BSE M3: no local player"); return; }
    const idVec3 start = player->firstPersonViewOrigin;
    const idVec3 end = start + player->firstPersonViewAxis[0] * 4096.0f;
    modelTrace_t trace;
    memset(&trace, 0, sizeof(trace));
    if (!gameRenderWorld->Trace(trace, start, end, 0.0f, true, true)) {
        common->Warning("Q4BSE M3: crosshair trace did not hit world geometry");
        return;
    }
    const idVec3 effectOrigin = trace.point + trace.normal * 0.15f;
    StartImpactAt(effectOrigin, trace.normal);
}

static void Cmd_M3Status(const idCmdArgs& args) {
    common->Printf("Q4BSE M3 full-impact status:\n");
    common->Printf("  impact_default.fx: %s (%d segments)\n", g_m3ImpactLoaded ? "parsed" : "not parsed",
                   g_m3ImpactLoaded ? (int)g_m3ImpactEffect.segments.size() : 0);
    common->Printf("  active impact: %s\n", g_m3Impact.active ? "yes" : "no");
    common->Printf("  runtime particles allocated: %d\n", (int)g_m3Impact.particles.size());
}

} // anonymous namespace

void Q4BSE_M3_Init(void) {
    if (g_m3Initialized) return;
    g_m3Initialized = true;
    cmdSystem->AddCommand("q4bse_m3_impact", Cmd_M3Impact, CMD_FL_GAME,
                          "traces from the crosshair and plays the full parsed Raven HyperBlaster impact");
    cmdSystem->AddCommand("q4bse_m3_status", Cmd_M3Status, CMD_FL_GAME, "prints M3 full-impact runtime status");
    common->Printf("Q4BSE M3: full HyperBlaster impact runtime initialized\n");
}

void Q4BSE_M3_Shutdown(void) {
    if (!g_m3Initialized) return;
    Q4BSE_M3_EndMap();
    cmdSystem->RemoveCommand("q4bse_m3_impact");
    cmdSystem->RemoveCommand("q4bse_m3_status");
    g_m3Initialized = false;
}

void Q4BSE_M3_BeginMap(void) {
    FreeImpact();
    ClearEnvelopeTables();
    g_m3ImpactLoaded = LoadEffect("effects/weapons/hyperblaster/impact_default.fx", g_m3ImpactEffect);
    if (g_m3ImpactLoaded) common->Printf("Q4BSE M3 READY: q4bse_m3_impact executes sound + decal + sprite + line + emitter + oriented segments\n");
}

void Q4BSE_M3_EndMap(void) {
    FreeImpact();
    ClearEnvelopeTables();
    g_m3ImpactLoaded = false;
    g_m3ImpactEffect = q4bse::Effect();
}

void Q4BSE_M3_Frame(int gameTimeMS) {
    if (!g_m3Impact.active) return;
    const float elapsedSec = (float)(gameTimeMS - g_m3Impact.startTimeMS) * 0.001f;
    ServiceEmitters(elapsedSec);
    if (!AnyEmitterActive() && !AnyParticleAlive(elapsedSec)) { FreeImpact(); return; }
    RebuildImpactModel(elapsedSec);
}
