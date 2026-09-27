#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
weapon_cpp = root / "neo" / "game" / "Weapon.cpp"
bse_cpp = root / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"V19S: {label} anchor not found")
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# 1) Raven's fx_crawl is a client effect attached to the struck actor. V19N
#    accidentally spawned it at a fixed world-space trace point, which leaves
#    the bright electricity/smoke card floating in mid-air after the actor
#    moves/falls. Keep the one-shot BSE lifetime, but bind its transform to the
#    actor so it follows the target instead of becoming a world-space ghost.
# ---------------------------------------------------------------------------
text = weapon_cpp.read_text(encoding="utf-8")
old = '''\t\t\t\tconst int nextCrawl = spawnArgs.GetInt( "_q4_lg_next_crawl", "0" );\n\t\t\t\tif ( gameLocal.time >= nextCrawl && hitEnt->IsType( idActor::Type ) ) {\n\t\t\t\t\tconst char *crawlFx = weaponDef->dict.GetString( "fx_crawl" );\n\t\t\t\t\tif ( crawlFx && crawlFx[0] ) Q4BSE_PlayEffectAxis( crawlFx, tr.endpos, tr.c.normal.ToMat3() );\n\t\t\t\t\tspawnArgs.Set( "_q4_lg_next_crawl", va( "%d", gameLocal.time + 300 ) );\n\t\t\t\t}\n'''
new = '''\t\t\t\tconst int nextCrawl = spawnArgs.GetInt( "_q4_lg_next_crawl", "0" );\n\t\t\t\tif ( gameLocal.time >= nextCrawl && hitEnt->IsType( idActor::Type ) ) {\n\t\t\t\t\tconst char *crawlFx = weaponDef->dict.GetString( "fx_crawl" );\n\t\t\t\t\tif ( crawlFx && crawlFx[0] ) {\n\t\t\t\t\t\tidVec3 crawlNormal = tr.c.normal;\n\t\t\t\t\t\tif ( crawlNormal.Normalize() < 0.001f ) crawlNormal = -beamDir;\n\t\t\t\t\t\t// Raven uses rvClientCrawlEffect bound to the actor. Our BSE adapter\n\t\t\t\t\t\t// does not yet own Raven's joint-walking client class, but binding the\n\t\t\t\t\t\t// authored crawl FX to the struck actor preserves the critical behavior:\n\t\t\t\t\t\t// it follows the target instead of lingering at a world-space hit point.\n\t\t\t\t\t\tconst idVec3 crawlOrigin = tr.endpos + crawlNormal * 0.25f;\n\t\t\t\t\t\tQ4BSE_AttachEffectToEntityTransform( crawlFx, hitEnt, crawlOrigin, crawlNormal.ToMat3() );\n\t\t\t\t\t}\n\t\t\t\t\tconst int crawlDelayMS = idMath::FtoiFast( weaponDef->dict.GetFloat( "crawlDelay", ".3" ) * 1000.0f );\n\t\t\t\t\tspawnArgs.Set( "_q4_lg_next_crawl", va( "%d", gameLocal.time + ( crawlDelayMS > 1 ? crawlDelayMS : 1 ) ) );\n\t\t\t\t}\n'''
text = replace_once(text, old, new, "actor-bound crawl effect")
weapon_cpp.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# 2) The existing high-parity Raven electricity renderer was deliberately
#    limited to Lightning Gun tube/spire FX. impact.fx and crawl.fx use the
#    same Raven electricity primitive (jitterRate 0 / lgun_smallbolt), so send
#    those two authored effects through the same renderer instead of the older
#    generic electricity fallback. This is scoped only to Lightning Gun FX.
# ---------------------------------------------------------------------------
text = bse_cpp.read_text(encoding="utf-8")
old = '''        const bool q4LightningGunAttached =\n            strstr(g_m3Impact.effectPath.c_str(), "effects/weapons/lightninggun/spire") != NULL ||\n            strstr(g_m3Impact.effectPath.c_str(), "effects/weapons/lightninggun/tube") != NULL;\n        if (g_m3Impact.q4ViewLocalGeometry || q4DarkMatterFly || q4LightningGunAttached) {\n'''
new = '''        const bool q4LightningGunElectricity =\n            strstr(g_m3Impact.effectPath.c_str(), "effects/weapons/lightninggun/spire") != NULL ||\n            strstr(g_m3Impact.effectPath.c_str(), "effects/weapons/lightninggun/tube") != NULL ||\n            strstr(g_m3Impact.effectPath.c_str(), "effects/weapons/lightninggun/impact") != NULL ||\n            strstr(g_m3Impact.effectPath.c_str(), "effects/weapons/lightninggun/crawl") != NULL;\n        if (g_m3Impact.q4ViewLocalGeometry || q4DarkMatterFly || q4LightningGunElectricity) {\n'''
text = replace_once(text, old, new, "Lightning Gun impact/crawl electricity parity")
bse_cpp.write_text(text, encoding="utf-8")

print("V19S Lightning Gun impact/crawl parity overlay applied")
print(" - actor crawl FX is now bound to the struck actor instead of world space")
print(" - crawl cadence reads Raven crawlDelay (default .3 sec)")
print(" - impact.fx and crawl.fx electricity use the Raven high-parity renderer")
