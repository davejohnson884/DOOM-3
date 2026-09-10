#ifndef __Q4BSE_CORE_H__
#define __Q4BSE_CORE_H__

#include "Q4FxParser.h"
#include <string>

namespace q4bse {

// Portable, renderer-independent helpers.  This layer intentionally contains
// no Doom 3 or Phrozo types.  It is the beginning of the BSE runtime proper.

struct Vec3 {
    float x, y, z;
    Vec3() : x(0), y(0), z(0) {}
    Vec3(float X, float Y, float Z) : x(X), y(Y), z(Z) {}
};

struct Vec2 {
    float x, y;
    Vec2() : x(0), y(0) {}
    Vec2(float X, float Y) : x(X), y(Y) {}
};

struct SpawnProbe {
    Vec3 position;
    Vec2 size;
    float fade;
    float rotate;
    SpawnProbe() : size(1,1), fade(1.0f), rotate(0.0f) {}
};

const Domain* FindDomain(const std::vector< std::pair<std::string, Domain> >& block,
                         const char* property);

// Evaluates only deterministic POINT domains.  This is sufficient for the
// M1 impact_flash proof, and deliberately refuses to pretend the remaining
// Raven domain types are implemented yet.
bool EvalPoint1(const Domain* d, float& out);
bool EvalPoint2(const Domain* d, Vec2& out);
bool EvalPoint3(const Domain* d, Vec3& out);

// Build the initial data for a sprite from the parsed Raven template.  No
// HyperBlaster values are hard-coded: the function consumes the parsed start
// block.  The effect/segment name is supplied only to select a diagnostic
// segment for M1.
bool BuildSpriteSpawnProbe(const Effect& fx, const char* segmentName,
                           SpawnProbe& out, std::string& error);

// Returns the particle duration in seconds if the named segment has one.
bool GetParticleDuration(const Effect& fx, const char* segmentName, float& seconds);

} // namespace q4bse

#endif
