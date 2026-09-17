#!/usr/bin/env python3
'''V18S: Raven Quake 4 Rocket Launcher guidance-speed parity.

Runs AFTER V18P + V18Q and changes only the already-working manual-guidance
projectile block. Normal rockets retain their authored velocity. While the
secondary/designator input is held, guided rockets linearly decelerate toward
q4_guide_speed_scale * authored speed over q4_guide_slow_time. Releasing the
guide linearly accelerates them back to authored speed over
q4_guide_recover_time.

Defaults:
  authored rocket speed       = 900
  q4_guide_speed_scale        = .25  -> guided target speed 225
  q4_guide_slow_time          = .5 s
  q4_guide_recover_time       = .5 s
  q4_guide_turn_rate          = 360 deg/s

No beam, marker, BSE, trail, impact, explosion, damage, ammo, reload, or normal
rocket presentation behavior is changed here.
'''

from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PROJECTILE_CPP = ROOT / 'neo' / 'game' / 'Projectile.cpp'
if not PROJECTILE_CPP.exists():
    raise SystemExit(f'ERROR: V18S prerequisite missing: {PROJECTILE_CPP}')

text = PROJECTILE_CPP.read_text(encoding='utf-8-sig')

start_marker = '\t// Q4 V18P: manual crosshair guidance.'
end_marker = '\n\tif ( thinkFlags & TH_THINK ) {'
start = text.find(start_marker)
if start < 0:
    raise SystemExit('ERROR: V18S could not find V18P manual-guidance block start')
end = text.find(end_marker, start)
if end < 0:
    raise SystemExit('ERROR: V18S could not find idProjectile::Think TH_THINK anchor')
if text.find(start_marker, start + 1) >= 0:
    raise SystemExit('ERROR: V18S found multiple V18P manual-guidance blocks')

new_block = r'''\t// Q4 V18S: Raven Rocket Homing Mod speed + turn behavior. The original
\t// V18P steering endpoint is retained, but guidance can slow the projectile
\t// smoothly and restore normal speed after release. All timing values are
\t// projectile DEF spawnargs so future tuning requires no DLL rebuild.
\tif ( state == LAUNCHED && spawnArgs.GetBool( "q4_manual_guide" ) &&
\t\t owner.GetEntity() && owner.GetEntity()->IsType( idPlayer::Type ) ) {
\t\tidPlayer* guidePlayer = static_cast<idPlayer*>( owner.GetEntity() );

\t\tidVec3 velocity = physicsObj.GetLinearVelocity();
\t\tfloat projectileSpeed = velocity.Normalize();
\t\tif ( projectileSpeed > 0.001f ) {
\t\t\tidVec3 authoredVelocity;
\t\t\tspawnArgs.GetVector( "velocity", "900 0 0", authoredVelocity );
\t\t\tfloat normalSpeed = authoredVelocity.Length();
\t\t\tif ( normalSpeed < 1.0f ) {
\t\t\t\tnormalSpeed = 900.0f;
\t\t\t}

\t\t\tfloat speedScale = spawnArgs.GetFloat( "q4_guide_speed_scale", "0.25" );
\t\t\tspeedScale = idMath::ClampFloat( 0.01f, 1.0f, speedScale );
\t\t\tconst float guidedSpeed = normalSpeed * speedScale;

\t\t\tfloat slowTime = spawnArgs.GetFloat( "q4_guide_slow_time", "0.5" );
\t\t\tfloat recoverTime = spawnArgs.GetFloat( "q4_guide_recover_time", "0.5" );
\t\t\tif ( slowTime < 0.001f ) {
\t\t\t\tslowTime = 0.001f;
\t\t\t}
\t\t\tif ( recoverTime < 0.001f ) {
\t\t\t\trecoverTime = 0.001f;
\t\t\t}

\t\t\tconst bool guiding = ( guidePlayer->usercmd.buttons & BUTTON_5 ) != 0;
\t\t\tconst float targetSpeed = guiding ? guidedSpeed : normalSpeed;
\t\t\tconst float rampTime = guiding ? slowTime : recoverTime;
\t\t\tconst float fullSpeedDelta = idMath::Fabs( normalSpeed - guidedSpeed );
\t\t\tconst float speedStep = fullSpeedDelta * MS2SEC( gameLocal.GetMSec() ) / rampTime;

\t\t\tif ( projectileSpeed < targetSpeed ) {
\t\t\t\tprojectileSpeed += speedStep;
\t\t\t\tif ( projectileSpeed > targetSpeed ) {
\t\t\t\t\tprojectileSpeed = targetSpeed;
\t\t\t\t}
\t\t\t} else if ( projectileSpeed > targetSpeed ) {
\t\t\t\tprojectileSpeed -= speedStep;
\t\t\t\tif ( projectileSpeed < targetSpeed ) {
\t\t\t\t\tprojectileSpeed = targetSpeed;
\t\t\t\t}
\t\t\t}

\t\t\tif ( guiding ) {
\t\t\t\tconst float guideRange = spawnArgs.GetFloat( "q4_guide_range", "10000" );
\t\t\t\tconst float turnRate = spawnArgs.GetFloat( "q4_guide_turn_rate", "360" );
\t\t\t\ttrace_t guideTrace;
\t\t\t\tconst idVec3 guideStart = guidePlayer->firstPersonViewOrigin;
\t\t\t\tconst idVec3 guideEnd = guideStart + guidePlayer->firstPersonViewAxis[0] * guideRange;
\t\t\t\tgameLocal.clip.TracePoint( guideTrace, guideStart, guideEnd, MASK_SHOT_RENDERMODEL, guidePlayer );

\t\t\t\tidVec3 desired = guideTrace.endpos - physicsObj.GetOrigin();
\t\t\t\tif ( desired.Normalize() > 0.001f ) {
\t\t\t\t\tconst float dot = idMath::ClampFloat( -1.0f, 1.0f, velocity * desired );
\t\t\t\t\tconst float angleDeg = RAD2DEG( idMath::ACos( dot ) );
\t\t\t\t\tconst float maxTurnDeg = turnRate * MS2SEC( gameLocal.GetMSec() );
\t\t\t\t\tconst float frac = ( angleDeg > maxTurnDeg && angleDeg > 0.001f ) ? ( maxTurnDeg / angleDeg ) : 1.0f;
\t\t\t\t\tidVec3 newDir = velocity * ( 1.0f - frac ) + desired * frac;
\t\t\t\t\tif ( newDir.Normalize() > 0.001f ) {
\t\t\t\t\t\tphysicsObj.SetLinearVelocity( newDir * projectileSpeed );
\t\t\t\t\t\tidMat3 q4GuideAxis = newDir.ToMat3();
\t\t\t\t\t\tif ( !spawnArgs.GetBool( "q4_projectile_forward_x" ) ) {
\t\t\t\t\t\t\tidVec3 tmp = q4GuideAxis[2];
\t\t\t\t\t\t\tq4GuideAxis[2] = q4GuideAxis[0];
\t\t\t\t\t\t\tq4GuideAxis[0] = -tmp;
\t\t\t\t\t\t}
\t\t\t\t\t\tphysicsObj.SetAxis( q4GuideAxis );
\t\t\t\t\t}
\t\t\t\t}
\t\t\t} else {
\t\t\t\t// No steering after release; only restore the authored normal speed.
\t\t\t\tphysicsObj.SetLinearVelocity( velocity * projectileSpeed );
\t\t\t}
\t\t}
\t}
'''

text = text[:start] + new_block + text[end:]

for needle in (
    'GetFloat( "q4_guide_speed_scale", "0.25" )',
    'GetFloat( "q4_guide_slow_time", "0.5" )',
    'GetFloat( "q4_guide_recover_time", "0.5" )',
    'GetFloat( "q4_guide_turn_rate", "360" )',
    'const bool guiding = ( guidePlayer->usercmd.buttons & BUTTON_5 ) != 0',
    'physicsObj.SetLinearVelocity( velocity * projectileSpeed )',
):
    if needle not in text:
        raise SystemExit(f'ERROR: V18S verification missing: {needle}')

if 'physicsObj.SetLinearVelocity( newDir * projectileSpeed );' not in text:
    raise SystemExit('ERROR: V18S steering velocity write missing')
if text.count(start_marker) != 0:
    raise SystemExit('ERROR: V18S old V18P guide block marker survived replacement')

PROJECTILE_CPP.write_text(text, encoding='utf-8')

print('Q4BSE V18S RAVEN GUIDANCE SPEED PASS.')
print('  - q4_guide_speed_scale defaults to 0.25 (900 -> 225)')
print('  - q4_guide_slow_time defaults to 0.5 s')
print('  - q4_guide_recover_time defaults to 0.5 s')
print('  - guide turn rate defaults to Raven 360 deg/s')
print('  - release continues speed recovery with no steering')
print('  - beam/marker/BSE/trail/impact/explosion paths untouched')

# Temporary build diagnostic: if another cumulative patch has injected invalid
# Game_local.cpp code, print the exact neighborhood immediately before compile.
local_cpp = ROOT / 'neo' / 'game' / 'Game_local.cpp'
if local_cpp.exists():
    local_lines = local_cpp.read_text(encoding='utf-8-sig').splitlines()
    lo = max(0, min(2768, len(local_lines) - 1))
    hi = min(len(local_lines), lo + 40)
    print(f'--- Game_local.cpp diagnostic lines {lo + 1}-{hi} ---')
    for idx in range(lo, hi):
        print(f'{idx + 1:5d}: {local_lines[idx]}')
