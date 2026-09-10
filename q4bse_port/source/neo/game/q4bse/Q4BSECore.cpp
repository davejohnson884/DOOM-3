#include "Q4BSECore.h"
#include <sstream>

namespace q4bse {

const Domain* FindDomain(const std::vector< std::pair<std::string, Domain> >& block,
                         const char* property) {
    if (property == NULL) return NULL;
    for (size_t i = 0; i < block.size(); ++i) {
        if (block[i].first == property) return &block[i].second;
    }
    return NULL;
}

bool EvalPoint1(const Domain* d, float& out) {
    if (!d || d->type != "point" || d->values.empty()) return false;
    out = d->values[0];
    return true;
}

bool EvalPoint2(const Domain* d, Vec2& out) {
    if (!d || d->type != "point" || d->values.empty()) return false;
    out.x = d->values[0];
    out.y = d->values.size() >= 2 ? d->values[1] : d->values[0];
    return true;
}

bool EvalPoint3(const Domain* d, Vec3& out) {
    if (!d || d->type != "point" || d->values.empty()) return false;
    out.x = d->values[0];
    out.y = d->values.size() >= 2 ? d->values[1] : 0.0f;
    out.z = d->values.size() >= 3 ? d->values[2] : 0.0f;
    return true;
}

bool BuildSpriteSpawnProbe(const Effect& fx, const char* segmentName,
                           SpawnProbe& out, std::string& error) {
    const Segment* s = FindSegment(fx, segmentName);
    if (!s) {
        error = std::string("segment not found: ") + (segmentName ? segmentName : "<null>");
        return false;
    }
    if (!s->hasParticle || s->particle.primitive != "sprite") {
        error = "selected segment is not a sprite particle";
        return false;
    }

    const Domain* position = FindDomain(s->particle.start, "position");
    const Domain* size = FindDomain(s->particle.start, "size");
    const Domain* fade = FindDomain(s->particle.start, "fade");
    const Domain* rotate = FindDomain(s->particle.start, "rotate");

    if (position && !EvalPoint3(position, out.position)) {
        error = "M1 requires deterministic point position for the probe";
        return false;
    }
    if (size && !EvalPoint2(size, out.size)) {
        error = "M1 requires deterministic point size for the probe";
        return false;
    }
    if (fade && !EvalPoint1(fade, out.fade)) {
        error = "M1 requires deterministic point fade for the probe";
        return false;
    }
    if (rotate && rotate->type == "point") {
        if (!EvalPoint1(rotate, out.rotate)) {
            error = "invalid point rotate domain";
            return false;
        }
    }

    return true;
}

bool GetParticleDuration(const Effect& fx, const char* segmentName, float& seconds) {
    const Segment* s = FindSegment(fx, segmentName);
    if (!s || !s->hasParticle || !s->particle.duration.valid) return false;
    // M1 uses the minimum.  Full BSE will select within the authored range
    // using Raven-compatible random semantics.
    seconds = s->particle.duration.min;
    return true;
}

} // namespace q4bse
