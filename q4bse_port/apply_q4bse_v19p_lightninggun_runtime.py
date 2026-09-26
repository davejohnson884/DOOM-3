#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
weapon_cpp = root / "neo" / "game" / "Weapon.cpp"
impact_cpp = root / "neo" / "game" / "q4bse" / "Q4BSEImpactM3.cpp"
playerview_h = root / "neo" / "game" / "PlayerView.h"
playerview_cpp = root / "neo" / "game" / "PlayerView.cpp"

# ---------------------------------------------------------------------------
# Weapon.cpp: live attack gating + Raven Lightning Gun screen shake.
# ---------------------------------------------------------------------------
text = weapon_cpp.read_text(encoding="utf-8")
old = 'const bool firing = isFiring && !disabled && status != WP_HOLSTERED && AmmoAvailable() > 0;'
new = 'const bool firing = ( WEAPON_ATTACK || WEAPON_NETFIRING ) && !WEAPON_LOWERWEAPON && !disabled && status != WP_HOLSTERED && AmmoAvailable() > 0;'
if old not in text:
    raise SystemExit("V19P: Lightning Gun firing gate anchor not found")
text = text.replace(old, new, 1)

anchor = '''\tconst bool wasFiring = spawnArgs.GetBool( "_q4_lg_firing", "0" );\n\tif ( !wasFiring ) {\n\t\t// Raven State_Fire starts fx_spire only while firing.\n'''
replacement = '''\tconst bool wasFiring = spawnArgs.GetBool( "_q4_lg_firing", "0" );\n\tif ( !wasFiring ) {\n\t\t// Raven WeaponLightningGun.cpp: entering the continuous firing loop gives\n\t\t// the local player a 500ms, scale-2 view shake instead of model recoil.\n\t\tif ( !gameLocal.isMultiplayer && owner == gameLocal.GetLocalPlayer() ) {\n\t\t\towner->playerView.SetShakeParms( MS2SEC( gameLocal.time + 500 ), 2.0f );\n\t\t}\n\n\t\t// Raven State_Fire starts fx_spire only while firing.\n'''
if anchor not in text:
    raise SystemExit("V19P: Lightning Gun fire-transition anchor not found")
text = text.replace(anchor, replacement, 1)
weapon_cpp.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# Q4BSEImpactM3.cpp: use Raven's per-frame electricity shape renderer for the
# attached Lightning Gun spire/tube effects too.  V19O kept the older generic
# static-shape path, so their 2 Hz emitters looked like slow-motion lightning.
# ---------------------------------------------------------------------------
text = impact_cpp.read_text(encoding="utf-8")
anchor = '''    if (pt.primitive == "electricity") {\n        const bool q4DarkMatterFly =\n            !idStr::Icmp(g_m3Impact.effectPath.c_str(), "effects/weapons/dmg/fly.fx");\n        if (g_m3Impact.q4ViewLocalGeometry || q4DarkMatterFly) {\n            return RenderQ4DarkMatterElectricity(model, p, pt, elapsedSec, age, life,\n                                                 worldPos, viewOrigin, viewAxis, color);\n        }\n\n        // Keep all unrelated generic/projectile electricity unchanged.\n'''
replacement = '''    if (pt.primitive == "electricity") {\n        const bool q4DarkMatterFly =\n            !idStr::Icmp(g_m3Impact.effectPath.c_str(), "effects/weapons/dmg/fly.fx");\n        const bool q4LightningGunAttached =\n            strstr(g_m3Impact.effectPath.c_str(), "effects/weapons/lightninggun/spire") != NULL ||\n            strstr(g_m3Impact.effectPath.c_str(), "effects/weapons/lightninggun/tube") != NULL;\n        if (g_m3Impact.q4ViewLocalGeometry || q4DarkMatterFly || q4LightningGunAttached) {\n            // Raven electricity with jitterRate 0 regenerates its shape every frame.\n            return RenderQ4DarkMatterElectricity(model, p, pt, elapsedSec, age, life,\n                                                 worldPos, viewOrigin, viewAxis, color);\n        }\n\n        // Keep all unrelated generic/projectile electricity unchanged.\n'''
if anchor not in text:
    raise SystemExit("V19P: electricity renderer anchor not found")
text = text.replace(anchor, replacement, 1)
impact_cpp.write_text(text, encoding="utf-8")

# ---------------------------------------------------------------------------
# PlayerView: add the small Raven SetShakeParms API needed by the LG.  Doom 3
# already applies shakeAng at the very last render step, so fold Raven's angular
# component into that existing path.  This is ephemeral; do not change savegame
# serialization for a 500ms weapon effect.
# ---------------------------------------------------------------------------
text = playerview_h.read_text(encoding="utf-8")
anchor = '''\tvoid\t\t\t\tCalculateShake( void );\n\n\t// this may involve rendering to a texture and displaying\n'''
replacement = '''\tvoid\t\t\t\tCalculateShake( void );\n\n\t// Raven Q4 view-shake API used by the Lightning Gun.\n\tvoid\t\t\t\tSetShakeParms( float time, float scale ) {\n\t\tshakeFinishTime = SEC2MS( time );\n\t\tshakeScale = scale;\n\t}\n\n\t// this may involve rendering to a texture and displaying\n'''
if anchor not in text:
    raise SystemExit("V19P: PlayerView public anchor not found")
text = text.replace(anchor, replacement, 1)

anchor = '''\tidAngles\t\t\tshakeAng;\t\t\t// from the sound sources\n\n\tidPlayer *\t\t\tplayer;\n'''
replacement = '''\tidAngles\t\t\tshakeAng;\t\t\t// from the sound sources\n\tint\t\t\t\t\tshakeFinishTime;\t// Raven Q4 explicit screen-shake end time\n\tfloat\t\t\t\tshakeScale;\t\t\t// Raven Q4 explicit screen-shake amplitude\n\n\tidPlayer *\t\t\tplayer;\n'''
if anchor not in text:
    raise SystemExit("V19P: PlayerView field anchor not found")
text = text.replace(anchor, replacement, 1)
playerview_h.write_text(text, encoding="utf-8")

text = playerview_cpp.read_text(encoding="utf-8")
anchor = '''\tshakeAng.Zero();\n\n\tClearEffects();\n'''
replacement = '''\tshakeAng.Zero();\n\tshakeFinishTime = 0;\n\tshakeScale = 1.0f;\n\n\tClearEffects();\n'''
if anchor not in text:
    raise SystemExit("V19P: PlayerView constructor anchor not found")
text = text.replace(anchor, replacement, 1)

anchor = '''\tdvFinishTime = ( gameLocal.time - 99999 );\n\tkickFinishTime = ( gameLocal.time - 99999 );\n\n\tfor ( int i = 0 ; i < MAX_SCREEN_BLOBS ; i++ ) {\n'''
replacement = '''\tdvFinishTime = ( gameLocal.time - 99999 );\n\tkickFinishTime = ( gameLocal.time - 99999 );\n\tshakeFinishTime = gameLocal.time;\n\tshakeScale = 1.0f;\n\n\tfor ( int i = 0 ; i < MAX_SCREEN_BLOBS ; i++ ) {\n'''
if anchor not in text:
    raise SystemExit("V19P: PlayerView ClearEffects anchor not found")
text = text.replace(anchor, replacement, 1)

anchor = '''\tshakeAng[0] = gameLocal.random.CRandomFloat() * shakeVolume;\n\tshakeAng[1] = gameLocal.random.CRandomFloat() * shakeVolume;\n\tshakeAng[2] = gameLocal.random.CRandomFloat() * shakeVolume;\n}\n'''
replacement = '''\tshakeAng[0] = gameLocal.random.CRandomFloat() * shakeVolume;\n\tshakeAng[1] = gameLocal.random.CRandomFloat() * shakeVolume;\n\tshakeAng[2] = gameLocal.random.CRandomFloat() * shakeVolume;\n\n\t// Raven PlayerView::ShakeOffsets angular component.  The original Q4 LG calls\n\t// SetShakeParms( now + 0.5s, 2.0 ), producing a one-degree random shake that\n\t// decays linearly over the 500ms window.  Doom 3 already injects shakeAng at\n\t// the final render step, so preserve that behavior here without model recoil.\n\tif ( gameLocal.time < shakeFinishTime ) {\n\t\tconst float offset = ( shakeFinishTime - gameLocal.time ) * shakeScale * 0.001f;\n\t\tshakeAng[0] = idMath::ClampFloat( -70.0f, 70.0f, shakeAng[0] + gameLocal.random.CRandomFloat() * offset );\n\t\tshakeAng[1] = idMath::ClampFloat( -70.0f, 70.0f, shakeAng[1] + gameLocal.random.CRandomFloat() * offset );\n\t\tshakeAng[2] = idMath::ClampFloat( -70.0f, 70.0f, shakeAng[2] + gameLocal.random.CRandomFloat() * offset );\n\t}\n}\n'''
if anchor not in text:
    raise SystemExit("V19P: PlayerView CalculateShake anchor not found")
text = text.replace(anchor, replacement, 1)
playerview_cpp.write_text(text, encoding="utf-8")

print("V19P Lightning Gun runtime parity overlay applied")
print(" - live attack input now cuts beam/spire instantly on trigger release")
print(" - attached LG electricity uses per-frame Raven jitter")
print(" - Raven 500ms / scale-2 Lightning Gun view shake ported")
