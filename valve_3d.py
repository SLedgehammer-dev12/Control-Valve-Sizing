"""Parametric 3D globe control valve geometry rendered with plotly Mesh3d."""

from __future__ import annotations

import math

import plotly.graph_objects as go

_BODY = "#94a3b8"
_BONNET = "#64748b"
_STEM = "#475569"
_WHEEL = "#ef4444"
_FLANGE = "#2563eb"

MeshData = tuple[list[float], list[float], list[float], list[int], list[int], list[int]]


def _mesh(x: list[float], y: list[float], z: list[float], i: list[int], j: list[int], k: list[int], color: str, name: str) -> go.Mesh3d:
    return go.Mesh3d(
        x=x, y=y, z=z, i=i, j=j, k=k,
        color=color, name=name, showlegend=False, flatshading=True,
        lighting=dict(ambient=0.6, diffuse=0.8, specular=0.2, roughness=0.6),
    )


def _cylinder(p0: tuple[float, float, float], p1: tuple[float, float, float], radius: float, segments: int = 32) -> MeshData:
    dx, dy, dz = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length <= 0.0:
        return [], [], [], [], [], []
    u = (dx / length, dy / length, dz / length)
    a = (0.0, 0.0, 1.0) if abs(u[2]) < 0.9 else (1.0, 0.0, 0.0)
    v1 = (u[1] * a[2] - u[2] * a[1], u[2] * a[0] - u[0] * a[2], u[0] * a[1] - u[1] * a[0])
    n1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2 + v1[2] ** 2)
    v1 = (v1[0] / n1, v1[1] / n1, v1[2] / n1)
    v2 = (u[1] * v1[2] - u[2] * v1[1], u[2] * v1[0] - u[0] * v1[2], u[0] * v1[1] - u[1] * v1[0])
    x, y, z = [], [], []
    for end in (p0, p1):
        for s in range(segments):
            ang = 2.0 * math.pi * s / segments
            c, sn = math.cos(ang), math.sin(ang)
            x.append(end[0] + radius * (c * v1[0] + sn * v2[0]))
            y.append(end[1] + radius * (c * v1[1] + sn * v2[1]))
            z.append(end[2] + radius * (c * v1[2] + sn * v2[2]))
    i, j, k = [], [], []
    for s in range(segments):
        a_i = s
        b_i = (s + 1) % segments
        c_i = s + segments
        d_i = (s + 1) % segments + segments
        i.extend([a_i, b_i])
        j.extend([b_i, d_i])
        k.extend([c_i, c_i])
    for center, base, flip in ((p0, 0, True), (p1, segments, False)):
        x.append(center[0])
        y.append(center[1])
        z.append(center[2])
        c_i = len(x) - 1
        for s in range(segments):
            a_i = base + s
            b_i = base + (s + 1) % segments
            if flip:
                i.append(c_i)
                j.append(a_i)
                k.append(b_i)
            else:
                i.append(c_i)
                j.append(b_i)
                k.append(a_i)
    return x, y, z, i, j, k


def _sphere(center: tuple[float, float, float], radius: float, rings: int = 20, segments: int = 32) -> MeshData:
    x, y, z = [], [], []
    for r in range(rings + 1):
        phi = math.pi * r / rings
        sz = math.cos(phi)
        sr = math.sin(phi)
        for s in range(segments):
            ang = 2.0 * math.pi * s / segments
            x.append(center[0] + radius * sr * math.cos(ang))
            y.append(center[1] + radius * sr * math.sin(ang))
            z.append(center[2] + radius * sz)
    i, j, k = [], [], []
    for r in range(rings):
        for s in range(segments):
            a_i = r * segments + s
            b_i = r * segments + (s + 1) % segments
            c_i = (r + 1) * segments + s
            d_i = (r + 1) * segments + (s + 1) % segments
            i.extend([a_i, a_i])
            j.extend([b_i, d_i])
            k.extend([c_i, c_i])
    return x, y, z, i, j, k


def build_valve_figure(dn_mm: float = 50.0) -> go.Figure:
    """Build a stylized parametric globe control valve sized by DN."""
    s = max(0.4, min(2.5, float(dn_mm) / 100.0))
    body = _sphere((0.0, 0.0, 0.0), s)
    inlet = _cylinder((-2.0 * s, 0.0, 0.0), (-0.5 * s, 0.0, 0.0), 0.42 * s)
    outlet = _cylinder((0.5 * s, 0.0, 0.0), (2.0 * s, 0.0, 0.0), 0.42 * s)
    inlet_flange = _cylinder((-2.08 * s, 0.0, 0.0), (-1.9 * s, 0.0, 0.0), 0.62 * s)
    outlet_flange = _cylinder((1.9 * s, 0.0, 0.0), (2.08 * s, 0.0, 0.0), 0.62 * s)
    bonnet = _cylinder((0.0, 0.0, 0.9 * s), (0.0, 0.0, 1.8 * s), 0.38 * s)
    stem = _cylinder((0.0, 0.0, 1.7 * s), (0.0, 0.0, 2.6 * s), 0.08 * s)
    wheel = _cylinder((0.0, 0.0, 2.6 * s), (0.0, 0.0, 2.72 * s), 0.85 * s)

    fig = go.Figure(data=[
        _mesh(*body, _BODY, "Gövde"),
        _mesh(*inlet, _BODY, "Giriş"),
        _mesh(*outlet, _BODY, "Çıkış"),
        _mesh(*inlet_flange, _FLANGE, "Giriş flanşı"),
        _mesh(*outlet_flange, _FLANGE, "Çıkış flanşı"),
        _mesh(*bonnet, _BONNET, "Bonnet"),
        _mesh(*stem, _STEM, "Mil"),
        _mesh(*wheel, _WHEEL, "El çarkı"),
    ])
    fig.update_layout(
        title=f"3D Vana Modeli — DN{int(round(float(dn_mm)))}",
        scene=dict(
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            zaxis=dict(visible=False),
            aspectmode="data",
            camera=dict(eye=dict(x=1.6, y=1.6, z=1.2)),
        ),
        height=520,
        margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig
