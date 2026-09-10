#ifndef __Q4FXPARSER_H__
#define __Q4FXPARSER_H__

#include <string>
#include <vector>
#include <utility>

namespace q4bse {

struct Range {
    float min;
    float max;
    bool valid;
    Range() : min(0.0f), max(0.0f), valid(false) {}
};

struct Domain {
    std::string type;
    std::vector<float> values;
    bool surface;
    bool relative;
    std::string envelope;
    bool hasEnvelopeOffset;
    float envelopeOffset;
    Domain() : surface(false), relative(false), hasEnvelopeOffset(false), envelopeOffset(0.0f) {}
};

struct ParticleTemplate {
    std::string primitive;
    Range duration;
    Range gravity;
    std::string blend;
    std::string material;
    bool generatedNormal;
    bool generatedOriginNormal;
    bool flipNormal;
    std::vector< std::pair<std::string, Domain> > start;
    std::vector< std::pair<std::string, Domain> > motion;
    std::vector< std::pair<std::string, Domain> > end;
    ParticleTemplate() : generatedNormal(false), generatedOriginNormal(false), flipNormal(false) {}
};

struct Segment {
    std::string type;
    std::string name;
    Range count;
    Range duration;
    float detail;
    bool locked;
    bool constant;
    std::string soundShader;
    bool hasParticle;
    ParticleTemplate particle;
    Segment() : detail(1.0f), locked(false), constant(false), hasParticle(false) {}
};

struct Effect {
    std::string name;
    float size;
    float cutOffDistance;
    std::vector<Segment> segments;
    Effect() : size(512.0f), cutOffDistance(0.0f) {}
};

class Parser {
public:
    Effect Parse(const std::string& text, const std::string& sourceName);
    Effect Parse(const std::string& text) { return Parse(text, "<memory>"); }
};

std::string DumpEffect(const Effect& fx);
const Segment* FindSegment(const Effect& fx, const char* name);

} // namespace q4bse

#endif
