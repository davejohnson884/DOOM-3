#!/usr/bin/env python3
'''V18S: Raven Quake 4 Rocket Launcher guidance-speed parity.

Runs AFTER V18P + V18Q.  It changes only the already-working manual-guidance
projectile block.  Normal rockets retain their authored velocity.  While the
secondary/designator input is held, guided rockets linearly decelerate from the
authored speed to lockSlowdown * authored speed over lockAccelTime; releasing
the guide linearly accelerates them back to authored speed over the same slope.

Retail Q4 homing-mod defaults:
  authored rocket speed = 900
  lockSlowdown          = .25  -> guided target speed 225
  lockAccelTime         = .5 s
  turn_max              = 360 deg/s

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

new_block = r'''\t// Q4 V18S: Raven Rocket Homing Mod speed + turn behavior.  The original
\t// V18P steering endpoint is retained, but Quake 4 does not guide at normal
\t// rocket speed: lockSlowdown=.25 ramps 900 -> 225 over lockAccelTime=.5s.
\t// Releasing the designator reverses the same linear speed ramp back to the
\t// authored normal-flight speed.  This block remains opt-in via q4_manual_guide.
\tif ( state == LAUNCHED && spawnArgs.GetBool( "q4_manual_guide" ) &&
\t\t owner.GetEntity() && owner.GetEntity()->IsType( idPlayer::Type ) ) {
\t\tidPlayer* guidePlayer = static_cast<idPlayer*>( owner.GetEntity() );
\n\t\tidVec3 velocity = physicsObj.GetLinearVelocity();
\t\tfloat projectileSpeed = velocity.Normalize();
\t\tif ( projectileSpeed > 0.001f ) {
\t\t\tidVec3 authoredVelocity;
\t\t\tspawnArgs.GetVector( "velocity", "900 0 0", authoredVelocity );
\t\t\tfloat normalSpeed = authoredVelocity.Length();
\t\t\tif ( normalSpeed < 1.0f ) {
\t\t\t\tnormalSpeed = projectileSpeed;
\t\t\t}
\n\t\t\tfloat slowFraction = spawnArgs.GetFloat( "q4_guide_slow_fraction", "0.25" );
\t\t\tslowFraction = idMath::ClampFloat( 0.01f, 1.0f, slowFraction );
\t\t\tconst float guidedSpeed = normalSpeed * slowFraction;
\t\t\tfloat accelTime = spawnArgs.GetFloat( "q4_guide_accel_time", "0.5" );
\t\t\tif ( accelTime < 0.001f ) {
\t\t\t\taccelTime = 0.001f;
\t\t\t}
\n\t\t\tconst bool guiding = ( guidePlayer->usercmd.buttons & BUTTON_5 ) != 0;
\t\t\tconst float targetSpeed = guiding ? guidedSpeed : normalSpeed;
\t\t\tconst float fullSpeedDelta = idMath::Fabs( normalSpeed - guidedSpeed );
\t\t\tconst float speedStep = fullSpeedDelta * MS2SEC( gameLocal.GetMSec() ) / accelTime;
\n\t\t\tif ( projectileSpeed < targetSpeed ) {
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
\n\t\t\tif ( guiding ) {
\t\t\t\tconst float guideRange = spawnArgs.GetFloat( "q4_guide_range", "10000" );
\t\t\t\tconst float turnRate = spawnArgs.GetFloat( "q4_guide_turn_rate", "360" );
\t\t\t\ttrace_t guideTrace;
\t\t\t\tconst idVec3 guideStart = guidePlayer->firstPersonViewOrigin;
\t\t\t\tconst idVec3 guideEnd = guideStart + guidePlayer->firstPersonViewAxis[0] * guideRange;
\t\t\t\tgameLocal.clip.TracePoint( guideTrace, guideStart, guideEnd, MASK_SHOT_RENDERMODEL, guidePlayer );
\n\t\t\t\tidVec3 desired = guideTrace.endpos - physicsObj.GetOrigin();
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
\t\t\t\t// No steering after release; only restore Raven's normal rocket speed.
\t\t\t\tphysicsObj.SetLinearVelocity( velocity * projectileSpeed );
\t\t\t}
\t\t}
\t}
'''

text = text[:start] + new_block + text[end:]

for needle in (
    'GetFloat( "q4_guide_slow_fraction", "0.25" )',
    'GetFloat( "q4_guide_accel_time", "0.5" )',
    'GetFloat( "q4_guide_turn_rate", "360" )',
    'const bool guiding = ( guidePlayer->usercmd.buttons & BUTTON_5 ) != 0',
    'physicsObj.SetLinearVelocity( velocity * projectileSpeed )',
):
    if needle not in text:
        raise SystemExit(f'ERROR: V18S verification missing: {needle}')

# Make sure the obsolete preserve-current-speed V18P path is gone.
if 'physicsObj.SetLinearVelocity( newDir * projectileSpeed );' not in text:
    raise SystemExit('ERROR: V18S steering velocity write missing')
if text.count(start_marker) != 0:
    raise SystemExit('ERROR: V18S old V18P guide block marker survived replacement')

PROJECTILE_CPP.write_text(text, encoding='utf-8')

print('Q4BSE V18S RAVEN GUIDANCE SPEED PASS.')
print('  - normal authored rocket speed remains the source of truth')
print('  - guide hold ramps to 25% speed over 0.5 s by default')
print('  - guide release ramps back to normal speed over the same slope')
print('  - guide turn rate defaults to Raven 360 deg/s')
print('  - beam/marker/BSE/trail/impact/explosion paths untouched')
