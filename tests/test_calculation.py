"""One-pass calculation checks, independent of the solver."""
import math

import pytest
from openpyxl import load_workbook

from src.calculation import (colebrook_friction_factor, friction_factor, head_loss,
                             pipe_state, to_si)

Q, L, EPS, NU = 0.05, 500.0, 0.045e-3, 1.004e-6


def test_unit_conversion_to_si():
    assert to_si(50, 0.045, 1.004) == pytest.approx((0.05, 4.5e-5, 1.004e-6))


def test_hand_calculation_at_200_mm():
    # Hand steps: A = pi*0.2^2/4 = 0.0314159 m², V = 0.05/A = 1.59155 m/s,
    # Re = 1.59155*0.2/1.004e-6 = 317,042, eps/D = 2.25e-4
    s = pipe_state(0.2, Q, L, EPS, NU)
    assert s["velocity_m_s"] == pytest.approx(1.59155, rel=1e-5)
    assert s["reynolds"] == pytest.approx(317_042, rel=1e-5)
    assert s["rel_roughness"] == pytest.approx(2.25e-4)
    # h_f = f * (500/0.2) * 1.59155^2 / (2*9.80665)
    expected = s["friction_factor"] * 2500 * 1.59155 ** 2 / (2 * 9.80665)
    assert s["head_loss_m"] == pytest.approx(expected, rel=1e-5)


@pytest.mark.parametrize("re, rel", [(1e4, 1e-4), (3.2e5, 2.25e-4), (1e6, 1e-3), (1e7, 1e-5)])
def test_swamee_jain_matches_colebrook_within_2_percent(re, rel):
    """Independent check: the explicit formula agrees with the implicit Colebrook equation."""
    assert friction_factor(re, rel) == pytest.approx(colebrook_friction_factor(re, rel), rel=0.02)


def test_laminar_branch_uses_64_over_re():
    assert friction_factor(1000, 1e-3) == pytest.approx(0.064)


def test_head_loss_decreases_as_diameter_grows():
    """The solver relies on this: a bigger pipe always means less head loss."""
    diameters = [d / 1000 for d in range(20, 1000, 10)]
    losses = [head_loss(d, Q, L, EPS, NU) for d in diameters]
    assert all(a > b for a, b in zip(losses, losses[1:]))


def test_matches_original_workbook_values():
    """Every trial row in the goal-seek workbook matches the Python calculation."""
    sheet = load_workbook("workbook/Pipe_Diameter_GoalSeek.xlsx", data_only=True)["GoalSeek_Log"]
    rows = [(sheet[f"B{r}"].value, sheet[f"G{r}"].value) for r in range(5, 13)]
    assert len(rows) == 8
    for d_mm, workbook_hf in rows:
        assert head_loss(d_mm / 1000, Q, L, EPS, NU) == pytest.approx(workbook_hf, rel=1e-9)
    assert math.isfinite(rows[-1][1])
