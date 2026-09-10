#include "../../idlib/precompiled.h"
#pragma hdrstop

#include "../Game_local.h"

// Doom 3's legacy headers intentionally macro-wrap several CRT names and the
// Win32 headers expose min/max macros.  This translation unit also embeds the
// portable Q4BSE parser, which uses the modern C++ standard library.  Drop the
// legacy macros here, after the Doom headers are parsed, so they cannot rewrite
// declarations inside <string>/<cstdio> or Range::min/Range::max.
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
#include "Q4BSECore.h"
#include "Q4BSEDoom3.h"

#include <string>
#include <vector>
#include <stdexcept>
#include <string.h>

namespace {

struct EnvelopeTableCache {
    std::string name;
    bool valid;
    bool clamp;
    bool snap;
    std::vector<float> values;

    EnvelopeTableCache() : valid(false), clamp(false), snap(false) {}
};

struct SpriteSample {
    q4bse::Vec3 position;
    q4bse::Vec2 size;
    q4bse::Vec3 tint;
    float fade;
    float rotate;

    SpriteSample() : size(1.0f, 1.0f), tint(1.0f, 1.0f, 1.0f), fade(1.0f), rotate(0.0f) {}
};

struct LiveSpriteInstance {
    bool active;
    bool animateEnvelopes;
    qhandle_t entityHandle;
    idRenderModel* model;
    const q4bse::Effect* effect;
    const q4bse::Segment* segment;
    idVec3 anchorOrigin;
    idMat3 anchorAxis;
    renderEntity_t renderEntity;
    int startTime;
    int endTime;
    float durationSec;

    LiveSpriteInstance()
        : active(false), animateEnvelopes(false), entityHandle(-1), model(NULL),
          effect(NULL), segment(NULL), startTime(0), endTime(0), durationSec(0.0f) {
        memset(&renderEntity, 0, sizeof(renderEntity));
    }
};

static bool g_initialized = false;
static bool g_impactLoaded = false;
static bool g_flyLoaded = false;
static q4bse::Effect g_impact;
static q4bse::Effect g_fly;
static LiveSpriteInstance g_liveSprite;
static std::vector<EnvelopeTableCache> g_envelopeTables;

static bool LoadQ4Fx(const char* path, q4bse::Effect& out) {
    void* buffer = NULL;
    const int len = fileSystem->ReadFile(path, &buffer, NULL);
    if (len < 0 || buffer == NULL) {
        common->Warning("Q4BSE M2: VFS could not read %s", path);
        return false;
    }

    bool ok = false;
    try {
        q4bse::Parser parser;
        out = parser.Parse(std::string((const char*)buffer, (size_t)len), path);
        common->Printf("Q4BSE M2: parsed %s (%d bytes, %d segments)\n",
                       path, len, (int)out.segments.size());
        ok = true;
    }
    catch (const std::exception& e) {
        common->Warning("Q4BSE M2: parse failure %s: %s", path, e.what());
    }
    catch (...) {
        common->Warning("Q4BSE M2: parse failure %s: unknown exception", path);
    }

    fileSystem->FreeFile(buffer);
    return ok;
}

static void ClearEnvelopeTables(void) {
    g_envelopeTables.clear();
}

static bool ParseDeclTableText(const idDecl* decl, EnvelopeTableCache& table, std::string& error) {
    if (!decl) {
        error = "null table declaration";
        return false;
    }

    const int textLen = decl->GetTextLength();
    if (textLen <= 0) {
        error = std::string("empty table declaration: ") + decl->GetName();
        return false;
    }

    char* text = new char[textLen + 1];
    decl->GetText(text);
    text[textLen] = '\0';

    idLexer src;
    src.LoadMemory(text, textLen, decl->GetFileName(), decl->GetLineNum());
    src.SetFlags(DECL_LEXER_FLAGS);

    bool ok = true;
    if (!src.SkipUntilString("{")) {
        error = std::string("table has no opening brace: ") + decl->GetName();
        ok = false;
    }

    idToken token;
    while (ok && src.ReadToken(&token)) {
        if (token == "}") {
            break;
        }

        if (!token.Icmp("snap")) {
            table.snap = true;
            continue;
        }
        if (!token.Icmp("clamp")) {
            table.clamp = true;
            continue;
        }
        if (token == "{") {
            while (src.ReadToken(&token)) {
                if (token == "}") {
                    break;
                }
                if (token == ",") {
                    continue;
                }

                src.UnreadToken(&token);
                bool parseError = false;
                const float value = src.ParseFloat(&parseError);
                if (parseError) {
                    error = std::string("non-numeric value in table ") + decl->GetName();
                    ok = false;
                    break;
                }
                table.values.push_back(value);
            }
            continue;
        }

        error = std::string("unsupported token in table ") + decl->GetName() + ": " + token.c_str();
        ok = false;
    }

    delete[] text;

    if (ok && table.values.empty()) {
        error = std::string("table has no values: ") + decl->GetName();
        ok = false;
    }

    return ok;
}

static EnvelopeTableCache* FindEnvelopeTable(const char* name, std::string& error) {
    if (!name || !name[0]) {
        error = "empty envelope table name";
        return NULL;
    }

    for (size_t i = 0; i < g_envelopeTables.size(); ++i) {
        if (g_envelopeTables[i].name == name) {
            if (!g_envelopeTables[i].valid) {
                error = std::string("envelope table unavailable: ") + name;
                return NULL;
            }
            return &g_envelopeTables[i];
        }
    }

    EnvelopeTableCache cache;
    cache.name = name;

    const idDecl* decl = declManager ? declManager->FindType(DECL_TABLE, name, false) : NULL;
    if (!decl) {
        error = std::string("Raven envelope table not found: ") + name;
        g_envelopeTables.push_back(cache);
        return NULL;
    }

    if (!ParseDeclTableText(decl, cache, error)) {
        g_envelopeTables.push_back(cache);
        return NULL;
    }

    cache.valid = true;
    g_envelopeTables.push_back(cache);
    EnvelopeTableCache& stored = g_envelopeTables.back();

    common->Printf("Q4BSE M2: loaded Raven table %s (%d values, %s%s)\n",
                   name, (int)stored.values.size(),
                   stored.clamp ? "clamp" : "wrap",
                   stored.snap ? ", snap" : "");
    return &stored;
}

static float LookupEnvelopeTable(const EnvelopeTableCache& table, float index) {
    const int domain = (int)table.values.size();
    if (domain <= 1) {
        return 1.0f;
    }

    int iIndex = 0;
    float iFrac = 0.0f;

    if (table.clamp) {
        index *= (float)(domain - 1);
        if (index >= (float)(domain - 1)) {
            return table.values[domain - 1];
        }
        if (index <= 0.0f) {
            return table.values[0];
        }

        iIndex = idMath::Ftoi(index);
        iFrac = index - (float)iIndex;
    }
    else {
        index *= (float)domain;
        if (index < 0.0f) {
            index += (float)domain * idMath::Ceil(-index / (float)domain);
        }

        iIndex = idMath::FtoiFast(idMath::Floor(index));
        iFrac = index - (float)iIndex;
        iIndex %= domain;
    }

    if (table.snap) {
        return table.values[iIndex];
    }

    const int next = (iIndex + 1) % domain;
    return table.values[iIndex] * (1.0f - iFrac) + table.values[next] * iFrac;
}

static bool EvaluateEnvelopeWeight(const q4bse::Domain* motion, float normalizedLife,
                                   float& weight, std::string& error) {
    float lookup = normalizedLife;

    if (motion) {
        // Justin Marshall's rvEnvParms defaults to mRate=1 and mIsCount=1,
        // making the default lookup rate normalized particle lifetime.
        // The current parser has not split authored "rate"/"count" controls
        // into distinct fields yet, so do not silently claim those extensions.
        if (!motion->values.empty()) {
            error = "motion envelope contains rate/count values not split by the M2 parser yet";
            return false;
        }

        if (motion->hasEnvelopeOffset) {
            lookup += motion->envelopeOffset;
        }

        if (!motion->envelope.empty() && motion->envelope != "linear") {
            EnvelopeTableCache* table = FindEnvelopeTable(motion->envelope.c_str(), error);
            if (!table) {
                return false;
            }
            weight = LookupEnvelopeTable(*table, lookup);
            return true;
        }
    }

    weight = lookup;
    return true;
}

static void AddRelative1(const q4bse::Domain* d, float start, float& end) {
    if (d && d->relative) {
        end += start;
    }
}

static void AddRelative2(const q4bse::Domain* d, const q4bse::Vec2& start, q4bse::Vec2& end) {
    if (d && d->relative) {
        end.x += start.x;
        end.y += start.y;
    }
}

static void AddRelative3(const q4bse::Domain* d, const q4bse::Vec3& start, q4bse::Vec3& end) {
    if (d && d->relative) {
        end.x += start.x;
        end.y += start.y;
        end.z += start.z;
    }
}

static bool EvaluateSpriteSample(const q4bse::Effect& fx, const char* segmentName,
                                 float normalizedLife, SpriteSample& out, std::string& error) {
    const q4bse::Segment* segment = q4bse::FindSegment(fx, segmentName);
    if (!segment || !segment->hasParticle || segment->particle.primitive != "sprite") {
        error = "selected segment is not a parsed sprite";
        return false;
    }

    q4bse::SpawnProbe start;
    if (!q4bse::BuildSpriteSpawnProbe(fx, segmentName, start, error)) {
        return false;
    }

    out.position = start.position;
    out.size = start.size;
    out.fade = start.fade;
    out.rotate = start.rotate;
    out.tint = q4bse::Vec3(1.0f, 1.0f, 1.0f);

    const q4bse::Domain* startTint = q4bse::FindDomain(segment->particle.start, "tint");
    if (startTint && !q4bse::EvalPoint3(startTint, out.tint)) {
        error = "M2 requires point start tint for sprite execution";
        return false;
    }

    // Raven defaults recovered from rvParticleTemplate::Init:
    // death size=ONE, death fade=NONE, death tint=NONE, death rotate=NONE.
    q4bse::Vec2 endSize(1.0f, 1.0f);
    float endFade = 0.0f;
    q4bse::Vec3 endTint(0.0f, 0.0f, 0.0f);
    float endRotate = 0.0f;

    const q4bse::Domain* endSizeDomain = q4bse::FindDomain(segment->particle.end, "size");
    const q4bse::Domain* endFadeDomain = q4bse::FindDomain(segment->particle.end, "fade");
    const q4bse::Domain* endTintDomain = q4bse::FindDomain(segment->particle.end, "tint");
    const q4bse::Domain* endRotateDomain = q4bse::FindDomain(segment->particle.end, "rotate");

    if (endSizeDomain && !q4bse::EvalPoint2(endSizeDomain, endSize)) {
        error = "M2 requires point end size for sprite execution";
        return false;
    }
    if (endFadeDomain && !q4bse::EvalPoint1(endFadeDomain, endFade)) {
        error = "M2 requires point end fade for sprite execution";
        return false;
    }
    if (endTintDomain && !q4bse::EvalPoint3(endTintDomain, endTint)) {
        error = "M2 requires point end tint for sprite execution";
        return false;
    }
    if (endRotateDomain && !q4bse::EvalPoint1(endRotateDomain, endRotate)) {
        error = "M2 requires point end rotate for sprite execution";
        return false;
    }

    AddRelative2(endSizeDomain, start.size, endSize);
    AddRelative1(endFadeDomain, start.fade, endFade);
    AddRelative3(endTintDomain, out.tint, endTint);
    AddRelative1(endRotateDomain, start.rotate, endRotate);

    const q4bse::Domain* sizeMotion = q4bse::FindDomain(segment->particle.motion, "size");
    const q4bse::Domain* fadeMotion = q4bse::FindDomain(segment->particle.motion, "fade");
    const q4bse::Domain* tintMotion = q4bse::FindDomain(segment->particle.motion, "tint");
    const q4bse::Domain* rotateMotion = q4bse::FindDomain(segment->particle.motion, "rotate");

    float weight = 0.0f;

    if (endSizeDomain || sizeMotion) {
        if (!EvaluateEnvelopeWeight(sizeMotion, normalizedLife, weight, error)) return false;
        out.size.x = start.size.x + (endSize.x - start.size.x) * weight;
        out.size.y = start.size.y + (endSize.y - start.size.y) * weight;
    }

    if (endFadeDomain || fadeMotion) {
        if (!EvaluateEnvelopeWeight(fadeMotion, normalizedLife, weight, error)) return false;
        out.fade = start.fade + (endFade - start.fade) * weight;
    }

    if (endTintDomain || tintMotion) {
        if (!EvaluateEnvelopeWeight(tintMotion, normalizedLife, weight, error)) return false;
        out.tint.x = out.tint.x + (endTint.x - out.tint.x) * weight;
        out.tint.y = out.tint.y + (endTint.y - out.tint.y) * weight;
        out.tint.z = out.tint.z + (endTint.z - out.tint.z) * weight;
    }

    if (endRotateDomain || rotateMotion) {
        if (!EvaluateEnvelopeWeight(rotateMotion, normalizedLife, weight, error)) return false;
        out.rotate = start.rotate + (endRotate - start.rotate) * weight;
    }

    return true;
}

static void FreeLiveSprite(void) {
    if (!g_liveSprite.active && !g_liveSprite.model) return;

    if (gameRenderWorld && g_liveSprite.entityHandle >= 0) {
        gameRenderWorld->FreeEntityDef(g_liveSprite.entityHandle);
    }
    g_liveSprite.entityHandle = -1;

    if (g_liveSprite.model && renderModelManager) {
        renderModelManager->FreeModel(g_liveSprite.model);
    }

    g_liveSprite.model = NULL;
    g_liveSprite.effect = NULL;
    g_liveSprite.segment = NULL;
    g_liveSprite.active = false;
    g_liveSprite.animateEnvelopes = false;
}

static void SetVertex(idDrawVert& v, const idVec3& xyz, float s, float t) {
    v.Clear();
    v.xyz = xyz;
    v.st.Set(s, t);
    v.normal.Set(1.0f, 0.0f, 0.0f);
    v.tangents[0].Set(0.0f, 1.0f, 0.0f);
    v.tangents[1].Set(0.0f, 0.0f, 1.0f);
    v.color[0] = 255;
    v.color[1] = 255;
    v.color[2] = 255;
    v.color[3] = 255;
}

static bool PopulateSpriteModel(idRenderModel* model, const char* materialName,
                                float widthRadius, float heightRadius) {
    if (!model || !declManager) return false;

    const idMaterial* material = declManager->FindMaterial(materialName, false);
    if (!material) {
        common->Warning("Q4BSE M2: material not found: %s", materialName);
        return false;
    }

    model->InitEmpty("_q4bse_live_sprite");

    srfTriangles_t* tri = model->AllocSurfaceTriangles(4, 6);
    if (!tri || !tri->verts || !tri->indexes) {
        return false;
    }

    // Raven rvSpriteParticle uses authored size as radii.
    SetVertex(tri->verts[0], idVec3(0.0f, -widthRadius, -heightRadius), 0.0f, 1.0f);
    SetVertex(tri->verts[1], idVec3(0.0f,  widthRadius, -heightRadius), 1.0f, 1.0f);
    SetVertex(tri->verts[2], idVec3(0.0f,  widthRadius,  heightRadius), 1.0f, 0.0f);
    SetVertex(tri->verts[3], idVec3(0.0f, -widthRadius,  heightRadius), 0.0f, 0.0f);

    tri->indexes[0] = 0; tri->indexes[1] = 1; tri->indexes[2] = 2;
    tri->indexes[3] = 0; tri->indexes[4] = 2; tri->indexes[5] = 3;
    tri->numVerts = 4;
    tri->numIndexes = 6;
    tri->generateNormals = false;

    modelSurface_t surface;
    surface.id = 0;
    surface.shader = material;
    surface.geometry = tri;
    model->AddSurface(surface);
    model->FinishSurfaces();
    return true;
}

static idRenderModel* BuildSpriteModel(const char* materialName, float widthRadius, float heightRadius) {
    if (!renderModelManager) return NULL;

    idRenderModel* model = renderModelManager->AllocModel();
    if (!model) return NULL;

    if (!PopulateSpriteModel(model, materialName, widthRadius, heightRadius)) {
        renderModelManager->FreeModel(model);
        return NULL;
    }
    return model;
}

static idVec3 SampleOrigin(const LiveSpriteInstance& instance, const SpriteSample& sample) {
    return instance.anchorOrigin +
           instance.anchorAxis[0] * sample.position.x +
           instance.anchorAxis[1] * sample.position.y +
           instance.anchorAxis[2] * sample.position.z;
}

static bool UpdateLiveSpriteVisual(float normalizedLife, bool rebuildGeometry) {
    if (!g_liveSprite.active || !g_liveSprite.effect || !g_liveSprite.segment) return false;

    SpriteSample sample;
    std::string error;
    if (!EvaluateSpriteSample(*g_liveSprite.effect, g_liveSprite.segment->name.c_str(),
                              normalizedLife, sample, error)) {
        common->Warning("Q4BSE M2: sprite evaluation failed: %s", error.c_str());
        return false;
    }

    if (rebuildGeometry) {
        if (!PopulateSpriteModel(g_liveSprite.model,
                                 g_liveSprite.segment->particle.material.c_str(),
                                 sample.size.x, sample.size.y)) {
            common->Warning("Q4BSE M2: failed to rebuild live sprite geometry");
            return false;
        }
    }

    g_liveSprite.renderEntity.origin = SampleOrigin(g_liveSprite, sample);
    g_liveSprite.renderEntity.shaderParms[SHADERPARM_RED] = sample.tint.x;
    g_liveSprite.renderEntity.shaderParms[SHADERPARM_GREEN] = sample.tint.y;
    g_liveSprite.renderEntity.shaderParms[SHADERPARM_BLUE] = sample.tint.z;
    g_liveSprite.renderEntity.shaderParms[SHADERPARM_ALPHA] = sample.fade;

    if (gameRenderWorld && g_liveSprite.entityHandle >= 0) {
        gameRenderWorld->UpdateEntityDef(g_liveSprite.entityHandle, &g_liveSprite.renderEntity);
    }

    return true;
}

static bool PlaySpriteSegment(const q4bse::Effect& fx, const char* segmentName,
                              bool animateEnvelopes, const char* milestoneLabel) {
    if (!gameRenderWorld) {
        common->Warning("Q4BSE %s: no gameRenderWorld (load a map first)", milestoneLabel);
        return false;
    }

    idPlayer* player = gameLocal.GetLocalPlayer();
    if (!player) {
        common->Warning("Q4BSE %s: no local player", milestoneLabel);
        return false;
    }

    const q4bse::Segment* segment = q4bse::FindSegment(fx, segmentName);
    if (!segment || !segment->hasParticle || segment->particle.primitive != "sprite") {
        common->Warning("Q4BSE %s: segment %s is not a parsed sprite", milestoneLabel, segmentName);
        return false;
    }

    float durationSec = 0.0f;
    if (!q4bse::GetParticleDuration(fx, segmentName, durationSec) || durationSec <= 0.0f) {
        common->Warning("Q4BSE %s: segment %s has no valid duration", milestoneLabel, segmentName);
        return false;
    }

    SpriteSample sample;
    std::string error;
    if (!EvaluateSpriteSample(fx, segmentName, 0.0f, sample, error)) {
        common->Warning("Q4BSE %s: initial sprite evaluation failed: %s",
                        milestoneLabel, error.c_str());
        return false;
    }

    FreeLiveSprite();

    idRenderModel* model = BuildSpriteModel(segment->particle.material.c_str(),
                                            sample.size.x, sample.size.y);
    if (!model) {
        common->Warning("Q4BSE %s: failed to build render model for material %s",
                        milestoneLabel, segment->particle.material.c_str());
        return false;
    }

    g_liveSprite.active = true;
    g_liveSprite.animateEnvelopes = animateEnvelopes;
    g_liveSprite.model = model;
    g_liveSprite.effect = &fx;
    g_liveSprite.segment = segment;
    g_liveSprite.anchorAxis = player->firstPersonViewAxis;
    g_liveSprite.anchorOrigin = player->firstPersonViewOrigin + g_liveSprite.anchorAxis[0] * 96.0f;
    g_liveSprite.startTime = gameLocal.time;
    g_liveSprite.durationSec = durationSec;
    g_liveSprite.endTime = gameLocal.time + idMath::FtoiFast(durationSec * 1000.0f);

    memset(&g_liveSprite.renderEntity, 0, sizeof(g_liveSprite.renderEntity));
    g_liveSprite.renderEntity.hModel = model;
    g_liveSprite.renderEntity.origin = SampleOrigin(g_liveSprite, sample);
    g_liveSprite.renderEntity.axis = g_liveSprite.anchorAxis;
    g_liveSprite.renderEntity.noShadow = true;
    g_liveSprite.renderEntity.noSelfShadow = true;
    g_liveSprite.renderEntity.shaderParms[SHADERPARM_RED] = sample.tint.x;
    g_liveSprite.renderEntity.shaderParms[SHADERPARM_GREEN] = sample.tint.y;
    g_liveSprite.renderEntity.shaderParms[SHADERPARM_BLUE] = sample.tint.z;
    g_liveSprite.renderEntity.shaderParms[SHADERPARM_ALPHA] = sample.fade;
    g_liveSprite.renderEntity.shaderParms[SHADERPARM_TIMEOFFSET] = -MS2SEC(gameLocal.time);

    const qhandle_t handle = gameRenderWorld->AddEntityDef(&g_liveSprite.renderEntity);
    if (handle < 0) {
        renderModelManager->FreeModel(model);
        g_liveSprite.model = NULL;
        g_liveSprite.active = false;
        common->Warning("Q4BSE %s: AddEntityDef failed", milestoneLabel);
        return false;
    }

    g_liveSprite.entityHandle = handle;

    common->Printf(
        "Q4BSE %s PLAY: fx=%s segment=%s primitive=%s material=%s "
        "size=(%.2f %.2f) pos=(%.2f %.2f %.2f) duration=%.3f envelopes=%s\n",
        milestoneLabel, fx.name.c_str(), segment->name.c_str(), segment->particle.primitive.c_str(),
        segment->particle.material.c_str(), sample.size.x, sample.size.y,
        sample.position.x, sample.position.y, sample.position.z, durationSec,
        animateEnvelopes ? "live" : "static");

    return true;
}

static void PrintMotionDomain(const q4bse::ParticleTemplate& particle, const char* property) {
    const q4bse::Domain* d = q4bse::FindDomain(particle.motion, property);
    if (!d) {
        common->Printf("  motion %-6s: <none>\n", property);
        return;
    }

    common->Printf("  motion %-6s: type=%s envelope=%s offset=%s%.3f extraValues=%d\n",
                   property,
                   d->type.empty() ? "<empty>" : d->type.c_str(),
                   d->envelope.empty() ? "<linear/default>" : d->envelope.c_str(),
                   d->hasEnvelopeOffset ? "" : "<none>",
                   d->hasEnvelopeOffset ? d->envelopeOffset : 0.0f,
                   (int)d->values.size());
}

static void Cmd_Q4BSE_Status(const idCmdArgs& args) {
    common->Printf("Q4BSE source-integrated M2 status:\n");
    common->Printf("  initialized: %s\n", g_initialized ? "yes" : "no");
    common->Printf("  impact_default.fx: %s (%d segments)\n",
                   g_impactLoaded ? "parsed" : "not parsed",
                   g_impactLoaded ? (int)g_impact.segments.size() : 0);
    common->Printf("  fly.fx: %s (%d segments)\n",
                   g_flyLoaded ? "parsed" : "not parsed",
                   g_flyLoaded ? (int)g_fly.segments.size() : 0);
    common->Printf("  live sprite: %s%s\n",
                   g_liveSprite.active ? "yes" : "no",
                   g_liveSprite.active ? (g_liveSprite.animateEnvelopes ? " (M2 envelopes)" : " (M1 static)") : "");
    common->Printf("  cached Raven envelope tables: %d\n", (int)g_envelopeTables.size());
}

static void Cmd_Q4BSE_M1Flash(const idCmdArgs& args) {
    if (!g_impactLoaded) {
        common->Warning("Q4BSE M1: impact_default.fx is not loaded");
        return;
    }
    PlaySpriteSegment(g_impact, "impact_flash", false, "M1");
}

static void Cmd_Q4BSE_M2Probe(const idCmdArgs& args) {
    if (!g_impactLoaded) {
        common->Warning("Q4BSE M2: impact_default.fx is not loaded");
        return;
    }

    const q4bse::Segment* segment = q4bse::FindSegment(g_impact, "impact_flash");
    if (!segment || !segment->hasParticle || segment->particle.primitive != "sprite") {
        common->Warning("Q4BSE M2: impact_flash is not a parsed sprite");
        return;
    }

    common->Printf("Q4BSE M2 PROBE: %s / %s\n",
                   g_impact.name.c_str(), segment->name.c_str());
    PrintMotionDomain(segment->particle, "size");
    PrintMotionDomain(segment->particle, "fade");
    PrintMotionDomain(segment->particle, "tint");
    PrintMotionDomain(segment->particle, "rotate");

    static const float samples[] = { 0.0f, 0.25f, 0.50f, 0.75f, 1.0f };
    for (int i = 0; i < 5; ++i) {
        SpriteSample sample;
        std::string error;
        if (!EvaluateSpriteSample(g_impact, "impact_flash", samples[i], sample, error)) {
            common->Warning("Q4BSE M2 PROBE: t=%.2f failed: %s", samples[i], error.c_str());
            return;
        }

        common->Printf(
            "  t=%.2f size=(%.3f %.3f) fade=%.3f tint=(%.3f %.3f %.3f) rotate=%.3f\n",
            samples[i], sample.size.x, sample.size.y, sample.fade,
            sample.tint.x, sample.tint.y, sample.tint.z, sample.rotate);
    }

    common->Printf("Q4BSE M2 PROBE PASS: Raven envelope table execution resolved through Doom 3 decl text.\n");
}

static void Cmd_Q4BSE_M2Flash(const idCmdArgs& args) {
    if (!g_impactLoaded) {
        common->Warning("Q4BSE M2: impact_default.fx is not loaded");
        return;
    }
    PlaySpriteSegment(g_impact, "impact_flash", true, "M2");
}

} // anonymous namespace

void Q4BSE_Init(void) {
    if (g_initialized) return;
    g_initialized = true;

    cmdSystem->AddCommand("q4bse_status", Cmd_Q4BSE_Status, CMD_FL_GAME,
                          "prints source-integrated Q4 BSE status");
    cmdSystem->AddCommand("q4bse_m1_flash", Cmd_Q4BSE_M1Flash, CMD_FL_GAME,
                          "renders the parsed Raven impact_flash as the M1 static proof");
    cmdSystem->AddCommand("q4bse_m2_probe", Cmd_Q4BSE_M2Probe, CMD_FL_GAME,
                          "samples parsed Raven sprite motion envelopes at five lifetime points");
    cmdSystem->AddCommand("q4bse_m2_flash", Cmd_Q4BSE_M2Flash, CMD_FL_GAME,
                          "renders impact_flash with live Raven size/fade/tint envelopes");

    common->Printf("Q4BSE M2: source-integrated subsystem initialized (no wrapper DLL)\n");
}

void Q4BSE_Shutdown(void) {
    if (!g_initialized) return;

    Q4BSE_EndMap();

    cmdSystem->RemoveCommand("q4bse_status");
    cmdSystem->RemoveCommand("q4bse_m1_flash");
    cmdSystem->RemoveCommand("q4bse_m2_probe");
    cmdSystem->RemoveCommand("q4bse_m2_flash");

    g_initialized = false;
    common->Printf("Q4BSE M2: shutdown\n");
}

void Q4BSE_BeginMap(void) {
    FreeLiveSprite();
    ClearEnvelopeTables();

    g_impactLoaded = LoadQ4Fx("effects/weapons/hyperblaster/impact_default.fx", g_impact);
    g_flyLoaded = LoadQ4Fx("effects/weapons/hyperblaster/fly.fx", g_fly);

    if (g_impactLoaded && g_flyLoaded) {
        common->Printf("Q4BSE M2 READY: real Raven .fx files parsed by code compiled into gamex86.dll\n");
        common->Printf("Q4BSE M2 TEST: q4bse_m2_probe then q4bse_m2_flash\n");
    }
}

void Q4BSE_EndMap(void) {
    FreeLiveSprite();
    ClearEnvelopeTables();

    g_impactLoaded = false;
    g_flyLoaded = false;
    g_impact = q4bse::Effect();
    g_fly = q4bse::Effect();
}

void Q4BSE_Frame(int gameTimeMS) {
    if (!g_liveSprite.active) return;

    if (gameTimeMS >= g_liveSprite.endTime) {
        FreeLiveSprite();
        return;
    }

    if (!g_liveSprite.animateEnvelopes) {
        return;
    }

    const int durationMS = g_liveSprite.endTime - g_liveSprite.startTime;
    if (durationMS <= 0) {
        FreeLiveSprite();
        return;
    }

    float normalizedLife = (float)(gameTimeMS - g_liveSprite.startTime) / (float)durationMS;
    if (normalizedLife < 0.0f) normalizedLife = 0.0f;
    if (normalizedLife > 1.0f) normalizedLife = 1.0f;

    if (!UpdateLiveSpriteVisual(normalizedLife, true)) {
        FreeLiveSprite();
    }
}
