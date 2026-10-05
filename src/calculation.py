"""Deterministic one-pass calculation: friction head loss in a full circular pipe.

Darcy-Weisbach:   h_f = f * (L / D) * V^2 / (2 g)
Velocity:         V = Q / (pi * D^2 / 4)
Reynolds number:  Re = V * D / nu
Friction factor:  laminar (Re < 2000)  -> f = 64 / Re
                  otherwise            -> Swamee-Jain explicit approximation of Colebrook
                  f = 0.25 / [log10( eps/(3.7 D) + 5.74 / Re^0.9 )]^2

All functions here work in SI base units (m, m^3/s, m^2/s). Unit conversion
from the user-facing units (L/s, mm, mm^2/s) happens in `to_si()`.
"""
import math

G = 9.80665                  # standard gravity, m/s^2
LAMINAR_RE_LIMIT = 2000.0    # below this Re, use f = 64/Re
TURBULENT_RE_LIMIT = 4000.0  # 2000..4000 is the transitional zone (flagged as a warning)

# Published validity range of the Swamee-Jain correlation
SJ_RE_MIN, SJ_RE_MAX = 5_000.0, 1.0e8
SJ_REL_ROUGH_MIN, SJ_REL_ROUGH_MAX = 1.0e-6, 1.0e-2


def to_si(flow_lps, roughness_mm, viscosity_mm2s):
    """Convert user-facing units to SI. Returns (Q m^3/s, eps m, nu m^2/s)."""
    return flow_lps / 1000.0, roughness_mm / 1000.0, viscosity_mm2s * 1.0e-6


def velocity(q, d):
    """Mean velocity (m/s) for flow q (m^3/s) in diameter d (m)."""
    return q / (math.pi * d * d / 4.0)


def reynolds(v, d, nu):
    return v * d / nu


def friction_factor(re, rel_roughness):
    """Darcy friction factor. Laminar below Re 2000, Swamee-Jain otherwise."""
    if re <= 0:
        raise ValueError(f"Reynolds number must be positive; got {re}")
    if re < LAMINAR_RE_LIMIT:
        return 64.0 / re
    return 0.25 / (math.log10(rel_roughness / 3.7 + 5.74 / re ** 0.9)) ** 2


def colebrook_friction_factor(re, rel_roughness, tol=1e-12, max_iter=100):
    """Implicit Colebrook-White equation. Used only as an independent check in tests."""
    f = 0.02
    for _ in range(max_iter):
        rhs = -2.0 * math.log10(rel_roughness / 3.7 + 2.51 / (re * math.sqrt(f)))
        f_new = 1.0 / rhs ** 2
        if abs(f_new - f) <= tol:
            return f_new
        f = f_new
    return f


def pipe_state(d, q, length, eps, nu):
    """Full one-pass evaluation for diameter d. All arguments in SI units."""
    v = velocity(q, d)
    re = reynolds(v, d, nu)
    rel = eps / d
    f = friction_factor(re, rel)
    hf = f * (length / d) * v * v / (2.0 * G)
    return {"velocity_m_s": v, "reynolds": re, "rel_roughness": rel,
            "friction_factor": f, "head_loss_m": hf}


def head_loss(d, q, length, eps, nu):
    """Friction head loss (m) for diameter d (m). This is the value the solver targets."""
    return pipe_state(d, q, length, eps, nu)["head_loss_m"]
