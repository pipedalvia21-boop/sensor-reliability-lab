"""Invalid input is refused before iteration, and the message names the input."""
import pytest

from src.iteration import INVALID_INPUT, solve_pipe_diameter
from src.validation import ValidationError, validate_inputs


def _inputs(base_case, **changes):
    data = dict(base_case, initial_diameter_mm=100.0, tolerance_m=0.01, max_iterations=60)
    data.update(changes)
    return data


def test_valid_inputs_pass(base_case):
    assert validate_inputs(**_inputs(base_case)) is True


@pytest.mark.parametrize("field, value", [
    ("flow_lps", -50.0),            # negative flow
    ("flow_lps", 0.0),              # zero where a positive quantity is required
    ("length_m", 0.0),
    ("roughness_mm", -0.01),
    ("viscosity_mm2s", 0.0),
    ("target_head_loss_m", -10.0),
    ("initial_diameter_mm", 0.0),
    ("initial_diameter_mm", 6_000.0),   # outside supported diameter range
    ("flow_lps", None),                 # missing input
    ("flow_lps", "50"),                 # not a number
    ("flow_lps", float("nan")),
    ("tolerance_m", 0.0),
    ("tolerance_m", 20.0),              # tolerance larger than the target itself
    ("max_iterations", 0),
    ("max_iterations", 2.5),
    ("max_iterations", True),
])
def test_invalid_input_is_rejected_and_named(base_case, field, value):
    with pytest.raises(ValidationError) as exc:
        validate_inputs(**_inputs(base_case, **{field: value}))
    assert exc.value.field == field


def test_solver_reports_invalid_input_without_iterating(base_case):
    r = solve_pipe_diameter(**_inputs(base_case, flow_lps=-50.0))
    assert r["status"] == INVALID_INPUT
    assert r["invalid_field"] == "flow_lps"
    assert "Flow rate" in r["message"]
    assert r["iterations"] == 0 and r["history"] == []
    assert r["solution_diameter_mm"] is None
