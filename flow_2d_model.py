"""2D axial (axisymmetric) flow simulation model for control valves and piping.

Calculates geometric cross-sections, streamlines, velocity field (u, v, |V|),
static pressure field P(x, y), vena contracta contraction, recirculation eddies,
and cavitation/Mach inception zones per IEC 60534 / ISA-75 principles.
Supports multiple valve trims: Globe, Butterfly, Segment/Ball, and Anti-Cavitation Cage.
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
    """Sampled 2D flow field on a regular Cartesian grid for heatmap & HUD."""
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
    """Complete 2D axial flow simulation package for visualization."""
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
    """Compute 2D axial flow geometry, velocity vectors, and pressure field for selectable valve types."""
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

    x_in = -dn * 2.2
    x_seat = 0.0
    x_vc = dn * (0.35 if vtype == "butterfly" else 0.45)
    x_out = dn * 2.5

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

    geom = _build_geometry(x_in, x_seat, x_vc, x_out, r1, r2, r_seat, h_gap, dn, op, vtype)

    grid = _compute_grid(
        nx, ny, x_in, x_out, r1, r2, r_seat, h_gap, dn, op,
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
    x_seat: float,
    x_vc: float,
    x_out: float,
    r1: float,
    r2: float,
    r_seat: float,
    h_gap: float,
    dn: float,
    op: float,
    vtype: str = "globe",
) -> Flow2DGeometry:
    """Build upper/lower pipe walls, seat ring, and specific valve trim polygon coordinates."""
    x_pre = x_seat - dn * 0.4
    x_post = x_vc + dn * 0.8

    top_wall = [
        [x_in, r1],
        [x_pre, r1],
        [x_seat - 5.0, r_seat + 8.0],
        [x_seat, r_seat],
        [x_vc, r_seat * 0.95],
        [x_post, r2],
        [x_out, r2],
    ]

    bottom_wall = [
        [x_in, -r1],
        [x_pre, -r1],
        [x_seat - 5.0, -(r_seat + 8.0)],
        [x_seat, -r_seat],
        [x_vc, -(r_seat * 0.95)],
        [x_post, -r2],
        [x_out, -r2],
    ]

    if vtype == "butterfly":
        # Tilted disk rotating around central shaft (0, 0)
        theta_deg = 15.0 + (op / 100.0) * 70.0
        theta_rad = theta_deg * math.pi / 180.0
        length_disk = r1 * 0.94
        th = r1 * 0.08
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
        seat_top = [[-4.0, r1], [-4.0, r1 * 0.95], [4.0, r1 * 0.95], [4.0, r1]]
        seat_bottom = [[-4.0, -r1], [-4.0, -r1 * 0.95], [4.0, -r1 * 0.95], [4.0, -r1]]

    elif vtype == "ball":
        # Segment / V-port ball: rotating circular segment blocking upper bore
        y_notch = -r_seat * 0.85 + (1.7 * r_seat) * (op / 100.0)
        bw = dn * 0.28
        plug = [
            [-bw, r1 * 1.05],
            [-bw * 0.85, y_notch],
            [0.0, y_notch - 2.0],
            [bw * 0.85, y_notch],
            [bw, r1 * 1.05],
        ]
        seat_top = [[-bw * 0.9, r1], [-bw * 0.9, r_seat], [bw * 0.9, r_seat], [bw * 0.9, r1]]
        seat_bottom = [[-bw * 0.9, -r1], [-bw * 0.9, -r_seat], [bw * 0.9, -r_seat], [bw * 0.9, -r1]]

    elif vtype == "angle_cage":
        # Perforated anti-cavitation cage sleeve with moving throttling plug
        cw = dn * 0.30
        plug_tip_y = r_seat - h_gap * 0.92
        plug = [
            [-cw * 0.45, r1 * 1.05],
            [-cw * 0.4, plug_tip_y],
            [0.0, plug_tip_y],
            [cw * 0.4, plug_tip_y],
            [cw * 0.45, r1 * 1.05],
        ]
        seat_top = [[-cw, r1], [-cw, r_seat], [cw, r_seat], [cw, r1]]
        seat_bottom = [[-cw, -r1], [-cw, -r_seat], [cw, -r_seat], [cw, -r1]]

    else:
        # Globe valve: vertical plug into seat ring
        plug_tip_y = r_seat - h_gap
        plug_width = dn * 0.35
        plug_top_y = r1 * 1.05
        plug = [
            [x_seat - plug_width * 0.4, plug_top_y],
            [x_seat - plug_width * 0.3, plug_tip_y + h_gap * 0.3],
            [x_seat, plug_tip_y],
            [x_seat + plug_width * 0.3, plug_tip_y + h_gap * 0.3],
            [x_seat + plug_width * 0.4, plug_top_y],
        ]
        seat_top = [
            [x_seat - dn * 0.15, r1],
            [x_seat - dn * 0.15, r_seat],
            [x_seat + dn * 0.15, r_seat],
            [x_seat + dn * 0.15, r1],
        ]
        seat_bottom = [
            [x_seat - dn * 0.15, -r1],
            [x_seat - dn * 0.15, -r_seat],
            [x_seat + dn * 0.15, -r_seat],
            [x_seat + dn * 0.15, -r1],
        ]

    centerline = [[x_in, 0.0], [x_out, 0.0]]

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
    x_out: float,
    r1: float,
    r2: float,
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
    max_r = max(r1, r2) * 1.05
    ys = [-max_r + (2.0 * max_r) * j / max(1, ny - 1) for j in range(ny)]

    u_field: list[list[float]] = []
    v_field: list[list[float]] = []
    vmag_field: list[list[float]] = []
    p_field: list[list[float]] = []
    mach_field: list[list[float]] = []
    cell_field: list[list[int]] = []

    plug_tip_y = r_seat - h_gap
    plug_w = (r_seat * 0.4)

    # Butterfly parameters
    theta_rad = (15.0 + (op / 100.0) * 70.0) * math.pi / 180.0
    cos_th = math.cos(theta_rad)
    sin_th = math.sin(theta_rad)
    bf_th = r1 * 0.08
    bf_len = r1 * 0.94

    # Ball notch height
    ball_y_notch = -r_seat * 0.85 + (1.7 * r_seat) * (op / 100.0)

    for _j, y in enumerate(ys):
        u_row: list[float] = []
        v_row: list[float] = []
        vmag_row: list[float] = []
        p_row: list[float] = []
        m_row: list[float] = []
        c_row: list[int] = []

        for _i, x in enumerate(xs):
            # 1. Determine local wall radius R(x)
            r_pipe = _pipe_radius(x, r1, r2, r_seat)

            # Check solid walls
            if abs(y) >= r_pipe:
                u_row.append(0.0)
                v_row.append(0.0)
                vmag_row.append(0.0)
                p_row.append(round(p1 if x < 0 else p2, 3))
                m_row.append(0.0)
                c_row.append(0)
                continue

            # Check trim-specific solid obstacles
            is_solid = False
            if vtype == "butterfly":
                # Central shaft
                if (x * x + y * y) <= ((r1 * 0.16) ** 2):
                    is_solid = True
                else:
                    # Rotated disk coords
                    x_rot = x * cos_th - y * sin_th
                    y_rot = x * sin_th + y * cos_th
                    if abs(x_rot) <= bf_th and abs(y_rot) <= bf_len or abs(x) <= 3.0 and abs(y) >= r1 * 0.94:
                        is_solid = True

            elif vtype == "ball":
                if abs(x) <= dn * 0.28 and y >= ball_y_notch or abs(x) <= dn * 0.28 and abs(y) >= r_seat:
                    is_solid = True

            elif vtype == "angle_cage":
                if abs(x) <= dn * 0.15 and y >= plug_tip_y or abs(x) <= dn * 0.26 and abs(y) >= r_seat and (int(abs(x) / 3.0) % 2 == 0):
                    is_solid = True

            else:  # globe
                if abs(x) <= plug_w and y >= plug_tip_y or abs(x) <= plug_w * 0.4 and abs(y) >= r_seat:
                    is_solid = True

            if is_solid:
                u_row.append(0.0)
                v_row.append(0.0)
                vmag_row.append(0.0)
                p_row.append(round(p1 if x < 0 else p2, 3))
                m_row.append(0.0)
                c_row.append(0)
                continue

            # 2. Physics-based velocity and pressure distribution
            u, v, vm, p, c_type = _point_physics(
                x, y, r_pipe, r1, r_seat, v1, v_vc, v2, p1, p2, p_vc, pv, rho, is_cav, vtype
            )

            mach = vm / c_sound
            u_row.append(round(u, 2))
            v_row.append(round(v, 2))
            vmag_row.append(round(vm, 2))
            p_row.append(round(p, 3))
            m_row.append(round(mach, 3))
            c_row.append(c_type)

        u_field.append(u_row)
        v_field.append(v_row)
        vmag_field.append(vmag_row)
        p_field.append(p_row)
        mach_field.append(m_row)
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


def _pipe_radius(x: float, r1: float, r2: float, r_seat: float) -> float:
    """Compute local pipe radius smoothly transitioning between inlet, throat, and outlet."""
    if x <= -20.0:
        return r1
    if x >= 40.0:
        return r2
    if x < 0.0:
        t = (x + 20.0) / 20.0
        return r1 * (1.0 - t) + r_seat * t
    t = x / 40.0
    return r_seat * (1.0 - t) + r2 * t


def _point_physics(
    x: float,
    y: float,
    r_pipe: float,
    r1: float,
    r_seat: float,
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
    """Calculate local (u, v, |V|, P, cell_type) according to specific valve trim aerodynamics."""
    r_rel = abs(y) / max(0.1, r_pipe)

    if x < -15.0:
        # Fully developed inlet pipe
        u_axial = v1 * 1.15 * max(0.0, 1.0 - (r_rel ** 6))
        v_rad = -0.05 * v1 * (y / r_pipe)
        p_local = p1 - 0.5 * rho * (u_axial * u_axial - v1 * v1) * 1e-5
        c_type = 1

    elif -15.0 <= x <= 15.0:
        # Throat & Vena Contracta zone
        t_vc = math.exp(-((x - 6.0) ** 2) / 60.0)
        u_peak = v1 + (v_vc - v1) * t_vc

        if vtype == "butterfly":
            # Flow divides into two jets: upper stream and lower stream around the disk
            jet_prof = max(0.0, 1.0 - ((abs(y) - 0.55 * r1) / (0.45 * r1)) ** 2)
            u_axial = u_peak * jet_prof
            v_rad = 0.16 * u_peak * math.sin((x / 15.0) * math.pi) * (1.0 if y >= 0 else -1.0)
        elif vtype == "ball":
            # Flow shoots strongly through bottom notch aperture
            jet_prof = max(0.0, 1.0 - ((y + 0.40 * r1) / (0.58 * r1)) ** 2)
            u_axial = u_peak * jet_prof
            v_rad = -0.18 * u_peak * math.sin((x / 15.0) * math.pi)
        elif vtype == "angle_cage":
            # Distributed multi-jet flow through cage slits
            jet_prof = 0.88 * (1.0 - 0.18 * math.cos(6.0 * math.pi * y / r1)) * max(0.0, 1.0 - r_rel ** 2)
            u_axial = u_peak * jet_prof
            v_rad = 0.06 * u_peak * math.sin((x / 10.0) * math.pi) * (y / r1)
        else:
            # Globe valve: flow under the plug
            u_axial = u_peak * max(0.0, 1.0 - ((y + 0.3 * r_seat) / (r_seat * 0.9)) ** 2)
            v_rad = -0.2 * u_peak * math.sin((x / 15.0) * math.pi) * (y / r_seat)

        p_drop = (p1 - p_vc) * t_vc
        p_local = p1 - p_drop

        if is_cav and (p_local <= pv or t_vc > 0.85):
            c_type = 3  # Cavitation / Vapor Core
            p_local = pv
        else:
            c_type = 1

    else:
        # Downstream expansion & recirculation eddy zone
        x_norm = min(1.0, (x - 15.0) / 60.0)
        u_jet = v_vc * (1.0 - x_norm) + v2 * x_norm

        if vtype == "butterfly":
            # Twin wake recirculation vortices behind the central tilted disk
            if abs(y) < (0.35 * r1) and x_norm < 0.65:
                u_axial = -0.26 * u_jet * math.sin(x_norm * math.pi)
                v_rad = 0.20 * u_jet * math.cos(x_norm * math.pi) * (1.0 if y >= 0 else -1.0)
                p_local = p_vc + (p2 - p_vc) * 0.5
                c_type = 2  # Recirculation Eddy
            else:
                u_axial = u_jet * max(0.0, 1.0 - (r_rel ** 2))
                v_rad = 0.08 * u_jet * (1.0 - x_norm) * (y / r_pipe)
                p_local = p_vc + (p2 - p_vc) * x_norm
                c_type = 1

        elif vtype == "ball":
            # Wide upper recirculation eddy in the dead space behind ball segment
            if y > (0.10 * r1) and x_norm < 0.75:
                u_axial = -0.38 * u_jet * math.sin(x_norm * math.pi)
                v_rad = 0.24 * u_jet * math.cos(x_norm * math.pi)
                p_local = p_vc + (p2 - p_vc) * 0.5
                c_type = 2
            else:
                u_axial = u_jet * max(0.0, 1.0 - ((y + 0.35 * r1) / (0.65 * r1)) ** 2)
                v_rad = 0.06 * u_jet * (1.0 - x_norm) * (y / r_pipe)
                p_local = p_vc + (p2 - p_vc) * x_norm
                c_type = 1

        elif vtype == "angle_cage":
            # Multi-jet rapid mixing with negligible macro-eddy
            u_axial = u_jet * max(0.0, 1.0 - (r_rel ** 2))
            v_rad = 0.05 * u_jet * (1.0 - x_norm) * (y / r_pipe)
            p_local = p_vc + (p2 - p_vc) * x_norm
            c_type = 1

        else:
            # Globe valve: single eddy behind the top plug
            if y > (r_seat * 0.4) and x_norm < 0.7:
                u_axial = -0.35 * u_jet * math.sin(x_norm * math.pi)
                v_rad = 0.25 * u_jet * math.cos(x_norm * math.pi)
                p_local = p_vc + (p2 - p_vc) * 0.5
                c_type = 2
            else:
                u_axial = u_jet * max(0.0, 1.0 - (r_rel ** 2))
                v_rad = 0.08 * u_jet * (1.0 - x_norm) * (y / r_pipe)
                p_local = p_vc + (p2 - p_vc) * x_norm
                c_type = 1

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
