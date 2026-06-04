"""Pipe thermal expansion estimation.

Provides linear expansion and thermal stress calculations for common
piping materials using tabulated expansion coefficients.
"""

from __future__ import annotations

# Material thermal expansion coefficients: alpha [um/m/K] at 20-100 C
MATERIAL_ALPHA: dict[str, float] = {
    "carbon_steel": 12.0,
    "stainless_304": 17.3,
    "stainless_316": 16.0,
    "stainless_321": 16.6,
    "copper": 16.6,
    "aluminium": 23.1,
    "pvc": 80.0,
    "cpvc": 70.0,
    "hppe": 200.0,
}

MATERIAL_LABELS: dict[str, str] = {
    "carbon_steel": "Karbon Celik (A106/A53)",
    "stainless_304": "Paslanmaz 304/304L",
    "stainless_316": "Paslanmaz 316/316L",
    "stainless_321": "Paslanmaz 321",
    "copper": "Bakir",
    "aluminium": "Aluminyum",
    "pvc": "PVC",
    "cpvc": "CPVC",
    "hppe": "HPPE",
}

YOUNGS_MODULUS_GPA: dict[str, float] = {
    "carbon_steel": 200.0,
    "stainless_304": 193.0,
    "stainless_316": 193.0,
    "stainless_321": 193.0,
    "copper": 110.0,
    "aluminium": 69.0,
    "pvc": 3.0,
    "cpvc": 2.8,
    "hppe": 0.8,
}


def get_material_options() -> list[str]:
    """Return sorted list of available material keys."""
    return sorted(MATERIAL_ALPHA.keys())


def get_material_label(material: str) -> str:
    """Return human-readable label for a material key."""
    return MATERIAL_LABELS.get(material, material)


def pipe_linear_expansion(length_m: float, delta_t_c: float, material: str) -> float:
    """Calculate linear thermal expansion of a pipe segment.

        dL = alpha * L0 * dT

    Parameters
    ----------
    length_m : Pipe segment length [m]
    delta_t_c : Temperature change [K] or [C]
    material : Material key (see MATERIAL_ALPHA)

    Returns
    -------
    Expansion length [mm].
    """
    alpha = MATERIAL_ALPHA.get(material)
    if alpha is None:
        raise KeyError(f"Bilinmeyen malzeme: {material}")
    delta_l_m = (alpha * 1e-6) * length_m * delta_t_c
    return delta_l_m * 1000.0


def pipe_thermal_stress(delta_t_c: float, material: str) -> float:
    """Thermal stress in a fully constrained pipe.

        sigma = E * alpha * dT

    Parameters
    ----------
    delta_t_c : Temperature change [K] or [C]
    material : Material key

    Returns
    -------
    Thermal stress [MPa].
    """
    alpha = MATERIAL_ALPHA.get(material)
    e_mod = YOUNGS_MODULUS_GPA.get(material)
    if alpha is None or e_mod is None:
        raise KeyError(f"Bilinmeyen malzeme: {material}")
    strain = alpha * 1e-6 * delta_t_c
    stress_gpa = e_mod * strain
    return stress_gpa * 1000.0


def expansion_loop_length(length_m: float, delta_t_c: float, material: str, allowable_stress_mpa: float = 150.0) -> float:
    """Estimate required L-shaped expansion loop leg length.

    Simplified approach: L_loop = sqrt(3 * E * D * dL / S)

    Parameters
    ----------
    length_m : Straight pipe length [m]
    delta_t_c : Temperature change [K] or [C]
    material : Material key
    allowable_stress_mpa : Allowable stress [MPa] (default 150 MPa)

    Returns
    -------
    Estimated expansion loop leg length [m].
    """
    alpha = MATERIAL_ALPHA.get(material)
    e_mod = YOUNGS_MODULUS_GPA.get(material)
    if alpha is None or e_mod is None:
        raise KeyError(f"Bilinmeyen malzeme: {material}")
    delta_l = pipe_linear_expansion(length_m, delta_t_c, material) / 1000.0
    d_outer = 0.1
    s_pa = allowable_stress_mpa * 1e6
    e_pa = e_mod * 1e9
    if s_pa <= 0:
        return 0.0
    return ((3.0 * e_pa * d_outer * delta_l) / s_pa) ** 0.5
