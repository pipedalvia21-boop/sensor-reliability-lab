# EGN 321 — Module 2 Conversion Module

## Purpose

`src/units.py` is a reusable unit-conversion library for EGN 321. Later
tools in this course (tank/volume calculations, pump pressure
calculations, sensor-processing workflows) import this module instead
of re-implementing conversion math. The design rule that shapes every
function here is:

**Convert once at the system boundary, then keep the internal
calculation in a single, consistent unit system.**

Because later assignments depend on this file, every function is kept
small, explicitly named, documented, and backed by tests whose
expected values come from an independent source (the course-provided
`UNIT_CONVERSIONS_reference.xlsx` workbook and NIST references), not
from the function being tested.

## Supported Conversions

| Function | Input Unit | Output Unit | Notes |
|---|---|---|---|
| `inches_to_feet()` | in | ft | Length |
| `feet_to_inches()` | ft | in | Length |
| `cubic_feet_to_gallons()` | ft^3 | US gal | Volume |
| `gallons_to_cubic_feet()` | US gal | ft^3 | Volume |
| `kpa_to_psi()` | kPa | psi | Pressure — required by Assignment 2.2 pump workbook |
| `psi_to_kpa()` | psi | kPa | Pressure |
| `fahrenheit_to_celsius()` | °F | °C | Temperature — later sensor work |
| `celsius_to_fahrenheit()` | °C | °F | Temperature |
| `gpm_to_lpm()` | US gal/min | L/min | Flow — later pump/instrument work |
| `lpm_to_gpm()` | L/min | US gal/min | Flow |

## Design Rules

- Every function name states both the source and destination unit
  (`inches_to_feet`, not `convert`).
- Each function performs exactly one conversion and does nothing
  else — no `input()`, no `print()`, no validation.
- Every fixed conversion factor is a named constant
  (`INCHES_PER_FOOT`, `GALLONS_PER_CUBIC_FOOT`, `KPA_PER_PSI`,
  `LITERS_PER_GALLON`) defined once at the top of `units.py`, rather
  than a repeated magic number.
- Conversion and validation are kept separate. For example,
  `inches_to_feet(-12)` returns `-1.0` without complaint — whether a
  negative length is acceptable for a specific tank is a decision for
  the validation/calculation layer built in Assignment 2.2, not for
  this module.

## Conversion Sources

All factors were verified against `UNIT_CONVERSIONS_reference.xlsx`
("Conversion Requirements" sheet) and NIST, and are the same factors
listed in `CONVERSION_REFERENCE.md`:

| Constant | Value | Source |
|---|---|---|
| `INCHES_PER_FOOT` | 12.0 | Exact, by definition |
| `GALLONS_PER_CUBIC_FOOT` | 7.48052 | NIST unit-conversion reference |
| `KPA_PER_PSI` | 6.89476 | NIST unit-conversion reference |
| `LITERS_PER_GALLON` | 3.785411784 | Exact, by definition (US gallon) |
| Fahrenheit ↔ Celsius | `(F - 32) * 5/9` and `C * 9/5 + 32` | Exact, by definition |

- NIST Unit Conversion: https://www.nist.gov/pml/owm/metric-si/unit-conversion
- NIST SI Units: https://www.nist.gov/pml/owm/metric-si/si-units

## Running the Tests

```bash
pip install -r requirements.txt
pytest
```

All 17 tests pass as of the last run.

## Test Strategy

Expected values in `tests/test_units.py` are taken directly from the
"Reference Test Data" sheet of `UNIT_CONVERSIONS_reference.xlsx`
(Test IDs T01–T14 are noted in the relevant test docstrings), which is
independent evidence — the tests never call a function to generate
its own expected answer.

- **Known-value tests (8):** verify each conversion against an
  independently known result (e.g., 12 in = 1 ft; 32 °F = 0 °C;
  100 kPa ≈ 14.5038 psi).
- **Reverse tests (4):** verify that the paired conversion in the
  opposite direction also matches an independent expected value
  (e.g., 2.5 ft = 30 in; 25 °C = 77 °F).
- **Round-trip tests (2):** convert a value forward and back
  (inches→feet→inches; psi→kPa→psi) and confirm the restored value
  matches the original within floating-point tolerance
  (`pytest.approx`).
- **Zero-value tests (2):** confirm that converting zero returns zero
  where that is physically meaningful (0 in → 0 ft; 0 ft → 0 in).

## Reuse in Later Modules

Later tools should import directly from this module rather than
duplicating conversion math:

```python
from src.units import inches_to_feet, kpa_to_psi
```

Any new EGN 321 tool that receives a value in a unit other than the
tool's internal working unit should call the appropriate function
from `units.py` once, at the point the value enters the tool (the
"boundary"), and then work exclusively in the internal unit from
that point on.

## Known Limitations

- Pressure, volume, and flow constants (`7.48052`, `6.89476`,
  `3.785411784`) are finite-precision approximations/definitions of
  real physical relationships; results are accurate to the precision
  of those constants, not to arbitrary precision.
- No input validation or type checking is performed — passing a
  non-numeric value will raise a standard Python `TypeError` from the
  arithmetic itself, not a custom error message.
- No engineering-context validation (e.g., rejecting a negative
  volume) is performed here by design; see the "Design Rules" section
  above.

## AI Use

Generative AI (Claude) was used to help draft this module and its
test suite from the assignment guide and the course-provided
`UNIT_CONVERSIONS_reference.xlsx` workbook. All conversion factors
were checked against the workbook's "Conversion Requirements" sheet
and against NIST, and every test's expected value was cross-checked
against the workbook's independent "Reference Test Data" sheet before
being accepted. See `AI_LOG.md` for details.
