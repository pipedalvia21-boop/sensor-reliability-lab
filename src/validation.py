"""Input validation. Runs BEFORE the iterative solver starts.

Every rule raises ValidationError naming the offending input, so the
interface can tell the user exactly what to fix.
"""
import math

# field: (label, unit, min, max, min_inclusive)
SUPPORTED_RANGES = {
    "flow_lps":            ("Flow rate", "L/s", 0.0, 5_000.0, False),
    "length_m":            ("Pipe length", "m", 0.0, 100_000.0, False),
    "roughness_mm":        ("Absolute roughness", "mm", 0.0, 10.0, True),
    "viscosity_mm2s":      ("Kinematic viscosity", "mm²/s", 0.1, 1_000.0, True),
    "target_head_loss_m":  ("Target head loss", "m", 0.0, 1_000.0, False),
    "initial_diameter_mm": ("Starting diameter", "mm", 1.0, 5_000.0, True),
}
DIAMETER_MIN_MM = 1.0       # the solver never searches outside this range
DIAMETER_MAX_MM = 5_000.0
MAX_ITERATIONS_LIMIT = 1_000


class ValidationError(ValueError):
    """Raised when an input breaks a supported rule. `field` names the input."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


def _number(field, label, value):
    if value is None:
        raise ValidationError(field, f"{label} is required.")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(field, f"{label} must be a number; received {value!r}.")
    if not math.isfinite(value):
        raise ValidationError(field, f"{label} must be a finite number; received {value}.")
    return float(value)


def validate_inputs(*, flow_lps, length_m, roughness_mm, viscosity_mm2s,
                    target_head_loss_m, initial_diameter_mm, tolerance_m, max_iterations):
    """Return True if every input is supported; otherwise raise ValidationError."""
    values = {
        "flow_lps": flow_lps, "length_m": length_m, "roughness_mm": roughness_mm,
        "viscosity_mm2s": viscosity_mm2s, "target_head_loss_m": target_head_loss_m,
        "initial_diameter_mm": initial_diameter_mm,
    }
    for field, raw in values.items():
        label, unit, lo, hi, lo_inclusive = SUPPORTED_RANGES[field]
        value = _number(field, label, raw)
        too_low = value < lo if lo_inclusive else value <= lo
        if too_low or value > hi:
            op = "≥" if lo_inclusive else ">"
            raise ValidationError(
                field, f"{label} must be {op} {lo:g} and ≤ {hi:g} {unit}; received {value:g} {unit}.")

    tol = _number("tolerance_m", "Tolerance", tolerance_m)
    if tol <= 0:
        raise ValidationError("tolerance_m", f"Tolerance must be > 0 m; received {tol:g} m.")
    if tol >= target_head_loss_m:
        raise ValidationError(
            "tolerance_m",
            f"Tolerance ({tol:g} m) must be smaller than the target head loss ({target_head_loss_m:g} m).")

    if max_iterations is None:
        raise ValidationError("max_iterations", "Maximum iterations is required.")
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int):
        raise ValidationError("max_iterations",
                              f"Maximum iterations must be a whole number; received {max_iterations!r}.")
    if not 1 <= max_iterations <= MAX_ITERATIONS_LIMIT:
        raise ValidationError("max_iterations",
                              f"Maximum iterations must be between 1 and {MAX_ITERATIONS_LIMIT}; "
                              f"received {max_iterations}.")
    return True
