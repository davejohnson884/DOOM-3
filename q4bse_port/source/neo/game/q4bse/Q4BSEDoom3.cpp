#include "../../idlib/precompiled.h"
#pragma hdrstop

#include "../Game_local.h"
#include "Q4FxParser.h"
#include "Q4BSECore.h"
#include "Q4BSEDoom3.h"

#include <string>
#include <stdexcept>
#include <string.h>

namespace {

struct M1SpriteInstance {
    bool active;
    qhandle_t entityHandle;
    idRenderModel* model;
    int startTime;
    int endTime;

    M1SpriteInstance()
        : active(false), entityHandle(-1), model(NULL), startTime(0), endTime(0) {}
};

static bool g_initialized = false;
static bool g_impactLoaded = false;
static bool g_flyLoaded = false;
static q4bse::Effect g_impact;
static q4bse::Effect g_fly;
static M1SpriteInstance g_m1Sprite;

static bool LoadQ4Fx(const char* path, q4bse::Effect& out) {
    void* buffer = NULL;
    const int len = fileSystem->ReadFile(path, &buffer, NULL);
    if (len < 0 || buffer == NULL) {
        common->Warning("Q4BSE M1: VFS could not read %s", path);
        return false;
    }

    bool ok = false;
    try {
        q4bse::Parser parser;
        out = parser.Parse(std::string((const char*)buffer, (size_t)len), path);
        common->Printf("Q4BSE M1: parsed %s (%d bytes, %d segments)\n",
                       path, len, (int)out.segments.size());
        ok = true;
    }
    catch (const std::exception& e) {
        common->Warning("Q4BSE M1: parse failure %s: %s", path, e.what());
    }
    catch (...) {
        common->Warning("Q4BSE M1: parse failure %s: unknown exception", path);
    }

    fileSystem->FreeFile(buffer);
    return ok;
}

static void FreeM1Sprite(void) {
    if (!g_m1Sprite.active && !g_m1Sprite.model) return;

    if (gameRenderWorld && g_m1Sprite.entityHandle >= 0) {
        gameRenderWorld->FreeEntityDef(g_m1Sprite.entityHandle);
    }
    g_m1Sprite.entityHandle = -1;

    if (g_m1Sprite.model && renderModelManager) {
        renderModelManager->FreeModel(g_m1Sprite.model);
    }
    g_m1Sprite.model = NULL;
    g_m1Sprite.active = false;
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

static idRenderModel* BuildSpriteModel(const char* materialName, float widthRadius, float heightRadius) {
    if (!renderModelManager || !declManager) return NULL;

    const idMaterial* material = declManager->FindMaterial(materialName, false);
    if (!material) {
        common->Warning("Q4BSE M1: material not found: %s", materialName);
        return NULL;
    }

    idRenderModel* model = renderModelManager->AllocModel();
    if (!model) return NULL;
    model->InitEmpty("_q4bse_m1_sprite");

    srfTriangles_t* tri = model->AllocSurfaceTriangles(4, 6);
    if (!tri || !tri->verts || !tri->indexes) {
        renderModelManager->FreeModel(model);
        return NULL;
    }

    // Raven rvSpriteParticle uses size values as radii: +/- right and +/- up.
    // Local X is the sprite normal; Y/Z span the quad.
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
    return model;
}

static void PlayM1ImpactFlash(void) {
    if (!g_impactLoaded) {
        common->Warning("Q4BSE M1: impact_default.fx is not loaded");
        return;
    }
    if (!gameRenderWorld) {
        common->Warning("Q4BSE M1: no gameRenderWorld (load a map first)");
        return;
    }

    idPlayer* player = gameLocal.GetLocalPlayer();
    if (!player) {
        common->Warning("Q4BSE M1: no local player");
        return;
    }

    const q4bse::Segment* segment = q4bse::FindSegment(g_impact, "impact_flash");
    if (!segment || !segment->hasParticle) {
        common->Warning("Q4BSE M1: parsed effect has no impact_flash particle");
        return;
    }

    q4bse::SpawnProbe probe;
    std::string error;
    if (!q4bse::BuildSpriteSpawnProbe(g_impact, "impact_flash", probe, error)) {
        common->Warning("Q4BSE M1: cannot build parsed sprite probe: %s", error.c_str());
        return;
    }

    float durationSec = 0.0f;
    if (!q4bse::GetParticleDuration(g_impact, "impact_flash", durationSec)) {
        common->Warning("Q4BSE M1: impact_flash has no parsed duration");
        return;
    }

    FreeM1Sprite();

    idRenderModel* model = BuildSpriteModel(segment->particle.material.c_str(), probe.size.x, probe.size.y);
    if (!model) {
        common->Warning("Q4BSE M1: failed to build render model for material %s",
                        segment->particle.material.c_str());
        return;
    }

    // The M1 command places a real parsed Raven segment in front of the player.
    // This is a renderer/API feasibility proof, not the final collision-normal path.
    const idMat3 axis = player->firstPersonViewAxis;
    idVec3 origin = player->firstPersonViewOrigin + axis[0] * 96.0f;
    origin += axis[0] * probe.position.x + axis[1] * probe.position.y + axis[2] * probe.position.z;

    renderEntity_t re;
    memset(&re, 0, sizeof(re));
    re.hModel = model;
    re.origin = origin;
    re.axis = axis;
    re.noShadow = true;
    re.noSelfShadow = true;
    re.shaderParms[SHADERPARM_RED] = 1.0f;
    re.shaderParms[SHADERPARM_GREEN] = 1.0f;
    re.shaderParms[SHADERPARM_BLUE] = 1.0f;
    re.shaderParms[SHADERPARM_ALPHA] = probe.fade;
    re.shaderParms[SHADERPARM_TIMEOFFSET] = -MS2SEC(gameLocal.time);

    const qhandle_t handle = gameRenderWorld->AddEntityDef(&re);
    if (handle < 0) {
        renderModelManager->FreeModel(model);
        common->Warning("Q4BSE M1: AddEntityDef failed");
        return;
    }

    g_m1Sprite.active = true;
    g_m1Sprite.entityHandle = handle;
    g_m1Sprite.model = model;
    g_m1Sprite.startTime = gameLocal.time;
    g_m1Sprite.endTime = gameLocal.time + idMath::FtoiFast(durationSec * 1000.0f);

    common->Printf(
        "Q4BSE M1 PLAY: fx=%s segment=%s primitive=%s material=%s size=(%.2f %.2f) pos=(%.2f %.2f %.2f) duration=%.3f\n",
        g_impact.name.c_str(), segment->name.c_str(), segment->particle.primitive.c_str(),
        segment->particle.material.c_str(), probe.size.x, probe.size.y,
        probe.position.x, probe.position.y, probe.position.z, durationSec);
    common->Printf("Q4BSE M1 NOTE: exp_x2 envelope execution is intentionally NOT claimed yet.\n");
}

static void Cmd_Q4BSE_Status(const idCmdArgs& args) {
    common->Printf("Q4BSE source-integrated M1 status:\n");
    common->Printf("  initialized: %s\n", g_initialized ? "yes" : "no");
    common->Printf("  impact_default.fx: %s (%d segments)\n",
                   g_impactLoaded ? "parsed" : "not parsed", g_impactLoaded ? (int)g_impact.segments.size() : 0);
    common->Printf("  fly.fx: %s (%d segments)\n",
                   g_flyLoaded ? "parsed" : "not parsed", g_flyLoaded ? (int)g_fly.segments.size() : 0);
    common->Printf("  live M1 sprite: %s\n", g_m1Sprite.active ? "yes" : "no");
}

static void Cmd_Q4BSE_M1Flash(const idCmdArgs& args) {
    PlayM1ImpactFlash();
}

} // anonymous namespace

void Q4BSE_Init(void) {
    if (g_initialized) return;
    g_initialized = true;

    cmdSystem->AddCommand("q4bse_status", Cmd_Q4BSE_Status, CMD_FL_GAME,
                          "prints source-integrated Q4 BSE M1 status");
    cmdSystem->AddCommand("q4bse_m1_flash", Cmd_Q4BSE_M1Flash, CMD_FL_GAME,
                          "renders the parsed Raven HyperBlaster impact_flash segment in front of the player");

    common->Printf("Q4BSE M1: source-integrated subsystem initialized (no wrapper DLL)\n");
}

void Q4BSE_Shutdown(void) {
    if (!g_initialized) return;
    Q4BSE_EndMap();
    cmdSystem->RemoveCommand("q4bse_status");
    cmdSystem->RemoveCommand("q4bse_m1_flash");
    g_initialized = false;
    common->Printf("Q4BSE M1: shutdown\n");
}

void Q4BSE_BeginMap(void) {
    FreeM1Sprite();
    g_impactLoaded = LoadQ4Fx("effects/weapons/hyperblaster/impact_default.fx", g_impact);
    g_flyLoaded = LoadQ4Fx("effects/weapons/hyperblaster/fly.fx", g_fly);

    if (g_impactLoaded && g_flyLoaded) {
        common->Printf("Q4BSE M1 READY: real Raven .fx files parsed by code compiled into gamex86.dll\n");
        common->Printf("Q4BSE M1 TEST: type q4bse_m1_flash in the console\n");
    }
}

void Q4BSE_EndMap(void) {
    FreeM1Sprite();
    g_impactLoaded = false;
    g_flyLoaded = false;
    g_impact = q4bse::Effect();
    g_fly = q4bse::Effect();
}

void Q4BSE_Frame(int gameTimeMS) {
    if (g_m1Sprite.active && gameTimeMS >= g_m1Sprite.endTime) {
        FreeM1Sprite();
    }
}
