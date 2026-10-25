"""2D axial (axisymmetric) flow simulation model for control valves and piping.

Calculates geometric cross-sections, streamlines, velocity field (u, v, |V|),
static pressure field P(x, y), vena contracta contraction, recirculation eddies,
and cavitation/Mach inception zones per IEC 60534 / ISA-75 principles.
Supports multiple valve trims: Globe, Butterfly, Segment/Ball, and Anti-Cavitation Cage,
with fully dynamic geometric scaling from 1/2" (DN15) up to 40" (DN1000).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Flow2DPoint:
    """A 2D coordinate point (x in mm, y in mm)."""
    x: float
    y: float


@dataclass(frozen=True)
class Flow2DSummary:
    """High-level physical parameters of the 2D cross-section flow."""
    inlet_velocity_m_s: float
    throat_velocity_m_s: float
    vena_contracta_velocity_m_s: float
    outlet_velocity_m_s: float
    p1_bar: float
    p2_bar: float
    p_vc_bar: float
    min_pressure_bar: float
    max_mach: float
    is_cavitating: bool
    is_flashing: bool
    is_choked: bool
    contraction_coef: float
    reynolds_inlet: float
    valve_type: str = "globe"


@dataclass(frozen=True)
class Flow2DGeometry:
    """Parametric boundaries of the valve and piping cross-section."""
    d1_mm: float
    d2_mm: float
    dn_mm: float
    opening_pct: float
    x_inlet_mm: float
    x_seat_mm: float
    x_vc_mm: float
    x_outlet_mm: float
    top_wall: list[list[float]]
    bottom_wall: list[list[float]]
    seat_top: list[list[float]]
    seat_bottom: list[list[float]]
    plug: list[list[float]]
    centerline: list[list[float]]
    valve_type: str = "globe"


@dataclass(frozen=True)
class Flow2DGrid:
    """2D Cartesian grid field values."""
    nx: int
    ny: int
    xs: list[float]
    ys: list[float]
    u: list[list[float]]
    v: list[list[float]]
    v_mag: list[list[float]]
    p: list[list[float]]
    mach: list[list[float]]
    cell_type: list[list[int]]


@dataclass(frozen=True)
class Flow2DSimulationResult:
    """Complete output payload for 2D axial flow visualization."""
    summary: Flow2DSummary
    geometry: Flow2DGeometry
    grid: Flow2DGrid
    streamline_seeds: list[list[float]]


def simulate_flow_2d(
    d1_mm: float,
    d2_mm: float,
    dn_mm: float,
    p1_bar: float,
    p2_bar: float,
    pv_bar: float,
    density_kg_m3: float,
    flow_rate_m3_h: float,
    opening_pct: float,
    fl: float = 0.90,
    is_choked: bool = False,
    fluid_type: str = "liquid",
    viscosity_pa_s: float = 0.001,
    sonic_velocity_m_s: float = 1480.0,
    nx: int = 140,
    ny: int = 50,
    valve_type: str = "globe",
) -> Flow2DSimulationResult:
    """Compute 2D axial flow geometry, velocity vectors, and pressure field scaled to actual dimensions."""
    # shortcut: 2D planar axisymmetry used instead of full 3D RANS, upgrade when GPU-WASM solver integrated
    d1 = max(10.0, float(d1_mm))
    d2 = max(10.0, float(d2_mm))
    dn = max(10.0, float(dn_mm))
    p1 = max(0.01, float(p1_bar))
    p2 = max(0.005, min(p1, float(p2_bar)))
    pv = max(0.0, float(pv_bar))
    rho = max(0.05, float(density_kg_m3))
    q_m3_h = max(0.001, float(flow_rate_m3_h))
    op = max(5.0, min(100.0, float(opening_pct)))
    c_sound = max(100.0, float(sonic_velocity_m_s))
    mu = max(1e-6, float(viscosity_pa_s))

    vtype = str(valve_type).lower().strip()
    if vtype not in ("globe", "butterfly", "ball", "angle_cage"):
        vtype = "globe"

    # Adjust default recovery factor FL per valve trim intrinsic hydraulics
    fl_val = max(0.50, min(0.98, float(fl)))
    if vtype == "butterfly" and fl == 0.90:
        fl_val = 0.70
    elif vtype == "ball" and fl == 0.90:
        fl_val = 0.65
    elif vtype == "angle_cage" and fl == 0.90:
        fl_val = 0.96

    r1 = d1 / 2.0
    r2 = d2 / 2.0
    r_dn = dn / 2.0
    r_seat = r_dn * 0.85

    # Dynamically scale axial geometry milestones to actual pipe & valve diameters
    x_seat = 0.0
    x_flange_in = -0.45 * dn
    x_flange_out = 0.55 * dn
    x_vc = dn * (0.28 if vtype == "butterfly" else 0.42)

    l_red = max(0.40 * dn, 1.25 * abs(r1 - r_dn)) if abs(r1 - r_dn) > 0.5 else 0.20 * dn
    x_red_start = x_flange_in - l_red
    l_pipe_in = max(0.80 * d1, 1.0 * dn)
    x_in = x_red_start - l_pipe_in

    l_exp = max(0.50 * dn, 1.40 * abs(r2 - r_dn)) if abs(r2 - r_dn) > 0.5 else 0.25 * dn
    x_exp_end = x_flange_out + l_exp
    l_pipe_out = max(1.0 * d2, 1.3 * dn)
    x_out = x_exp_end + l_pipe_out

    dp = max(0.001, p1 - p2)
    fl_sq = fl_val * fl_val
    p_vc = p1 - (dp / fl_sq)
    if is_choked or p_vc <= pv:
        p_vc = max(0.005, pv * 0.95)

    is_cav = (p_vc <= pv) and (fluid_type == "liquid")
    is_flash = (p2 <= pv) and (fluid_type == "liquid")

    q_m3_s = q_m3_h / 3600.0
    a1_m2 = math.pi * ((d1 / 2000.0) ** 2)
    a2_m2 = math.pi * ((d2 / 2000.0) ** 2)
    v1 = q_m3_s / a1_m2
    v2 = q_m3_s / a2_m2

    cc = max(0.62, min(0.95, 1.0 - math.sqrt(max(0.0, 1.0 - fl_sq))))
    plug_lift_ratio = op / 100.0
    h_gap = r_seat * 0.65 * plug_lift_ratio
    throat_area_m2 = math.pi * ((r_seat / 1000.0) ** 2) * (0.15 + 0.85 * plug_lift_ratio)
    v_throat = q_m3_s / max(1e-7, throat_area_m2)

    dp_vc_pa = max(0.0, (p1 - p_vc) * 1e5)
    v_vc = math.sqrt(v1 * v1 + 2.0 * dp_vc_pa / rho)
    v_vc = max(v_throat * (1.0 / cc), v_vc)

    re_inlet = (rho * v1 * (d1 / 1000.0)) / mu

    geom = _build_geometry(
        x_in, x_red_start, x_flange_in, x_seat, x_vc, x_flange_out, x_exp_end, x_out,
        r1, r2, r_dn, r_seat, h_gap, dn, op, vtype
    )

    grid = _compute_grid(
        nx, ny, x_in, x_red_start, x_flange_in, x_vc, x_flange_out, x_exp_end, x_out,
        r1, r2, r_dn, r_seat, h_gap, dn, op,
        v1, v_vc, v2, p1, p2, p_vc, pv, rho, c_sound, is_cav, vtype,
    )

    max_m = 0.0
    for row in grid.mach:
        for m_val in row:
            if m_val > max_m:
                max_m = m_val

    summary = Flow2DSummary(
        inlet_velocity_m_s=round(v1, 2),
        throat_velocity_m_s=round(v_throat, 2),
        vena_contracta_velocity_m_s=round(v_vc, 2),
        outlet_velocity_m_s=round(v2, 2),
        p1_bar=round(p1, 3),
        p2_bar=round(p2, 3),
        p_vc_bar=round(p_vc, 3),
        min_pressure_bar=round(p_vc, 3),
        max_mach=round(max_m, 2),
        is_cavitating=is_cav,
        is_flashing=is_flash,
        is_choked=is_choked,
        contraction_coef=round(cc, 3),
        reynolds_inlet=round(re_inlet, 0),
        valve_type=vtype,
    )

    seeds = _generate_streamline_seeds(r1, x_in, count=13)

    return Flow2DSimulationResult(
        summary=summary,
        geometry=geom,
        grid=grid,
        streamline_seeds=seeds,
    )


def _build_geometry(
    x_in: float,
    x_red_start: float,
    x_flange_in: float,
    x_seat: float,
    x_vc: float,
    x_flange_out: float,
    x_exp_end: float,
    x_out: float,
    r1: float,
    r2: float,
    r_dn: float,
    r_seat: float,
    h_gap: float,
    dn: float,
    op: float,
    vtype: str = "globe",
) -> Flow2DGeometry:
    """Build upper/lower pipe walls, seat ring, and specific valve trim polygon coordinates."""
    # Build smoothly curved wall coordinates using _pipe_radius
    xs_wall: list[float] = [x_in, x_red_start]
    if abs(r1 - r_dn) > 0.5:
        for k in range(1, 4):
            xs_wall.append(x_red_start + (x_flange_in - x_red_start) * (k / 4.0))
    xs_wall.extend([x_flange_in, x_seat - dn * 0.12, x_seat, x_vc, x_flange_out])
    if abs(r2 - r_dn) > 0.5:
        for k in range(1, 5):
            xs_wall.append(x_flange_out + (x_exp_end - x_flange_out) * (k / 5.0))
    xs_wall.extend([x_exp_end, x_out])

    top_wall: list[list[float]] = []
    bottom_wall: list[list[float]] = []
    for xw in xs_wall:
        rw = _pipe_radius(xw, x_red_start, x_flange_in, x_flange_out, x_exp_end, r1, r2, r_dn, r_seat)
        top_wall.append([round(xw, 1), round(rw, 1)])
        bottom_wall.append([round(xw, 1), round(-rw, 1)])

    if vtype == "butterfly":
        # Tilted disk rotating around central shaft (0, 0)
        theta_deg = 15.0 + (op / 100.0) * 70.0
        theta_rad = theta_deg * math.pi / 180.0
        length_disk = r_seat * 0.96
        th = r_seat * 0.10
        dx = length_disk * math.sin(theta_rad)
        dy = length_disk * math.cos(theta_rad)
        nx_val = -math.cos(theta_rad) * th
        ny_val = math.sin(theta_rad) * th

        plug = [
            [round(dx + nx_val, 1), round(dy + ny_val, 1)],
            [round(dx - nx_val, 1), round(dy - ny_val, 1)],
            [round(-dx - nx_val, 1), round(-dy - ny_val, 1)],
            [round(-dx + nx_val, 1), round(-dy + ny_val, 1)],
        ]
        seat_w = dn * 0.08
        seat_top = [[-seat_w, r_dn], [-seat_w, r_seat], [seat_w, r_seat], [seat_w, r_dn]]
        seat_bottom = [[-seat_w, -r_dn], [-seat_w, -r_seat], [seat_w, -r_seat], [seat_w, -r_dn]]

    elif vtype == "ball":
        # Segment / V-port ball: rotating circular segment blocking upper bore
        y_notch = -r_seat * 0.85 + (1.7 * r_seat) * (op / 100.0)
        bw = dn * 0.28
        plug = [
            [round(-bw, 1), round(r_dn * 1.05, 1)],
            [round(-bw * 0.85, 1), round(y_notch, 1)],
            [0.0, round(y_notch - 0.02 * dn, 1)],
            [round(bw * 0.85, 1), round(y_notch, 1)],
            [round(bw, 1), round(r_dn * 1.05, 1)],
        ]
        seat_top = [[-bw * 0.9, r_dn], [-bw * 0.9, r_seat], [bw * 0.9, r_seat], [bw * 0.9, r_dn]]
        seat_bottom = [[-bw * 0.9, -r_dn], [-bw * 0.9, -r_seat], [bw * 0.9, -r_seat], [bw * 0.9, -r_dn]]

    elif vtype == "angle_cage":
        # Perforated anti-cavitation cage sleeve with moving throttling plug
        cw = dn * 0.30
        plug_tip_y = r_seat - h_gap * 0.92
        plug = [
            [round(-cw * 0.45, 1), round(r_dn * 1.05, 1)],
            [round(-cw * 0.4, 1), round(plug_tip_y, 1)],
            [0.0, round(plug_tip_y, 1)],
            [round(cw * 0.4, 1), round(plug_tip_y, 1)],
            [round(cw * 0.45, 1), round(r_dn * 1.05, 1)],
        ]
        seat_top = [[-cw, r_dn], [-cw, r_seat], [cw, r_seat], [cw, r_dn]]
        seat_bottom = [[-cw, -r_dn], [-cw, -r_seat], [cw, -r_seat], [cw, -r_dn]]

    else:
        # Globe valve: vertical plug into seat ring
        plug_tip_y = r_seat - h_gap
        plug_width = dn * 0.35
        plug_top_y = r_dn * 1.08
        plug = [
            [round(x_seat - plug_width * 0.4, 1), round(plug_top_y, 1)],
            [round(x_seat - plug_width * 0.3, 1), round(plug_tip_y + h_gap * 0.3, 1)],
            [round(x_seat, 1), round(plug_tip_y, 1)],
            [round(x_seat + plug_width * 0.3, 1), round(plug_tip_y + h_gap * 0.3, 1)],
            [round(x_seat + plug_width * 0.4, 1), round(plug_top_y, 1)],
        ]
        seat_top = [
            [round(x_seat - dn * 0.15, 1), round(r_dn, 1)],
            [round(x_seat - dn * 0.15, 1), round(r_seat, 1)],
            [round(x_seat + dn * 0.15, 1), round(r_seat, 1)],
            [round(x_seat + dn * 0.15, 1), round(r_dn, 1)],
        ]
        seat_bottom = [
            [round(x_seat - dn * 0.15, 1), round(-r_dn, 1)],
            [round(x_seat - dn * 0.15, 1), round(-r_seat, 1)],
            [round(x_seat + dn * 0.15, 1), round(-r_seat, 1)],
            [round(x_seat + dn * 0.15, 1), round(-r_dn, 1)],
        ]

    centerline = [[round(x_in, 1), 0.0], [round(x_out, 1), 0.0]]

    return Flow2DGeometry(
        d1_mm=round(r1 * 2, 1),
        d2_mm=round(r2 * 2, 1),
        dn_mm=round(dn, 1),
        opening_pct=round(op, 1),
        x_inlet_mm=round(x_in, 1),
        x_seat_mm=round(x_seat, 1),
        x_vc_mm=round(x_vc, 1),
        x_outlet_mm=round(x_out, 1),
        top_wall=top_wall,
        bottom_wall=bottom_wall,
        seat_top=seat_top,
        seat_bottom=seat_bottom,
        plug=plug,
        centerline=centerline,
        valve_type=vtype,
    )


def _compute_grid(
    nx: int,
    ny: int,
    x_in: float,
    x_red_start: float,
    x_flange_in: float,
    x_vc: float,
    x_flange_out: float,
    x_exp_end: float,
    x_out: float,
    r1: float,
    r2: float,
    r_dn: float,
    r_seat: float,
    h_gap: float,
    dn: float,
    op: float,
    v1: float,
    v_vc: float,
    v2: float,
    p1: float,
    p2: float,
    p_vc: float,
    pv: float,
    rho: float,
    c_sound: float,
    is_cav: bool,
    vtype: str = "globe",
) -> Flow2DGrid:
    """Generate velocity vectors, pressure, and cell classifications on Cartesian grid."""
    xs = [x_in + (x_out - x_in) * i / max(1, nx - 1) for i in range(nx)]
    max_r = max(r1, r2, r_dn) * 1.08
    ys = [-max_r + (2.0 * max_r) * j / max(1, ny - 1) for j in range(ny)]

    u_field: list[list[float]] = []
    v_field: list[list[float]] = []
    vmag_field: list[list[float]] = []
    p_field: list[list[float]] = []
    mach_field: list[list[float]] = []
    cell_field: list[list[int]] = []

    plug_tip_y = r_seat - h_gap

    # Butterfly parameters
    theta_rad = (15.0 + (op / 100.0) * 70.0) * math.pi / 180.0
    cos_th = math.cos(theta_rad)
    sin_th = math.sin(theta_rad)
    bf_th = r_seat * 0.10
    bf_len = r_seat * 0.96

    # Ball notch height
    ball_y_notch = -r_seat * 0.85 + (1.7 * r_seat) * (op / 100.0)

    for _j, y in enumerate(ys):
        u_row: list[float] = []
        v_row: list[float] = []
        vmag_row: list[float] = []
        p_row: list[float] = []
        mach_row: list[float] = []
        c_row: list[int] = []

        for _i, x in enumerate(xs):
            # 1. Determine local wall radius R(x)
            r_pipe = _pipe_radius(x, x_red_start, x_flange_in, x_flange_out, x_exp_end, r1, r2, r_dn, r_seat)

            # Check solid walls
            if abs(y) >= r_pipe:
                u_row.append(0.0)
                v_row.append(0.0)
                vmag_row.append(0.0)
                p_row.append(round(p1 if x < 0 else p2, 3))
                mach_row.append(0.0)
                c_row.append(0)
                continue

            # Check trim-specific solid obstacles
            is_solid = False
            if vtype == "butterfly":
                # Central shaft
                if (x * x + y * y) <= ((r_seat * 0.16) ** 2):
                    is_solid = True
                else:
                    # Rotated disk coords
                    x_rot = x * cos_th - y * sin_th
                    y_rot = x * sin_th + y * cos_th
                    if (abs(x_rot) <= bf_th and abs(y_rot) <= bf_len) or (abs(x) <= dn * 0.05 and abs(y) >= r_seat):
                        is_solid = True

            elif vtype == "ball":
                if (abs(x) <= dn * 0.28 and y >= ball_y_notch) or (abs(x) <= dn * 0.28 and abs(y) >= r_seat):
                    is_solid = True

            elif vtype == "angle_cage":
                cage_slot_pitch = max(4.0, dn * 0.08)
                if (abs(x) <= dn * 0.15 and y >= plug_tip_y) or (
                    abs(x) <= dn * 0.26 and abs(y) >= r_seat and (int(abs(x) / cage_slot_pitch) % 2 == 0)
                ):
                    is_solid = True

            else:
                # Globe valve plug & seat
                plug_w = dn * 0.35
                if abs(x) <= plug_w * 0.4 and y >= plug_tip_y or abs(x) <= dn * 0.15 and abs(y) >= r_seat:
                    is_solid = True

            if is_solid:
                u_row.append(0.0)
                v_row.append(0.0)
                vmag_row.append(0.0)
                p_row.append(round(p1 if x < 0 else p2, 3))
                mach_row.append(0.0)
                c_row.append(0)
                continue

            # Compute flow aerodynamics/hydrodynamics at this point
            u_pt, v_pt, vm_pt, p_pt, c_pt = _point_physics(
                x, y, r_pipe, x_red_start, x_flange_in, x_vc, x_flange_out, x_exp_end,
                r1, r2, r_dn, r_seat, dn, v1, v_vc, v2, p1, p2, p_vc, pv, rho, is_cav, vtype,
            )

            mach = vm_pt / c_sound
            u_row.append(round(u_pt, 2))
            v_row.append(round(v_pt, 2))
            vmag_row.append(round(vm_pt, 2))
            p_row.append(round(p_pt, 3))
            mach_row.append(round(mach, 3))
            c_row.append(c_pt)

        u_field.append(u_row)
        v_field.append(v_row)
        vmag_field.append(vmag_row)
        p_field.append(p_row)
        mach_field.append(mach_row)
        cell_field.append(c_row)

    return Flow2DGrid(
        nx=nx,
        ny=ny,
        xs=[round(x, 1) for x in xs],
        ys=[round(y, 1) for y in ys],
        u=u_field,
        v=v_field,
        v_mag=vmag_field,
        p=p_field,
        mach=mach_field,
        cell_type=cell_field,
    )


def _pipe_radius(
    x: float,
    x_red_start: float,
    x_flange_in: float,
    x_flange_out: float,
    x_exp_end: float,
    r1: float,
    r2: float,
    r_dn: float,
    r_seat: float,
) -> float:
    """Compute local pipe radius smoothly transitioning between inlet, reducer, throat, expander, and outlet."""
    if x <= x_red_start:
        return r1
    if x < x_flange_in:
        t = (x - x_red_start) / max(0.1, x_flange_in - x_red_start)
        s = 0.5 * (1.0 - math.cos(math.pi * t))
        return r1 * (1.0 - s) + r_dn * s
    if x < 0.0:
        t = (x - x_flange_in) / max(0.1, -x_flange_in)
        s = 0.5 * (1.0 - math.cos(math.pi * t))
        return r_dn * (1.0 - s) + r_seat * s
    if x <= x_flange_out:
        t = x / max(0.1, x_flange_out)
        s = 0.5 * (1.0 - math.cos(math.pi * t))
        return r_seat * (1.0 - s) + r_dn * s
    if x < x_exp_end:
        t = (x - x_flange_out) / max(0.1, x_exp_end - x_flange_out)
        s = 0.5 * (1.0 - math.cos(math.pi * t))
        return r_dn * (1.0 - s) + r2 * s
    return r2


def _point_physics(
    x: float,
    y: float,
    r_pipe: float,
    x_red_start: float,
    x_flange_in: float,
    x_vc: float,
    x_flange_out: float,
    x_exp_end: float,
    r1: float,
    r2: float,
    r_dn: float,
    r_seat: float,
    dn: float,
    v1: float,
    v_vc: float,
    v2: float,
    p1: float,
    p2: float,
    p_vc: float,
    pv: float,
    rho: float,
    is_cav: bool,
    vtype: str = "globe",
) -> tuple[float, float, float, float, int]:
    """Calculate local (u, v, |V|, P, cell_type) with smooth gradient transitions between pipe and valve."""
    r_rel = abs(y) / max(0.1, r_pipe)

    # Local bulk continuity velocity across variable-diameter duct
    v_bulk = v1 * ((r1 / max(0.1, r_pipe)) ** 2)
    v_body = v1 * ((r1 / max(0.1, r_dn)) ** 2)

    sigma_vc = max(1.0, 0.28 * dn)
    t_flange_out = math.exp(-((x_flange_out - x_vc) ** 2) / (2.0 * sigma_vc * sigma_vc))

    if x < x_flange_in:
        # Upstream inlet pipe & reducer transition into valve
        prof = max(0.0, 1.0 - (r_rel ** 4))
        u_axial = v_bulk * 1.15 * prof

        # Inward contraction streamline slope during reducer
        if x > x_red_start and abs(r1 - r_dn) > 0.5:
            xi_red = (x - x_red_start) / max(0.1, x_flange_in - x_red_start)
            slope = (r_dn - r1) / max(0.1, x_flange_in - x_red_start)
            v_rad = u_axial * (y / max(0.1, r_pipe)) * slope * math.sin(math.pi * xi_red)
        else:
            v_rad = -0.04 * v_bulk * (y / max(0.1, r_pipe))

        p_local = p1 - 0.5 * rho * max(0.0, u_axial * u_axial - v1 * v1) * 1e-5
        c_type = 1

    elif x_flange_in <= x <= x_flange_out:
        # Valve body, seat & Vena Contracta throttling zone
        t_vc = math.exp(-((x - x_vc) ** 2) / (2.0 * sigma_vc * sigma_vc))
        u_peak = v_body + (v_vc - v_body) * t_vc

        if vtype == "butterfly":
            jet_prof = max(0.0, 1.0 - ((abs(y) - 0.55 * r_seat) / (0.45 * r_seat)) ** 2)
            u_axial = u_peak * jet_prof
            v_rad = 0.16 * u_peak * math.sin((x / max(1.0, x_flange_out)) * math.pi) * (1.0 if y >= 0 else -1.0)
        elif vtype == "ball":
            jet_prof = max(0.0, 1.0 - ((y + 0.40 * r_seat) / (0.58 * r_seat)) ** 2)
            u_axial = u_peak * jet_prof
            v_rad = -0.18 * u_peak * math.sin((x / max(1.0, x_flange_out)) * math.pi)
        elif vtype == "angle_cage":
            jet_prof = 0.88 * (1.0 - 0.18 * math.cos(6.0 * math.pi * y / max(0.1, r_seat))) * max(0.0, 1.0 - r_rel ** 2)
            u_axial = u_peak * jet_prof
            v_rad = 0.06 * u_peak * math.sin((x / max(1.0, x_flange_out)) * math.pi) * (y / max(0.1, r_seat))
        else:
            # Globe
            u_axial = u_peak * max(0.0, 1.0 - ((y + 0.30 * r_seat) / (r_seat * 0.90)) ** 2)
            v_rad = -0.20 * u_peak * math.sin((x / max(1.0, x_flange_out)) * math.pi) * (y / max(0.1, r_seat))

        p_drop = (p1 - p_vc) * t_vc
        p_local = p1 - p_drop

        if is_cav and (p_local <= pv or t_vc > 0.85):
            c_type = 3  # Cavitation / Vapor Core
            p_local = pv
        else:
            c_type = 1

    else:
        # Downstream expansion: smooth gradient transition from valve exit into pipe
        l_recov = max(1.6 * dn, (x_exp_end - x_flange_out) + 1.2 * r2)
        x_norm = min(1.0, max(0.0, (x - x_flange_out) / l_recov))
        s_recov = 0.5 * (1.0 - math.cos(math.pi * x_norm))

        # Valve exit velocity and pressure perfectly match the flange boundary
        u_exit = v_body + (v_vc - v_body) * t_flange_out
        p_exit = p1 - (p1 - p_vc) * t_flange_out

        # Jet centerline velocity and forward pressure smoothly recover to outlet pipe values
        v_target = (1.0 - s_recov) * v_bulk + s_recov * v2
        u_jet = u_exit * (1.0 - s_recov) + v_target * s_recov
        p_fwd = p_exit + (p2 - p_exit) * s_recov

        # Outward expansion streamline velocity in expanding pipe
        if x <= x_exp_end and abs(r2 - r_dn) > 0.5:
            xi_exp = (x - x_flange_out) / max(0.1, x_exp_end - x_flange_out)
            slope = (r2 - r_dn) / max(0.1, x_exp_end - x_flange_out)
            v_exp = u_jet * (y / max(0.1, r_pipe)) * slope * math.sin(math.pi * xi_exp)
        else:
            v_exp = 0.05 * u_jet * (1.0 - x_norm) * (y / max(0.1, r_pipe))

        if vtype == "butterfly":
            # Twin wake recirculation vortices behind disk decaying into pipe
            u_fwd = u_jet * max(0.0, 1.0 - (r_rel ** 2))
            v_fwd = v_exp

            w_x = math.sin(math.pi * min(1.0, x_norm / 0.70)) if x_norm < 0.70 else 0.0
            w_y = math.exp(-0.5 * ((y / max(0.1, 0.22 * r_seat)) ** 2))
            w_e = w_x * w_y

            u_vort = -0.28 * u_jet * math.sin(x_norm * math.pi)
            v_vort = 0.22 * u_jet * math.cos(x_norm * math.pi) * (1.0 if y >= 0 else -1.0)
            p_vort = p_fwd * 0.95

            u_axial = (1.0 - w_e) * u_fwd + w_e * u_vort
            v_rad = (1.0 - w_e) * v_fwd + w_e * v_vort
            p_local = (1.0 - w_e) * p_fwd + w_e * p_vort
            c_type = 2 if w_e > 0.30 else 1

        elif vtype == "ball":
            # Upper dead space recirculation eddy behind ball segment
            u_fwd = u_jet * max(0.0, 1.0 - ((y + 0.35 * r_seat) / (0.65 * r_seat)) ** 2)
            v_fwd = v_exp

            w_x = math.sin(math.pi * min(1.0, x_norm / 0.75)) if x_norm < 0.75 else 0.0
            w_y = math.exp(-0.5 * (((y - 0.45 * r_seat) / max(0.1, 0.28 * r_seat)) ** 2)) if y > 0.0 else 0.0
            w_e = w_x * w_y

            u_vort = -0.38 * u_jet * math.sin(x_norm * math.pi)
            v_vort = 0.24 * u_jet * math.cos(x_norm * math.pi)
            p_vort = p_fwd * 0.95

            u_axial = (1.0 - w_e) * u_fwd + w_e * u_vort
            v_rad = (1.0 - w_e) * v_fwd + w_e * v_vort
            p_local = (1.0 - w_e) * p_fwd + w_e * p_vort
            c_type = 2 if w_e > 0.30 else 1

        elif vtype == "angle_cage":
            # Distributed micro-jet mixing
            u_axial = u_jet * max(0.0, 1.0 - (r_rel ** 2))
            v_rad = v_exp
            p_local = p_fwd
            c_type = 1

        else:
            # Globe valve: eddy behind the plug
            u_fwd = u_jet * max(0.0, 1.0 - (r_rel ** 2))
            v_fwd = v_exp

            w_x = math.sin(math.pi * min(1.0, x_norm / 0.70)) if x_norm < 0.70 else 0.0
            w_y = math.exp(-0.5 * (((y - 0.55 * r_seat) / max(0.1, 0.26 * r_seat)) ** 2)) if y > 0.0 else 0.0
            w_e = w_x * w_y

            u_vort = -0.35 * u_jet * math.sin(x_norm * math.pi)
            v_vort = 0.25 * u_jet * math.cos(x_norm * math.pi)
            p_vort = p_fwd * 0.95

            u_axial = (1.0 - w_e) * u_fwd + w_e * u_vort
            v_rad = (1.0 - w_e) * v_fwd + w_e * v_vort
            p_local = (1.0 - w_e) * p_fwd + w_e * p_vort
            c_type = 2 if w_e > 0.30 else 1

    vm = math.sqrt(u_axial * u_axial + v_rad * v_rad)
    p_local = max(0.005, min(p1, p_local))

    return u_axial, v_rad, vm, p_local, c_type


def _generate_streamline_seeds(r1: float, x_in: float, count: int = 13) -> list[list[float]]:
    """Generate starting seed points for particle streakline advection."""
    seeds: list[list[float]] = []
    for k in range(count):
        frac = (k + 0.5) / count
        y_val = -r1 * 0.88 + (1.76 * r1) * frac
        seeds.append([round(x_in + 2.0, 1), round(y_val, 1)])
    return seeds
