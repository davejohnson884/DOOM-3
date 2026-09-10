#include "Q4FxParser.h"
#include <cctype>
#include <cstdlib>
#include <sstream>
#include <stdexcept>

namespace q4bse {
namespace {

struct TokenStream {
    std::vector<std::string> t;
    size_t p;
    std::string source;
    TokenStream(const std::vector<std::string>& tokens, const std::string& sourceName)
        : t(tokens), p(0), source(sourceName) {}
    bool eof() const { return p >= t.size(); }
    const std::string& peek() const {
        if (eof()) throw std::runtime_error("unexpected EOF in " + source);
        return t[p];
    }
    std::string get() {
        std::string s = peek();
        ++p;
        return s;
    }
    bool accept(const char* s) {
        if (!eof() && t[p] == s) { ++p; return true; }
        return false;
    }
    void expect(const char* s) {
        if (!accept(s)) {
            throw std::runtime_error("expected '" + std::string(s) + "' but got '" +
                (eof() ? std::string("<EOF>") : t[p]) + "' in " + source);
        }
    }
};

static bool IsNum(const std::string& s) {
    if (s.empty()) return false;
    char* e = NULL;
    std::strtod(s.c_str(), &e);
    return e != NULL && *e == '\0';
}

static float ToFloat(const std::string& s) {
    char* e = NULL;
    double v = std::strtod(s.c_str(), &e);
    if (e == NULL || *e != '\0') throw std::runtime_error("expected float, got '" + s + "'");
    return (float)v;
}

static std::vector<std::string> Lex(const std::string& s) {
    std::vector<std::string> out;
    size_t i = 0;
    while (i < s.size()) {
        unsigned char c = (unsigned char)s[i];
        if (std::isspace(c)) { ++i; continue; }
        if (s[i] == '/' && i + 1 < s.size() && s[i + 1] == '/') {
            i += 2;
            while (i < s.size() && s[i] != '\n') ++i;
            continue;
        }
        if (s[i] == '/' && i + 1 < s.size() && s[i + 1] == '*') {
            i += 2;
            while (i + 1 < s.size() && !(s[i] == '*' && s[i + 1] == '/')) ++i;
            if (i + 1 < s.size()) i += 2;
            continue;
        }
        if (s[i] == '"') {
            ++i;
            std::string q;
            while (i < s.size() && s[i] != '"') {
                if (s[i] == '\\' && i + 1 < s.size()) {
                    q.push_back(s[i + 1]);
                    i += 2;
                } else {
                    q.push_back(s[i]);
                    ++i;
                }
            }
            if (i >= s.size()) throw std::runtime_error("unterminated quote");
            ++i;
            out.push_back(q);
            continue;
        }
        if (s[i] == '{' || s[i] == '}' || s[i] == ',') {
            out.push_back(std::string(1, s[i]));
            ++i;
            continue;
        }
        size_t b = i;
        while (i < s.size()) {
            char ch = s[i];
            if (std::isspace((unsigned char)ch) || ch == '{' || ch == '}' || ch == ',' || ch == '"') break;
            if (ch == '/' && i + 1 < s.size() && (s[i + 1] == '/' || s[i + 1] == '*')) break;
            ++i;
        }
        out.push_back(s.substr(b, i - b));
    }
    return out;
}

static Range ParseRange(TokenStream& ts) {
    Range r;
    r.min = ToFloat(ts.get());
    if (ts.accept(",")) r.max = ToFloat(ts.get()); else r.max = r.min;
    r.valid = true;
    return r;
}

static Domain ParseDomain(TokenStream& ts) {
    Domain d;
    ts.expect("{");
    d.type = ts.get();
    if (d.type == "envelope") {
        d.envelope = ts.get();
        if (!ts.eof() && ts.peek() == "offset") {
            ts.get();
            d.hasEnvelopeOffset = true;
            d.envelopeOffset = ToFloat(ts.get());
        }
    }
    while (!ts.eof() && ts.peek() != "}") {
        if (ts.peek() == "surface") { ts.get(); d.surface = true; continue; }
        if (ts.peek() == "relative") { ts.get(); d.relative = true; continue; }
        if (ts.peek() == "envelope") {
            ts.get();
            d.envelope = ts.get();
            if (!ts.eof() && ts.peek() == "offset") {
                ts.get();
                d.hasEnvelopeOffset = true;
                d.envelopeOffset = ToFloat(ts.get());
            }
            continue;
        }
        if (ts.accept(",")) continue;
        if (IsNum(ts.peek())) { d.values.push_back(ToFloat(ts.get())); continue; }
        throw std::runtime_error("unsupported domain token '" + ts.peek() + "'");
    }
    ts.expect("}");
    return d;
}

static void ParseDomainBlock(TokenStream& ts, std::vector< std::pair<std::string, Domain> >& dst) {
    ts.expect("{");
    while (!ts.accept("}")) {
        std::string property = ts.get();
        dst.push_back(std::make_pair(property, ParseDomain(ts)));
    }
}

static ParticleTemplate ParseParticle(TokenStream& ts, const std::string& primitive) {
    ParticleTemplate p;
    p.primitive = primitive;
    ts.expect("{");
    while (!ts.accept("}")) {
        std::string k = ts.get();
        if (k == "duration") p.duration = ParseRange(ts);
        else if (k == "gravity") p.gravity = ParseRange(ts);
        else if (k == "blend") p.blend = ts.get();
        else if (k == "material") p.material = ts.get();
        else if (k == "generatedNormal") p.generatedNormal = true;
        else if (k == "generatedOriginNormal") p.generatedOriginNormal = true;
        else if (k == "flipNormal") p.flipNormal = true;
        else if (k == "start") ParseDomainBlock(ts, p.start);
        else if (k == "motion") ParseDomainBlock(ts, p.motion);
        else if (k == "end") ParseDomainBlock(ts, p.end);
        else throw std::runtime_error("unsupported particle keyword '" + k + "'");
    }
    return p;
}

static bool IsPrimitive(const std::string& s) {
    return s == "sprite" || s == "line" || s == "oriented" || s == "decal" || s == "model" || s == "trail";
}

static Segment ParseSegment(TokenStream& ts, const std::string& type) {
    Segment s;
    s.type = type;
    s.name = ts.get();
    ts.expect("{");
    while (!ts.accept("}")) {
        std::string k = ts.get();
        if (k == "count") s.count = ParseRange(ts);
        else if (k == "duration") s.duration = ParseRange(ts);
        else if (k == "detail") s.detail = ToFloat(ts.get());
        else if (k == "locked") s.locked = true;
        else if (k == "constant") s.constant = true;
        else if (k == "soundShader") s.soundShader = ts.get();
        else if (IsPrimitive(k)) {
            s.particle = ParseParticle(ts, k);
            s.hasParticle = true;
        } else {
            throw std::runtime_error("unsupported segment keyword '" + k + "' in segment '" + s.name + "'");
        }
    }
    return s;
}

static std::string RangeStr(const Range& r) {
    if (!r.valid) return "-";
    std::ostringstream os;
    os << r.min << ".." << r.max;
    return os.str();
}

static std::string DomainStr(const Domain& d) {
    std::ostringstream os;
    os << d.type << "(";
    for (size_t i = 0; i < d.values.size(); ++i) {
        if (i) os << ",";
        os << d.values[i];
    }
    os << ")";
    if (d.surface) os << " surface";
    if (d.relative) os << " relative";
    if (!d.envelope.empty()) {
        os << " envelope=" << d.envelope;
        if (d.hasEnvelopeOffset) os << " offset=" << d.envelopeOffset;
    }
    return os.str();
}

static void DumpDomainBlock(std::ostringstream& os, const char* name,
                            const std::vector< std::pair<std::string, Domain> >& b) {
    if (b.empty()) return;
    os << "    " << name << ":\n";
    for (size_t i = 0; i < b.size(); ++i) {
        os << "      " << b[i].first << " = " << DomainStr(b[i].second) << "\n";
    }
}

} // anonymous namespace

Effect Parser::Parse(const std::string& text, const std::string& sourceName) {
    TokenStream ts(Lex(text), sourceName);
    if (ts.get() != "effect") throw std::runtime_error("file does not start with 'effect'");
    Effect e;
    e.name = ts.get();
    ts.expect("{");
    while (!ts.accept("}")) {
        std::string k = ts.get();
        if (k == "size") e.size = ToFloat(ts.get());
        else if (k == "cutOffDistance") e.cutOffDistance = ToFloat(ts.get());
        else if (k == "spawner" || k == "emitter" || k == "sound" || k == "decal" ||
                 k == "effect" || k == "trail" || k == "light" || k == "delay") {
            e.segments.push_back(ParseSegment(ts, k));
        } else {
            throw std::runtime_error("unsupported effect-level keyword '" + k + "'");
        }
    }
    if (!ts.eof()) throw std::runtime_error("unexpected trailing tokens");
    return e;
}

std::string DumpEffect(const Effect& fx) {
    std::ostringstream os;
    os << "EFFECT " << fx.name << "\n";
    os << "size=" << fx.size << " cutoff=" << fx.cutOffDistance << "\n";
    os << "segments=" << fx.segments.size() << "\n";
    for (size_t i = 0; i < fx.segments.size(); ++i) {
        const Segment& s = fx.segments[i];
        os << "[" << i << "] " << s.type << " \"" << s.name << "\"";
        if (s.count.valid) os << " count=" << RangeStr(s.count);
        if (s.duration.valid) os << " duration=" << RangeStr(s.duration);
        if (s.detail != 1.0f) os << " detail=" << s.detail;
        if (s.locked) os << " locked";
        if (s.constant) os << " constant";
        if (!s.soundShader.empty()) os << " soundShader=" << s.soundShader;
        os << "\n";
        if (s.hasParticle) {
            const ParticleTemplate& p = s.particle;
            os << "    primitive=" << p.primitive << " duration=" << RangeStr(p.duration);
            if (!p.blend.empty()) os << " blend=" << p.blend;
            if (!p.material.empty()) os << " material=" << p.material;
            if (p.gravity.valid) os << " gravity=" << RangeStr(p.gravity);
            if (p.generatedNormal) os << " generatedNormal";
            if (p.generatedOriginNormal) os << " generatedOriginNormal";
            if (p.flipNormal) os << " flipNormal";
            os << "\n";
            DumpDomainBlock(os, "start", p.start);
            DumpDomainBlock(os, "motion", p.motion);
            DumpDomainBlock(os, "end", p.end);
        }
    }
    return os.str();
}

const Segment* FindSegment(const Effect& fx, const char* name) {
    if (name == NULL) return NULL;
    for (size_t i = 0; i < fx.segments.size(); ++i) {
        if (fx.segments[i].name == name) return &fx.segments[i];
    }
    return NULL;
}

} // namespace q4bse
