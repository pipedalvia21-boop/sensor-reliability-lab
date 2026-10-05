"""Iterative solver: find the pipe diameter whose friction head loss equals the target.

Head loss falls as diameter grows, so the solver:
  1. BRACKET - starts at the user's diameter and doubles (or halves) it until one
               diameter gives too much head loss and another gives too little.
  2. BISECT  - halves that bracket, keeping the half that still contains the target.

Every evaluation, in either phase, is one iteration: it is stored in the history
and counts toward max_iterations. Convergence rule: |h_f - target| <= tolerance.
"""
from src.calculation import (LAMINAR_RE_LIMIT, SJ_REL_ROUGH_MAX, SJ_REL_ROUGH_MIN,
                             SJ_RE_MAX, SJ_RE_MIN, TURBULENT_RE_LIMIT, pipe_state, to_si)
from src.validation import DIAMETER_MAX_MM, DIAMETER_MIN_MM, ValidationError, validate_inputs

CONVERGED = "CONVERGED"
NOT_CONVERGED = "NOT CONVERGED"
INVALID_INPUT = "INVALID INPUT"

DEFAULT_TOLERANCE_M = 0.01
DEFAULT_MAX_ITERATIONS = 60


def _result(status, *, message, history=(), solution=None, invalid_field=None, warnings=()):
    last = history[-1] if history else None
    return {
        "status": status,
        "solution_diameter_mm": solution,  # only set when CONVERGED
        "final_head_loss_m": last["head_loss_m"] if last else None,
        "final_error_m": last["error_m"] if last else None,
        "last_diameter_mm": last["diameter_mm"] if last else None,
        "iterations": len(history),
        "history": list(history),
        "message": message,
        "invalid_field": invalid_field,
        "warnings": list(warnings),
    }


def design_warnings(state):
    """Notes about a converged design that sits outside the documented comfort zone."""
    notes = []
    re, rel, v = state["reynolds"], state["rel_roughness"], state["velocity_m_s"]
    if LAMINAR_RE_LIMIT <= re < TURBULENT_RE_LIMIT:
        notes.append(f"Re = {re:,.0f} is in the transitional zone (2,000-4,000); "
                     "the friction factor there is uncertain.")
    if re >= LAMINAR_RE_LIMIT and not SJ_RE_MIN <= re <= SJ_RE_MAX:
        notes.append(f"Re = {re:,.0f} is outside the Swamee-Jain range (5,000-100,000,000).")
    if re >= LAMINAR_RE_LIMIT and rel > 0 and not SJ_REL_ROUGH_MIN <= rel <= SJ_REL_ROUGH_MAX:
        notes.append(f"Relative roughness ε/D = {rel:.2e} is outside the Swamee-Jain range (1e-6 to 1e-2).")
    if not 0.5 <= v <= 3.0:
        notes.append(f"Velocity {v:.2f} m/s is outside the typical water-design range of 0.5-3.0 m/s.")
    return notes


def solve_pipe_diameter(*, flow_lps, length_m, roughness_mm, viscosity_mm2s,
                        target_head_loss_m, initial_diameter_mm,
                        tolerance_m=DEFAULT_TOLERANCE_M, max_iterations=DEFAULT_MAX_ITERATIONS):
    """Return a result dict with status CONVERGED, NOT CONVERGED or INVALID INPUT."""
    # 1. Validate before any iteration ------------------------------------------------
    try:
        validate_inputs(flow_lps=flow_lps, length_m=length_m, roughness_mm=roughness_mm,
                        viscosity_mm2s=viscosity_mm2s, target_head_loss_m=target_head_loss_m,
                        initial_diameter_mm=initial_diameter_mm, tolerance_m=tolerance_m,
                        max_iterations=max_iterations)
    except ValidationError as exc:
        return _result(INVALID_INPUT, message=str(exc), invalid_field=exc.field)

    q, eps, nu = to_si(flow_lps, roughness_mm, viscosity_mm2s)
    history = []

    def evaluate(d_mm, phase):
        state = pipe_state(d_mm / 1000.0, q, length_m, eps, nu)
        signed = state["head_loss_m"] - target_head_loss_m  # + means pipe is too small
        history.append({
            "iteration": len(history) + 1, "phase": phase, "diameter_mm": d_mm,
            "head_loss_m": state["head_loss_m"], "error_m": abs(signed), "signed_error_m": signed,
            "velocity_m_s": state["velocity_m_s"], "reynolds": state["reynolds"],
            "friction_factor": state["friction_factor"],
        })
        return state, signed

    def converged(state, d_mm):
        return _result(CONVERGED, history=history, solution=d_mm, warnings=design_warnings(state),
                       message=f"Converged: |h_f - target| = {history[-1]['error_m']:.6g} m "
                               f"≤ tolerance {tolerance_m:g} m after {len(history)} iterations.")

    def out_of_iterations():
        return _result(NOT_CONVERGED, history=history,
                       message=f"Not converged: reached the {max_iterations}-iteration limit with "
                               f"|h_f - target| = {history[-1]['error_m']:.6g} m, above the "
                               f"{tolerance_m:g} m tolerance. No diameter is reported.")

    # 2. Bracket, starting from the user's diameter ----------------------------------
    d = float(initial_diameter_mm)
    state, err = evaluate(d, "bracket")
    if abs(err) <= tolerance_m:
        return converged(state, d)
    if err > 0:   # too much head loss -> pipe too small -> grow it
        low, high, step = d, None, 2.0
    else:         # too little head loss -> pipe too big -> shrink it
        low, high, step = None, d, 0.5

    while low is None or high is None:
        at_limit = d >= DIAMETER_MAX_MM if step > 1 else d <= DIAMETER_MIN_MM
        if at_limit:
            side = "largest" if step > 1 else "smallest"
            return _result(NOT_CONVERGED, history=history,
                           message=f"Not converged: even the {side} supported diameter ({d:g} mm) "
                                   f"cannot reach the target head loss. Supported diameters are "
                                   f"{DIAMETER_MIN_MM:g}-{DIAMETER_MAX_MM:g} mm.")
        if len(history) >= max_iterations:
            return out_of_iterations()
        d = min(max(d * step, DIAMETER_MIN_MM), DIAMETER_MAX_MM)
        state, err = evaluate(d, "bracket")
        if abs(err) <= tolerance_m:
            return converged(state, d)
        if err > 0:
            low = d
        else:
            high = d

    # 3. Bisection inside [low, high] --------------------------------------------------
    while len(history) < max_iterations:
        d = (low + high) / 2.0
        state, err = evaluate(d, "bisect")
        if abs(err) <= tolerance_m:
            return converged(state, d)
        if err > 0:
            low = d
        else:
            high = d
    return out_of_iterations()
