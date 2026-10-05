"""Solver behaviour: convergence, tolerance boundary, non-convergence, history, limits."""
import pytest

from src.calculation import head_loss, to_si
from src.iteration import CONVERGED, NOT_CONVERGED, solve_pipe_diameter

REFERENCE_D_MM = 176.21  # verified in the workbook: 176.2 mm gives h_f = 10.007 m


def solve(base_case, **kw):
    kw.setdefault("initial_diameter_mm", 100.0)
    return solve_pipe_diameter(**base_case, **kw)


def plug_back(base_case, d_mm):
    q, eps, nu = to_si(base_case["flow_lps"], base_case["roughness_mm"], base_case["viscosity_mm2s"])
    return head_loss(d_mm / 1000, q, base_case["length_m"], eps, nu)


# 1. Known convergence case
def test_known_case_converges(base_case):
    r = solve(base_case, tolerance_m=0.01)
    assert r["status"] == CONVERGED
    assert r["solution_diameter_mm"] == pytest.approx(REFERENCE_D_MM, abs=0.1)
    assert r["final_error_m"] <= 0.01
    # plugging the answer back into the calculation really hits the target
    assert abs(plug_back(base_case, r["solution_diameter_mm"]) - 10.0) <= 0.01


# 2. Different starting conditions reach the same answer
@pytest.mark.parametrize("start_mm", [20.0, 1000.0, 4000.0])
def test_converges_from_different_starting_diameters(base_case, start_mm):
    r = solve(base_case, initial_diameter_mm=start_mm, tolerance_m=0.01)
    assert r["status"] == CONVERGED
    assert r["history"][0]["diameter_mm"] == start_mm          # starting value is really used
    assert r["solution_diameter_mm"] == pytest.approx(REFERENCE_D_MM, abs=0.1)


# 3. Tolerance boundary: error == tolerance converges, error just above does not
def test_tolerance_boundary_is_inclusive(base_case):
    trace = solve(base_case, tolerance_m=1e-9, max_iterations=12)["history"]
    k = 10
    e_k = trace[k - 1]["error_m"]
    assert all(h["error_m"] > e_k for h in trace[:k - 1])       # first time error is this small

    at_boundary = solve(base_case, tolerance_m=e_k, max_iterations=60)
    assert at_boundary["status"] == CONVERGED
    assert at_boundary["iterations"] == k
    assert at_boundary["final_error_m"] == e_k

    just_below = solve(base_case, tolerance_m=e_k * (1 - 1e-9), max_iterations=60)
    assert just_below["iterations"] > k                         # did not stop at iteration k


# 4. Non-convergence: valid inputs, too few iterations
def test_not_converged_when_iterations_run_out(base_case):
    r = solve(base_case, tolerance_m=0.01, max_iterations=3)
    assert r["status"] == NOT_CONVERGED
    assert r["solution_diameter_mm"] is None                   # no fake engineering answer
    assert r["final_error_m"] > 0.01
    assert r["iterations"] == 3
    assert "Not converged" in r["message"]


# 5. Non-convergence: target unreachable inside the supported diameter range
def test_not_converged_when_target_unreachable():
    r = solve_pipe_diameter(flow_lps=5000, length_m=100_000, roughness_mm=0.045,
                            viscosity_mm2s=1.004, target_head_loss_m=0.02,
                            initial_diameter_mm=1000, tolerance_m=0.01, max_iterations=100)
    assert r["status"] == NOT_CONVERGED
    assert r["solution_diameter_mm"] is None
    assert r["last_diameter_mm"] == 5000.0
    assert "largest supported diameter" in r["message"]


# 6. Iteration history is produced and explains the result
def test_history_is_complete_and_consistent(base_case):
    r = solve(base_case, tolerance_m=0.01)
    h = r["history"]
    assert len(h) == r["iterations"] > 1
    assert [row["iteration"] for row in h] == list(range(1, len(h) + 1))
    for row in h:
        assert {"diameter_mm", "head_loss_m", "error_m", "phase", "reynolds"} <= row.keys()
        assert row["error_m"] == pytest.approx(abs(row["head_loss_m"] - 10.0))
    assert h[-1]["diameter_mm"] == r["solution_diameter_mm"]
    assert h[-1]["error_m"] == r["final_error_m"]
    assert all(row["error_m"] > 0.01 for row in h[:-1])        # stopped at first acceptable one


# 7. Maximum iterations is never exceeded
@pytest.mark.parametrize("limit", [1, 2, 5, 8, 13])
def test_never_exceeds_max_iterations(base_case, limit):
    r = solve(base_case, tolerance_m=1e-12, max_iterations=limit)
    assert r["iterations"] <= limit
    assert len(r["history"]) == r["iterations"]
    assert r["status"] == NOT_CONVERGED


def test_starting_value_already_within_tolerance_stops_immediately(base_case):
    r = solve(base_case, initial_diameter_mm=176.2, tolerance_m=0.01)
    assert r["status"] == CONVERGED and r["iterations"] == 1


def test_laminar_case_uses_laminar_physics():
    """Viscous oil (100 mm²/s): the solution must satisfy h_f = 64/Re physics."""
    r = solve_pipe_diameter(flow_lps=0.5, length_m=100, roughness_mm=0.045, viscosity_mm2s=100,
                            target_head_loss_m=2.0, initial_diameter_mm=50, tolerance_m=0.001)
    assert r["status"] == CONVERGED
    last = r["history"][-1]
    assert last["reynolds"] < 2000
    assert last["friction_factor"] == pytest.approx(64 / last["reynolds"])


def test_converged_design_outside_comfort_zone_carries_warning():
    r = solve_pipe_diameter(flow_lps=0.5, length_m=100, roughness_mm=0.045, viscosity_mm2s=100,
                            target_head_loss_m=2.0, initial_diameter_mm=50, tolerance_m=0.001)
    assert any("Velocity" in w for w in r["warnings"])
