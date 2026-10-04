"""Analyze the raw Velxio temperature readings and generate the lab report.

Usage (from the repo root):
    python analyze.py                       # reads data/raw_readings.csv
    python analyze.py path/to/serial_log.csv

The raw file is never modified. Outputs:
    results/classified_readings.csv   every raw row + decision + reason
    results/temperature_plot.png      readings over time, rejected ones marked
    results/summary.json              numbers used in the report
    REPORT.md                         analysis report (regenerated each run)
"""
import csv
import json
import math
import statistics
import sys
from pathlib import Path

# ----------------------------------------------------------------- rule settings
SPEC_MIN_C, SPEC_MAX_C = -40.0, 125.0   # NTC module operating range
ADC_RAIL_LOW, ADC_RAIL_HIGH = 5, 1018   # ADC pinned to a rail = open / shorted sensor
MAX_JUMP_C = 5.0                        # allowed change vs. last accepted reading (per 0.5 s sample)

ROOT = Path(__file__).resolve().parent
COLUMNS = ["sample", "timestamp_ms", "raw_adc", "temperature_c", "unit", "status", "sim_note"]


# ----------------------------------------------------------------- loading
def load_serial_csv(path):
    """Parse a Serial Monitor capture. Skips anything before the header and after '# DONE'."""
    rows, started = [], False
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("sample,"):
            started = True
            continue
        if line.startswith("# DONE"):
            break
        if not started:
            continue
        parts = next(csv.reader([line]))
        parts += [""] * (len(COLUMNS) - len(parts))
        row = dict(zip(COLUMNS, parts[:len(COLUMNS)]))
        row["sample"] = int(row["sample"])
        row["timestamp_ms"] = int(row["timestamp_ms"]) if row["timestamp_ms"] else None
        row["raw_adc"] = int(row["raw_adc"]) if row["raw_adc"] else None
        row["temperature_c"] = _to_float(row["temperature_c"])
        rows.append(row)
    return rows


def _to_float(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value  # may be inf / nan; the rule handles it


# ----------------------------------------------------------------- the rule
def classify(rows, max_jump=MAX_JUMP_C):
    """Apply the rejection rule. Returns new dicts with 'decision' and 'reason'.

    R1 MISSING      no temperature value arrived                     -> REJECT
    R2 FAULT        raw ADC at a rail (<= 5 or >= 1018)              -> REJECT
    R3 OUT_OF_SPEC  temperature outside -40..125 C or not finite     -> REJECT
    R4 SPIKE        jumps > max_jump from the last accepted reading
                    AND the next reading does not stay at the new level -> REVIEW (excluded)
    A jump that the next reading confirms is ACCEPTED as a real step change.
    """
    out = [dict(r, decision="", reason="") for r in rows]

    def basic_check(r):
        t, raw = r["temperature_c"], r["raw_adc"]
        if t is None or raw is None:
            return "REJECT", "R1 missing value"
        if raw <= ADC_RAIL_LOW or raw >= ADC_RAIL_HIGH:
            return "REJECT", f"R2 ADC at rail ({raw}) - open/shorted sensor"
        if not math.isfinite(t) or not SPEC_MIN_C <= t <= SPEC_MAX_C:
            return "REJECT", "R3 outside sensor range -40..125 C"
        return None

    for r in out:
        result = basic_check(r)
        if result:
            r["decision"], r["reason"] = result

    candidates = [r for r in out if not r["decision"]]
    last_ok = None
    for i, r in enumerate(candidates):
        t = r["temperature_c"]
        if last_ok is None or abs(t - last_ok) <= max_jump:
            r["decision"], r["reason"] = "ACCEPT", ""
            last_ok = t
            continue
        nxt = candidates[i + 1]["temperature_c"] if i + 1 < len(candidates) else None
        if nxt is not None and abs(nxt - t) <= max_jump:
            r["decision"] = "ACCEPT"
            r["reason"] = f"step change {t - last_ok:+.2f} C confirmed by next reading"
            last_ok = t
        else:
            r["decision"] = "REVIEW"
            r["reason"] = f"R4 spike {t - last_ok:+.2f} C, not confirmed by next reading"
    return out


# ----------------------------------------------------------------- analysis
def describe(values):
    if not values:
        return None
    diffs = [abs(b - a) for a, b in zip(values, values[1:])]
    return {
        "count": len(values),
        "min": min(values), "max": max(values),
        "mean": statistics.fmean(values), "median": statistics.median(values),
        "range": max(values) - min(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "median_step": statistics.median(diffs) if diffs else 0.0,
        "p95_step": sorted(diffs)[int(0.95 * (len(diffs) - 1))] if diffs else 0.0,
        "max_step": max(diffs) if diffs else 0.0,
    }


def analyze(rows):
    classified = classify(rows)
    numeric = [r["temperature_c"] for r in rows
               if r["temperature_c"] is not None and math.isfinite(r["temperature_c"])]
    accepted = [r["temperature_c"] for r in classified if r["decision"] == "ACCEPT"]
    counts = {d: sum(r["decision"] == d for r in classified) for d in ("ACCEPT", "REJECT", "REVIEW")}
    flagged = [r for r in classified if r["decision"] != "ACCEPT" or r["reason"]]
    return {
        "classified": classified,
        "total": len(rows),
        "counts": counts,
        "accepted_stats": describe(accepted),
        "all_numeric_stats": describe(numeric),
        "flagged": flagged,
        "uninjected_flags": [r for r in classified
                             if r["decision"] != "ACCEPT" and not r["sim_note"]],
        "injected_missed": [r for r in classified
                            if r["sim_note"] and r["decision"] == "ACCEPT"],
        "steps": [r for r in classified if r["decision"] == "ACCEPT" and r["reason"]],
    }


# ----------------------------------------------------------------- outputs
def write_classified(classified, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS + ["decision", "reason"])
        w.writeheader()
        for r in classified:
            row = dict(r)
            row["temperature_c"] = "" if r["temperature_c"] is None else r["temperature_c"]
            w.writerow(row)


def plot(classified, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ok = [(r["sample"], r["temperature_c"]) for r in classified if r["decision"] == "ACCEPT"]
    ax.plot(*zip(*ok), "-o", ms=3, lw=1, color="#1f5f99", label="Accepted")
    review = [(r["sample"], r["temperature_c"]) for r in classified if r["decision"] == "REVIEW"]
    if review:
        ax.plot(*zip(*review), "^", ms=9, color="#d98200", label="Review (spike)")
    lo, hi = ax.get_ylim()
    for r in classified:
        if r["decision"] == "REJECT":
            ax.axvline(r["sample"], color="#b00020", alpha=0.35, lw=2)
    ax.plot([], [], color="#b00020", alpha=0.35, lw=2, label="Rejected (missing / fault / out of range)")
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Sample number (0.5 s apart)")
    ax.set_ylabel("Temperature (°C)")
    ax.set_title("Virtual NTC temperature sensor - raw readings and rule decisions")
    ax.grid(alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float) and not math.isfinite(v):
        return str(v)
    return f"{v:.2f}" if isinstance(v, float) else str(v)


def write_report(res, path, raw_name):
    a, n = res["accepted_stats"], res["all_numeric_stats"]
    c = res["counts"]
    duration = ""
    stamps = [r["timestamp_ms"] for r in res["classified"] if r["timestamp_ms"] is not None]
    if len(stamps) > 1:
        duration = f" over about {(stamps[-1] - stamps[0]) / 1000:.0f} s of simulation time"

    flagged_rows = "\n".join(
        f"| {r['sample']} | {_fmt(r['raw_adc'])} | {_fmt(r['temperature_c'])} | {r['status']} | "
        f"{r['decision']} | {r['reason'] or '-'} | {r['sim_note'] or 'none (not injected)'} |"
        for r in res["flagged"])

    if res["uninjected_flags"]:
        cost_evidence = ("In this dataset the rule also excluded readings that were **not** injected: samples "
                         + ", ".join(str(r["sample"]) for r in res["uninjected_flags"])
                         + ". These came from moving the virtual sensor, so they are real changes that the "
                           "rule removed. That is the cost of the rule in action.")
    else:
        cost_evidence = ("In this run every excluded reading was an injected condition, so the rule did not "
                         "remove any real data here. That is a property of this dataset, not a guarantee.")
    if res["steps"]:
        cost_evidence += (" The rule also accepted " + str(len(res["steps"])) +
                          " large jump(s) as real step changes because the next reading confirmed them "
                          "(samples " + ", ".join(str(r["sample"]) for r in res["steps"]) + ").")
    missed = ""
    if res["injected_missed"]:
        missed = ("\n\n**Missed by the rule:** injected samples "
                  + ", ".join(str(r["sample"]) for r in res["injected_missed"])
                  + " were accepted. Their deviation was within the 5 °C limit, so the rule cannot tell them "
                    "from normal readings.")

    text = f"""# First Readings: Virtual Sensor Reliability Lab - Analysis Report

*Generated by `analyze.py` from `{raw_name}`. Rerun the script after collecting new data.*

## Sensor and Measurement
NTC thermistor temperature module (10 kΩ NTC, β = 3950, in series with a 10 kΩ resistor), read on Arduino Uno pin A0.
The board reports the raw 10-bit ADC count (0-1023) and the temperature in **degrees Celsius (°C)** converted with the β equation.
The module's supported range is -40 to 125 °C.

## Simulation Platform
Velxio (browser Arduino simulator). Project file: `arduino-temp-sensor-lab.vlx`. Sketch: `sketch/temperature_sensor_lab.ino`.

## Collection Method
- **Samples:** {res['total']} readings, one every 0.5 s{duration}, printed as CSV on the Serial Monitor and saved unedited in `{raw_name}`.
- **Temperature changes:** the sensor's temperature was changed by hand during the run with the component's temperature control.
- **ADC noise:** the simulator's ADC is ideal, so the sketch adds ±2 counts of noise, as a real 10-bit ADC typically shows.
- **Injected conditions:** the sketch deliberately adds three one-sample electrical spikes (samples 30, 61, 88), a three-sample dropout where no reading arrives (45-47), and a two-sample short circuit with the ADC pinned at 1023 (100-101).
- **Labeling:** every injected row is marked in the `sim_note` column. The rejection rule never reads that column, so it is used only to check how well the rule performed.

## Observed Range
| Statistic | Accepted readings ({a['count']}) | All numeric raw values ({n['count']}) |
|---|---|---|
| Minimum (°C) | {_fmt(a['min'])} | {_fmt(n['min'])} |
| Maximum (°C) | {_fmt(a['max'])} | {_fmt(n['max'])} |
| Mean (°C) | {_fmt(a['mean'])} | {_fmt(n['mean'])} |
| Median / typical (°C) | {_fmt(a['median'])} | {_fmt(n['median'])} |
| Range (°C) | {_fmt(a['range'])} | {_fmt(n['range'])} |
| Standard deviation (°C) | {_fmt(a['stdev'])} | {_fmt(n['stdev'])} |

The right-hand column shows how much a few bad readings distort the summary. The short-circuit rows convert to -273.15 °C (absolute zero), which is physically impossible.

## Normal Variation
- **Sample-to-sample change:** among accepted readings, the typical (median) change was **{a['median_step']:.2f} °C**. 95% of changes were ≤ **{a['p95_step']:.2f} °C**, and the largest accepted change was {a['max_step']:.2f} °C.
- **Noise level:** at room temperature one ADC count is about 0.1 °C, so the ±2-count noise appears as roughly ±0.2 °C of jitter.
- **Overall trend:** the larger, slower movement in the trend comes from the temperature changes made during the run.

## Suspicious Readings
| Sample | Raw ADC | Temp (°C) | Board status | Decision | Reason | Injected? |
|---|---|---|---|---|---|---|
{flagged_rows}

Why each pattern deserves investigation:
- **Missing values (NO_DATA).** No measurement arrived, so any value filled in would be invented. Three in a row point to a connection problem, not random noise.
- **ADC pinned at 1023.** The divider is at a rail, which means a shorted thermistor or wiring fault. The β equation turns this into -273.15 °C, an impossible temperature. Two in a row is a repeated failure, not noise.
- **Single-sample spikes of about 10-15 °C.** These are far larger than the observed sample-to-sample variation, and the next reading returns to the previous level. A real air or liquid temperature cannot jump that far and back within 1 second.
- **Large jumps that persist.** These are not treated as errors. If the next reading stays at the new level, the change is most likely real (in this run, the temperature control being moved).

**Finding about the original sketch:** it applied the TMP36 formula (voltage − 0.5) × 100 to an NTC divider. At the project's saved setting of 72 °C, the ADC reads about 145 counts, which that formula reports as about 20.7 °C with status "OK". An overheating condition would look normal. The original code also labeled any reading below 0 °C as "MISSING", even though cold readings are valid data. Both issues were corrected before collecting this dataset.

## Proposed Rejection / Filtering Rule
Apply these checks in order. Rejected readings stay in the raw file; they are only excluded from the trusted dataset (`results/classified_readings.csv`).
1. **R1 Missing.** No temperature value → **REJECT**.
2. **R2 Sensor fault.** Raw ADC ≤ 5 or ≥ 1018 (open or shorted sensor) → **REJECT**.
3. **R3 Out of range.** Temperature not finite or outside -40 to 125 °C → **REJECT**.
4. **R4 Unconfirmed spike.** The reading differs by more than **{MAX_JUMP_C:g} °C** from the last accepted reading, and the next reading does **not** stay within {MAX_JUMP_C:g} °C of it → **REVIEW** (excluded from statistics but kept for a person to check). If the next reading confirms the new level, the jump is **ACCEPTED** as a real step change.

The 5 °C limit is more than 20 times the typical sample-to-sample change measured above. R2 and R3 come from the sensor's documented behavior, not from this dataset.

**Result on this dataset:** {c['ACCEPT']} accepted, {c['REJECT']} rejected, {c['REVIEW']} sent to review.

## Cost of the Rule
- **Real fast events can be lost.** R4 needs the next reading to confirm a jump, so a genuine event lasting a single sample (0.5 s) is excluded. Examples are a burst of hot air or a contact transient. If the process can really change by more than 5 °C in one sample, the rule hides it.
- **Real changes are confirmed late.** A real step change is only confirmed once the following reading arrives, adding at least 0.5 s of delay.
- **Valid extremes can be removed.** R3 rejects anything outside -40 to 125 °C. A real temperature beyond the sensor's range, which is exactly when an alarm matters, would be discarded instead of reported as "too hot". A better system would raise an alarm for these readings rather than silently drop them.
- **Gaps are hidden.** Rejected rows are removed from the statistics, so the summary looks more stable than the stream really was. That is why rejected and review counts are always reported next to the statistics.
- **A slow failure passes.** A drifting or slowly failing sensor that changes less than 5 °C per sample passes every check.

{cost_evidence}{missed}

![Readings and decisions](results/temperature_plot.png)
"""
    Path(path).write_text(text, encoding="utf-8")


def main(argv):
    raw_path = Path(argv[1]) if len(argv) > 1 else ROOT / "data" / "raw_readings.csv"
    rows = load_serial_csv(raw_path)
    if len(rows) < 100:
        print(f"WARNING: only {len(rows)} readings found; the lab needs at least 100.")
    res = analyze(rows)
    (ROOT / "results").mkdir(exist_ok=True)
    write_classified(res["classified"], ROOT / "results" / "classified_readings.csv")
    plot(res["classified"], ROOT / "results" / "temperature_plot.png")
    summary = {k: res[k] for k in ("total", "counts", "accepted_stats", "all_numeric_stats")}
    (ROOT / "results" / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    try:
        raw_name = raw_path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        raw_name = raw_path.name
    write_report(res, ROOT / "REPORT.md", raw_name)
    a = res["accepted_stats"]
    print(f"{res['total']} readings | accepted {res['counts']['ACCEPT']} | "
          f"rejected {res['counts']['REJECT']} | review {res['counts']['REVIEW']}")
    print(f"Accepted: min {a['min']:.2f}  max {a['max']:.2f}  median {a['median']:.2f}  "
          f"range {a['range']:.2f} C")
    print("Wrote REPORT.md and results/")


if __name__ == "__main__":
    main(sys.argv)
