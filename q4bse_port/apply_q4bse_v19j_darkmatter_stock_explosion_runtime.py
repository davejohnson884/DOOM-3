#!/usr/bin/env python3
'''V19J / user-facing V45: exact Raven Dark Matter explosion runtime parity.

Runs after V19H and intentionally replaces the experimental V19I detonation
step.  The stock Quake 4 DMG content uses two separate effects:
  fx_impact   -> impact_default_mp.fx (surface/world impact)
  fx_detonate -> impact_default.fx    (air/fuse detonation)

The exact retail effect files are much heavier than the earlier approximation
and depend on Raven BSE fade/envelope semantics.  This patch teaches our BSE
bridge those semantics only for the two stock DMG explosion paths so the
already-accepted core/projectile effects are not regressed.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
CPP = ROOT / 'neo' / 'game' / 'q4bse' / 'Q4BSEImpactM3.cpp'
if not CPP.exists():
    raise SystemExit(f'ERROR: missing {CPP}')

text = CPP.read_text(encoding='utf-8-sig')

def replace_once(old, new, label):
    global text
    hits = text.count(old)
    if hits != 1:
        raise SystemExit(f'ERROR: V19J expected exactly one {label}, found {hits}')
    text = text.replace(old, new, 1)

# Retail impact_default_mp has 50 sparks + 6 fire + 70 + 70 + 70 sphere
# particles = 266 simultaneous spawner particles.  128 silently truncated most
# of the defining Dark Matter sphere layers.
replace_once(
    'static const int M3_MAX_PARTICLES = 128;',
    'static const int M3_MAX_PARTICLES = 512;',
    'particle pool limit')

# Add path-scoped helpers immediately after the current-impact macro.
anchor = '#define g_m3Impact (*g_m3CurrentImpact)\n'
helper = r'''#define g_m3Impact (*g_m3CurrentImpact)

static bool IsQ4DMGStockExplosion(void) {
    if (!g_m3CurrentImpact) return false;
    const char* path = g_m3Impact.effectPath.c_str();
    return !idStr::Icmp(path, "effects/weapons/dmg/impact_default.fx") ||
           !idStr::Icmp(path, "effects/weapons/dmg/impact_default_mp.fx");
}

'''
replace_once(anchor, helper, 'current-impact macro')

# Built-in equivalents for the small set of Raven envelope names used by the
# retail DMG explosion.  This avoids falling back to linear when Doom 3 does
# not have the Quake 4 table declarations loaded.
old_env = r'''static float EnvelopeWeight(const q4bse::Domain* motion, float normalizedLife) {
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
'''
new_env = r'''static float EnvelopeWeight(const q4bse::Domain* motion, float normalizedLife) {
    float lookup = normalizedLife;
    if (!motion) return lookup;
    if (motion->hasEnvelopeOffset) lookup += motion->envelopeOffset;
    lookup = Clamp01(lookup);
    if (motion->envelope.empty() || !idStr::Icmp(motion->envelope.c_str(), "linear")) return lookup;

    // Exact-stock DMG explosion compatibility.  These are the standard Raven
    // BSE curve families used by impact_default(.fx/_mp.fx).  Keeping them
    // path-agnostic is safe because they are just named envelope definitions.
    const char* env = motion->envelope.c_str();
    if (!idStr::Icmp(env, "convexfade")) {
        return idMath::Sin(lookup * idMath::HALF_PI);
    }
    if (!idStr::Icmp(env, "cosine")) {
        return 0.5f - 0.5f * idMath::Cos(lookup * idMath::PI);
    }
    if (!idStr::Icmp(env, "exp_x2")) {
        return lookup * lookup;
    }
    if (!idStr::Icmp(env, "halflinear")) {
        // Raven's half-linear family is used here only as an ease-in growth
        // curve for the long-lived fire sprites.
        return 0.5f * lookup + 0.5f * lookup * lookup;
    }
    if (!idStr::Icmp(env, "fastinslowout") ||
        !idStr::Icmp(env, "fast_in_slow_out")) {
        // Fast initial response with a soft approach to the endpoint.
        const float oneMinus = 1.0f - lookup;
        return 1.0f - oneMinus * oneMinus;
    }

    std::string error;
    M3EnvelopeTable* table = FindEnvelopeTable(env, error);
    if (!table) {
        static bool warned = false;
        if (!warned) { common->Warning("Q4BSE M3: %s; falling back to linear", error.c_str()); warned = true; }
        return lookup;
    }
    return TableLookup(*table, lookup);
}
'''
replace_once(old_env, new_env, 'EnvelopeWeight function')

# Raven BSE `fade` is fade-AMOUNT: 0 = fully visible, 1 = fully faded.
# Our bridge historically used it as direct alpha because the custom ported
# effects were authored around that behavior.  Use native semantics only for
# the two newly restored stock DMG explosion files.
old_defaults = '    p.fadeStart = 1.0f; p.fadeEnd = 0.0f;\n'
new_defaults = '''    if (IsQ4DMGStockExplosion()) {
        p.fadeStart = 0.0f;
        p.fadeEnd = 1.0f;
    } else {
        p.fadeStart = 1.0f;
        p.fadeEnd = 0.0f;
    }
'''
replace_once(old_defaults, new_defaults, 'particle fade defaults')

old_state = r'''    const idVec3 tint = EvalVec3(p.tintStart, p.tintEnd, FindDomain(pt.motion, "tint"), life);
    const float fade = EvalFloat(p.fadeStart, p.fadeEnd, FindDomain(pt.motion, "fade"), life);
    if (fade <= 0.0f) return false;
    color.Set(tint.x, tint.y, tint.z, fade);
'''
new_state = r'''    const idVec3 tint = EvalVec3(p.tintStart, p.tintEnd, FindDomain(pt.motion, "tint"), life);
    const float fadeValue = EvalFloat(p.fadeStart, p.fadeEnd, FindDomain(pt.motion, "fade"), life);
    const float alpha = IsQ4DMGStockExplosion() ? (1.0f - fadeValue) : fadeValue;
    if (alpha <= 0.0f) return false;
    color.Set(tint.x, tint.y, tint.z, alpha);
'''
replace_once(old_state, new_state, 'Q4ParticleRenderState fade semantics')

old_render = r'''    const idVec3 tint = EvalVec3(p.tintStart, p.tintEnd, FindDomain(pt.motion, "tint"), life);
    const float fade = EvalFloat(p.fadeStart, p.fadeEnd, FindDomain(pt.motion, "fade"), life);
    if (fade <= 0.0f) return false;
    const idVec4 color(tint.x, tint.y, tint.z, fade);
'''
new_render = r'''    const idVec3 tint = EvalVec3(p.tintStart, p.tintEnd, FindDomain(pt.motion, "tint"), life);
    const float fadeValue = EvalFloat(p.fadeStart, p.fadeEnd, FindDomain(pt.motion, "fade"), life);
    const float alpha = IsQ4DMGStockExplosion() ? (1.0f - fadeValue) : fadeValue;
    if (alpha <= 0.0f) return false;
    const idVec4 color(tint.x, tint.y, tint.z, alpha);
'''
replace_once(old_render, new_render, 'RenderParticle fade semantics')

# The wall explosion is large and can temporarily have hundreds of surfaces.
# Reserve enough vector capacity when starting the two stock DMG explosion
# paths to avoid needless reallocations during the burst.
old_start = r'''static void StartAllSegments(void) {
    if (!g_m3CurrentImpact || !g_m3Impact.effect) return;
    g_m3Impact.emitters.clear();
'''
new_start = r'''static void StartAllSegments(void) {
    if (!g_m3CurrentImpact || !g_m3Impact.effect) return;
    if (IsQ4DMGStockExplosion()) {
        g_m3Impact.particles.reserve(320);
    }
    g_m3Impact.emitters.clear();
'''
replace_once(old_start, new_start, 'StartAllSegments reserve')

for required in (
    'M3_MAX_PARTICLES = 512',
    'IsQ4DMGStockExplosion',
    'impact_default_mp.fx',
    'impact_default.fx',
    'convexfade',
    'fast_in_slow_out',
    '1.0f - fadeValue',
    'particles.reserve(320)',
):
    if required not in text:
        raise SystemExit(f'ERROR: V19J verification missing {required}')

CPP.write_text(text, encoding='utf-8')
print('Q4BSE V19J EXACT STOCK DMG EXPLOSION RUNTIME PARITY.')
print('  - 512-particle runtime pool for Raven wall explosion')
print('  - stock Raven fade semantics scoped to DMG impact_default effects')
print('  - built-in Raven explosion envelope families')
print('  - accepted core/fly custom effects keep their existing alpha semantics')
