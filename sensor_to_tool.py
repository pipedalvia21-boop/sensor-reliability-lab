"""Feed the Module 4 pipe-sizing tool with the virtual temperature sensor (CSV replay).

    Velxio NTC sensor -> data/raw_readings.csv -> SensorGate (validation + 5.1 rule)
    -> water temperature -> kinematic viscosity -> solve_pipe_diameter (unchanged) -> log

Before: the user TYPED the kinematic viscosity (mm²/s).
Now:    it is calculated from the measured water temperature, one reading at a time.
All other inputs are still the typed design values in DESIGN below.

Usage (repo root):
    python sensor_to_tool.py                     # replays data/raw_readings.csv
    python sensor_to_tool.py path/to/file.csv
Writes results/sensor_to_tool_log.csv and prints a summary.
"""
import csv
import sys
from pathlib import Path

from analyze import load_serial_csv
from src.iteration import CONVERGED, solve_pipe_diameter
from src.sensor_gate import SensorGate
from src.water import kinematic_viscosity_mm2s

ROOT = Path(__file__).resolve().parent

# Typed design inputs - same defaults as the Module 4 app
DESIGN = dict(flow_lps=50.0, length_m=500.0, roughness_mm=0.045, target_head_loss_m=10.0,
              initial_diameter_mm=100.0, tolerance_m=0.01, max_iterations=60)

UNAVAILABLE_AFTER = 3   # this many non-accepted readings in a row -> sensor reported unavailable

LOG_COLUMNS = [
    "sample", "timestamp_ms", "raw_adc", "raw_temperature_c", "unit", "board_status",
    "gate_decision", "gate_reason", "value_used_temperature_c", "viscosity_mm2s",
    "tool_status", "diameter_mm", "head_loss_m", "iterations", "sensor_state", "sim_note",
]


def run_tool(decided, design=DESIGN):
    """Turn one gate decision into one log row. Only ACCEPTED readings reach the calculation."""
    row = {
        "sample": decided["sample"], "timestamp_ms": decided.get("timestamp_ms"),
        "raw_adc": decided.get("raw_adc"), "raw_temperature_c": decided.get("temperature_c"),
        "unit": decided.get("unit"), "board_status": decided.get("status"),
        "gate_decision": decided["decision"], "gate_reason": decided["reason"],
        "value_used_temperature_c": None, "viscosity_mm2s": None, "tool_status": "NOT CALCULATED",
        "diameter_mm": None, "head_loss_m": None, "iterations": None,
        "sim_note": decided.get("sim_note", ""),
    }
    if decided["decision"] != "ACCEPT":
        return row                      # no value is invented for a rejected reading

    temp = decided["temperature_c"]
    nu = kinematic_viscosity_mm2s(temp)
    result = solve_pipe_diameter(viscosity_mm2s=nu, **design)
    row.update(value_used_temperature_c=temp, viscosity_mm2s=nu, tool_status=result["status"],
               diameter_mm=result["solution_diameter_mm"], head_loss_m=result["final_head_loss_m"],
               iterations=result["iterations"])
    return row


def replay(raw_rows, design=DESIGN):
    """Replay raw readings one at a time. Returns the traceability log (one row per sample)."""
    gate, log, misses = SensorGate(), [], 0

    def emit(decided_rows):
        nonlocal misses
        for d in decided_rows:
            row = run_tool(d, design)
            misses = 0 if d["decision"] == "ACCEPT" else misses + 1
            row["sensor_state"] = "UNAVAILABLE" if misses >= UNAVAILABLE_AFTER else (
                "OK" if d["decision"] == "ACCEPT" else "DEGRADED")
            log.append(row)

    for raw in raw_rows:
        emit(gate.process(raw))
    emit(gate.flush())
    log.sort(key=lambda r: r["sample"])
    return log


def write_log(log, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_COLUMNS)
        w.writeheader()
        for r in log:
            w.writerow({k: ("" if r[k] is None else r[k]) for k in LOG_COLUMNS})


def summarize(log):
    calc = [r for r in log if r["tool_status"] == CONVERGED]
    counts = {d: sum(r["gate_decision"] == d for r in log) for d in ("ACCEPT", "REJECT", "REVIEW")}
    diam = [r["diameter_mm"] for r in calc]
    return {
        "readings": len(log), **counts,
        "calculated": len(calc),
        "not_calculated": sum(r["tool_status"] == "NOT CALCULATED" for r in log),
        "unavailable_samples": [r["sample"] for r in log if r["sensor_state"] == "UNAVAILABLE"],
        "diameter_min_mm": min(diam) if diam else None,
        "diameter_max_mm": max(diam) if diam else None,
    }


def main(argv):
    path = Path(argv[1]) if len(argv) > 1 else ROOT / "data" / "raw_readings.csv"
    raw = load_serial_csv(path)
    if not raw:
        sys.exit(f"No readings found in {path}. Check that it contains the CSV header line.")
    log = replay(raw)
    (ROOT / "results").mkdir(exist_ok=True)
    write_log(log, ROOT / "results" / "sensor_to_tool_log.csv")
    s = summarize(log)
    print(f"{s['readings']} readings | accepted {s['ACCEPT']} | rejected {s['REJECT']} | "
          f"review {s['REVIEW']}")
    print(f"Pipe tool ran {s['calculated']} times; {s['not_calculated']} readings not calculated.")
    if s["diameter_min_mm"] is not None:
        print(f"Required diameter: {s['diameter_min_mm']:.2f} - {s['diameter_max_mm']:.2f} mm")
    if s["unavailable_samples"]:
        print(f"Sensor reported UNAVAILABLE at samples {s['unavailable_samples']}")
    print("Wrote results/sensor_to_tool_log.csv")


if __name__ == "__main__":
    main(sys.argv)
