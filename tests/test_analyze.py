"""Tests for the parsing and rejection rule in analyze.py."""
import math
from pathlib import Path

import pytest

from analyze import MAX_JUMP_C, analyze, classify, load_serial_csv

SERIAL = """\
Velxio serial monitor
sample,timestamp_ms,raw_adc,temperature_c,unit,status,sim_note
1,0,512,25.00,C,OK,
2,500,511,25.10,C,OK,
3,1000,358,39.60,C,OK,injected_spike
4,1500,513,24.90,C,OK,
5,2000,,,C,NO_DATA,injected_dropout
6,2500,1023,-273.15,C,SENSOR_FAULT,injected_short
7,3000,310,45.00,C,OK,
8,3500,309,45.10,C,OK,
9,4000,0,-273.15,C,SENSOR_FAULT,
# DONE
10,4500,512,25.00,C,OK,
"""


@pytest.fixture
def rows(tmp_path):
    f = tmp_path / "serial.csv"
    f.write_text(SERIAL)
    return load_serial_csv(f)


def decisions(rows):
    return {r["sample"]: (r["decision"], r["reason"]) for r in classify(rows)}


def test_parser_skips_junk_and_stops_at_done(rows):
    assert [r["sample"] for r in rows] == list(range(1, 10))
    assert rows[4]["temperature_c"] is None and rows[4]["raw_adc"] is None


def test_normal_variation_accepted(rows):
    d = decisions(rows)
    assert d[1][0] == d[2][0] == d[4][0] == "ACCEPT"


def test_missing_rejected(rows):
    assert decisions(rows)[5] == ("REJECT", "R1 missing value")


def test_rail_values_rejected_as_fault(rows):
    d = decisions(rows)
    assert d[6][0] == "REJECT" and d[6][1].startswith("R2")
    assert d[9][0] == "REJECT" and d[9][1].startswith("R2")


def test_unconfirmed_spike_goes_to_review(rows):
    decision, reason = decisions(rows)[3]
    assert decision == "REVIEW" and reason.startswith("R4")


def test_confirmed_step_change_is_kept(rows):
    decision, reason = decisions(rows)[7]
    assert decision == "ACCEPT" and "step change" in reason


def test_jump_exactly_at_limit_is_accepted():
    base = [{"sample": i, "raw_adc": 500, "temperature_c": t, "sim_note": "", "status": "OK"}
            for i, t in enumerate([20.0, 20.0 + MAX_JUMP_C, 20.0], start=1)]
    assert [r["decision"] for r in classify(base)] == ["ACCEPT"] * 3


def test_out_of_spec_and_non_finite_rejected():
    base = [{"sample": 1, "raw_adc": 500, "temperature_c": 130.0, "sim_note": "", "status": "OK"},
            {"sample": 2, "raw_adc": 500, "temperature_c": math.inf, "sim_note": "", "status": "OK"}]
    assert all(r["reason"].startswith("R3") for r in classify(base))


def test_spike_does_not_shift_baseline(rows):
    """After a spike, the next reading is compared with the last ACCEPTED value, not the spike."""
    assert decisions(rows)[4][0] == "ACCEPT"


def test_statistics_exclude_bad_rows(rows):
    res = analyze(rows)
    a = res["accepted_stats"]
    assert a["min"] == pytest.approx(24.9) and a["max"] == pytest.approx(45.1)
    assert res["all_numeric_stats"]["min"] == pytest.approx(-273.15)   # shows the distortion
    assert res["counts"] == {"ACCEPT": 5, "REJECT": 3, "REVIEW": 1}


def test_raw_file_is_not_modified(tmp_path):
    f = tmp_path / "serial.csv"
    f.write_text(SERIAL)
    analyze(load_serial_csv(f))
    assert f.read_text() == SERIAL
