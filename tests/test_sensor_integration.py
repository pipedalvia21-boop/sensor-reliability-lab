"""Sensor -> gate -> water properties -> original pipe solver (Assignment 5.2)."""
import math
from pathlib import Path

import pytest

from analyze import classify, load_serial_csv
from sensor_to_tool import DESIGN, replay, run_tool
from src.calculation import head_loss, to_si
from src.iteration import CONVERGED, solve_pipe_diameter
from src.sensor_gate import SensorGate
from src.water import kinematic_viscosity_mm2s

ROOT = Path(__file__).resolve().parent.parent


def reading(sample, temp, raw=523, ts=None, unit="C"):
    """A simulated sensor row in the same shape the CSV parser produces."""
    return {"sample": sample, "timestamp_ms": (sample - 1) * 500 if ts is None else ts,
            "raw_adc": None if temp is None else raw, "temperature_c": temp, "unit": unit,
            "status": "OK", "sim_note": ""}


def run(temps, **kw):
    return {r["sample"]: r for r in replay([reading(i, t, **kw) for i, t in enumerate(temps, 1)])}


# ---------------------------------------------------------------- water property bridge
@pytest.mark.parametrize("temp_c, ref_mm2s", [(10, 1.306), (20, 1.004), (40, 0.658),
                                              (60, 0.474), (80, 0.365)])
def test_viscosity_matches_reference_table(temp_c, ref_mm2s):
    """Correlation vs. standard water-property table values, within 2%."""
    assert kinematic_viscosity_mm2s(temp_c) == pytest.approx(ref_mm2s, rel=0.02)


def test_viscosity_refuses_non_liquid_water():
    for t in (0.0, 100.0, -5.0):
        with pytest.raises(ValueError):
            kinematic_viscosity_mm2s(t)


# ---------------------------------------------------------------- required cases
def test_normal_reading_flows_through_original_calculation():
    """A valid reading reaches solve_pipe_diameter UNCHANGED and the answer is physically right."""
    row = run([20.0])[1]
    assert row["gate_decision"] == "ACCEPT" and row["tool_status"] == CONVERGED
    direct = solve_pipe_diameter(viscosity_mm2s=kinematic_viscosity_mm2s(20.0), **DESIGN)
    assert row["diameter_mm"] == direct["solution_diameter_mm"]
    # 20 °C water is the Module 4 reference case (nu = 1.004 mm²/s -> D = 176.21 mm)
    assert row["diameter_mm"] == pytest.approx(176.21, abs=0.1)
    q, eps, nu = to_si(DESIGN["flow_lps"], DESIGN["roughness_mm"], row["viscosity_mm2s"])
    assert abs(head_loss(row["diameter_mm"] / 1000, q, DESIGN["length_m"], eps, nu) - 10.0) <= 0.01


def test_normal_variation_is_accepted_and_calculated():
    rows = run([23.82, 24.08, 24.17, 23.90, 23.99])
    assert all(r["gate_decision"] == "ACCEPT" and r["tool_status"] == CONVERGED for r in rows.values())


@pytest.mark.parametrize("temp, accepted", [(0.0, False), (0.1, True), (99.9, True), (100.0, False)])
def test_tool_range_boundaries(temp, accepted):
    """Water must be liquid: 0 and 100 °C are rejected, values just inside are accepted."""
    row = run([temp])[1]
    assert (row["gate_decision"] == "ACCEPT") is accepted
    if not accepted:
        assert row["gate_reason"].startswith("R5")


def test_jump_exactly_at_limit_is_accepted():
    rows = run([24.0, 29.0, 29.0])                       # +5.0 °C = MAX_JUMP_C
    assert rows[2]["gate_decision"] == "ACCEPT" and rows[2]["gate_reason"] == ""


def test_out_of_range_values_are_rejected_without_calculation():
    rows = run([24.0, 110.0, 130.0])
    assert rows[2]["gate_reason"].startswith("R5")       # valid for the sensor, not for water
    assert rows[3]["gate_reason"].startswith("R3")       # outside the sensor itself
    assert rows[2]["tool_status"] == rows[3]["tool_status"] == "NOT CALCULATED"


def test_suspicious_spike_goes_to_review_and_is_not_used():
    rows = run([24.0, 24.1, 38.0, 24.0])
    assert rows[3]["gate_decision"] == "REVIEW"
    assert rows[3]["value_used_temperature_c"] is None and rows[3]["diameter_mm"] is None
    assert rows[4]["gate_decision"] == "ACCEPT"          # baseline was not shifted by the spike


def test_confirmed_step_change_is_used():
    rows = run([24.0, 40.0, 40.2])
    assert rows[2]["gate_decision"] == "ACCEPT" and "step change" in rows[2]["gate_reason"]
    assert rows[2]["viscosity_mm2s"] == pytest.approx(kinematic_viscosity_mm2s(40.0))


def test_missing_reading_is_not_invented():
    rows = run([24.0, None, 24.1])
    miss = rows[2]
    assert miss["gate_reason"] == "R1 missing value"
    assert miss["value_used_temperature_c"] is None and miss["viscosity_mm2s"] is None
    assert miss["diameter_mm"] is None and miss["tool_status"] == "NOT CALCULATED"


def test_three_misses_in_a_row_mark_sensor_unavailable():
    rows = run([24.0, None, None, None, 24.0])
    assert [rows[i]["sensor_state"] for i in range(1, 6)] == \
        ["OK", "DEGRADED", "DEGRADED", "UNAVAILABLE", "OK"]


def test_rail_fault_is_rejected():
    row = run([24.0, -273.15], raw=1023)[2]
    assert row["gate_reason"].startswith("R2")


def test_stale_and_wrong_unit_are_rejected():
    gate = SensorGate()
    gate.process(reading(1, 24.0, ts=1000))
    stale = gate.process(reading(2, 24.0, ts=1000))[0]   # timestamp did not advance
    wrong_unit = gate.process(reading(3, 75.2, ts=1500, unit="F"))[0]
    assert stale["reason"].startswith("S stale") and wrong_unit["reason"].startswith("U ")


def test_raw_values_are_preserved_next_to_decision():
    row = run([24.0, 38.0])[2]                           # unconfirmed at end of data
    assert row["raw_temperature_c"] == 38.0 and row["raw_adc"] == 523
    assert row["gate_decision"] == "REVIEW" and "data ended" in row["gate_reason"]


# ---------------------------------------------------------------- consistency with 5.1
def test_streaming_gate_matches_5_1_batch_rule_on_real_dataset():
    raw = load_serial_csv(ROOT / "data" / "raw_readings.csv")
    assert len(raw) == 120
    batch = {r["sample"]: r["decision"] for r in classify(raw)}
    stream = {r["sample"]: r["gate_decision"] for r in replay(raw)}
    assert stream == batch


def test_every_sample_has_exactly_one_log_row_in_order():
    raw = load_serial_csv(ROOT / "data" / "raw_readings.csv")
    log = replay(raw)
    assert [r["sample"] for r in log] == list(range(1, 121))
    assert all((r["diameter_mm"] is not None) == (r["gate_decision"] == "ACCEPT") for r in log)
    assert all(math.isfinite(r["diameter_mm"]) for r in log if r["diameter_mm"] is not None)


def test_run_tool_never_calls_solver_for_rejected_rows(monkeypatch):
    called = []
    monkeypatch.setattr("sensor_to_tool.solve_pipe_diameter", lambda **k: called.append(k))
    run_tool({"sample": 1, "decision": "REJECT", "reason": "R1 missing value"})
    assert called == []
