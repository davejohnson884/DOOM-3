#!/usr/bin/env python3
'''Reproduce the accepted cumulative Q4BSE source pipeline through V19H, then
apply V19J stock Raven explosion runtime and V19K DMG wall generatedNormal fix.
Used only by the isolated V19K Actions branch/workflow.
'''
from pathlib import Path
import subprocess
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
PY = sys.executable


def run(rel):
    path = ROOT / rel
    if not path.exists():
        raise SystemExit(f'ERROR: missing pipeline script: {path}')
    print(f'>>> {rel}', flush=True)
    subprocess.check_call([PY, str(path), str(ROOT)])


def prepare_projectile_anchors():
    path = ROOT / 'neo' / 'game' / 'Projectile.cpp'
    text = path.read_text(encoding='utf-8-sig')
    q4 = '#include "q4bse/Q4BSEImpactM3.h"'
    if q4 not in text:
        anchor = '#include "Game_local.h"'
        if anchor not in text:
            raise SystemExit('ERROR: Game_local.h include anchor not found in Projectile.cpp')
        text = text.replace(anchor, anchor + '\n' + q4, 1)
    material_anchor = '\tconst idMaterial *material = collision.c.material;'
    if material_anchor not in text:
        axis_anchor = '\tSetAxis( collision.endAxis );'
        if axis_anchor not in text:
            raise SystemExit('ERROR: Collide SetAxis anchor not found in Projectile.cpp')
        compat = axis_anchor + '\n\n\tconst idDict &projectileDef = spawnArgs;\n' + material_anchor
        text = text.replace(axis_anchor, compat, 1)
    path.write_text(text, encoding='utf-8')
    print('>>> prepared Projectile.cpp gameplay anchors', flush=True)


def prepare_weapon_include():
    path = ROOT / 'neo' / 'game' / 'Weapon.cpp'
    text = path.read_text(encoding='utf-8-sig')
    inc = '#include "q4bse/Q4BSEImpactM3.h"'
    if inc not in text:
        anchor = '#include "Game_local.h"'
        if anchor not in text:
            raise SystemExit('ERROR: Game_local.h include anchor not found in Weapon.cpp')
        text = text.replace(anchor, anchor + '\n' + inc, 1)
        path.write_text(text, encoding='utf-8')
    print('>>> prepared Weapon.cpp BSE include', flush=True)


run('q4bse_port/modernize_vs2022.py')
run('q4bse_port/apply_q4bse_m1.py')
run('q4bse_port/apply_q4bse_m3_overlay.py')
run('q4bse_port/finalize_q4bse_m3_single_owner.py')
prepare_projectile_anchors()
run('q4bse_port/promote_q4bse_gameplay.py')
run('q4bse_port/fix_q4bse_gameplay_compile.py')
run('q4bse_port/apply_q4_viewmodel_presentation.py')
run('q4bse_port/finalize_q4bse_projectile_visual_ownership.py')
prepare_weapon_include()
run('q4bse_port/extend_q4bse_attached_fx.py')
run('q4bse_v16_muzzle_lock_gui.py')
run('q4bse_v17_q4_decal_life_bridge.py')
run('q4bse_v18_grenade_launcher_bse.py')
run('q4bse_v18b_nailgun_gui_ammo_track.py')
run('q4bse_v18c_machinegun_exact.py')
run('q4bse_v18d_machinegun_native_lower_gui_light.py')
run('q4bse_v18e_shotgun_joint_muzzle.py')
run('q4bse_port/apply_q4bse_v18f_surface_audio.py')
run('q4bse_port/apply_q4bse_v18h_native_impact_overlay.py')
run('q4bse_port/apply_q4bse_v18i_blaster_native_bse.py')
run('q4bse_port/apply_q4bse_v18j_blaster_line_axis_fix.py')
run('q4bse_port/apply_q4bse_v18k_rocketlauncher.py')
run('q4bse_port/apply_q4bse_v18l_rocket_fly_persist.py')
run('q4bse_port/apply_q4bse_v18m_smooth_attached_emitters.py')
run('q4bse_port/apply_q4bse_v18n_rocket_sphere_domains.py')
run('q4bse_port/apply_q4bse_v18o_rocket_oriented_parity.py')
run('q4bse_port/prepare_q4bse_v18s_guidance_anchor.py')
run('q4bse_port/apply_q4bse_v18p_rocket_guidance_laser.py')
run('q4bse_port/apply_q4bse_v18q_mouse2_guidance.py')
run('q4bse_port/apply_q4bse_v18s_raven_guidance_speed.py')
run('q4bse_port/apply_q4bse_v18t_darkmatter_fx_rings.py')
run('q4bse_port/apply_q4bse_v18u_darkmatter_joint_light.py')
run('q4bse_port/apply_q4bse_v18x_darkmatter_core_only.py')
run('q4bse_port/apply_q4bse_v18y_darkmatter_core_depthhack.py')
run('q4bse_port/apply_q4bse_v18z_darkmatter_core_recharge.py')
run('q4bse_port/apply_q4bse_v19a_darkmatter_core_parity.py')
run('q4bse_port/apply_q4bse_v19b_darkmatter_core_handoff.py')
run('q4bse_port/apply_q4bse_v19c_darkmatter_native_electricity.py')
run('q4bse_port/apply_q4bse_v19d_darkmatter_native_lines.py')
run('q4bse_port/apply_q4bse_v19e_darkmatter_sphere_domains.py')
run('q4bse_port/apply_q4bse_v19f_darkmatter_view_light.py')
run('q4bse_port/apply_q4bse_v19g_darkmatter_projectile_parity.py')
run('q4bse_port/apply_q4bse_v19h_darkmatter_motion_parity.py')

# V45 accepted explosion baseline: deliberately skip the superseded V19I
# detonation experiment and apply V19J directly to V19H.
run('q4bse_port/apply_q4bse_v19j_darkmatter_stock_explosion_runtime.py')
run('q4bse_port/apply_q4bse_v19k_dmg_generatednormal_oriented.py')

print('Q4BSE V19K cumulative pipeline complete.', flush=True)
