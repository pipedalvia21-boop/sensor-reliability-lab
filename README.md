# Virtual Sensor Lab - Readings (5.1) and Feeding the Tool (5.2)

Which readings from a sensor should software trust? This project collects 100+ readings from a **virtual NTC temperature sensor** in **Velxio**, keeps every raw value, and applies a documented rejection rule. It also reports what that rule might wrongly remove.

## Sensor and Units
| Item | Value |
|---|---|
| Board | Arduino Uno (Velxio simulation) |
| Sensor | NTC thermistor module: 10 kΩ NTC, β = 3950, in series with 10 kΩ |
| Wiring | 5V → VCC, GND → GND, OUT → A0 |
| Raw value | 10-bit ADC count, 0-1023 (no unit) |
| Measured value | Temperature in **°C** (β equation) |
| Supported range | -40 to 125 °C |
| Sample rate | 1 reading every 0.5 s, 120 readings per run |

## Repository Layout
```
sensor_to_tool.py                5.2: replays the sensor CSV into the pipe-sizing tool
src/sensor_gate.py               5.2: validation + 5.1 rule, one reading at a time
src/water.py                     5.2: water temperature -> kinematic viscosity
src/calculation.py, validation.py, iteration.py   Module 4 pipe tool (unchanged)
workbook/Pipe_Diameter_GoalSeek.xlsx              Module 4 reference workbook (used by its tests)
results/sensor_to_tool_log.csv   5.2: raw -> decision -> value used -> result, per sample
arduino-temp-sensor-lab.vlx      Velxio project (import this) - corrected sketch, sensor starts at 24 °C
sketch/temperature_sensor_lab.ino  Same sketch as plain code
data/raw_readings.csv            Raw Serial Monitor output, never edited
analyze.py                       Rule + statistics + plot + report generator
results/                         classified_readings.csv, temperature_plot.png, summary.json
REPORT.md                        Analysis report (generated from the data)
evidence/                        Circuit screenshot
tests/test_analyze.py            Tests for the parser and the rejection rule
```

## Collection Method
1. **Import the project.** Open Velxio (https://velxio.dev) and import `arduino-temp-sensor-lab.vlx`.
2. **Set the sensor.** Set its temperature control to 24 °C.
3. **Run.** Start the simulation. The sketch prints 120 CSV rows (one every 0.5 s) and then `# DONE`.
4. **Save the output.** Copy the Serial Monitor output, unedited, into `data/raw_readings.csv`.
5. **Take the screenshot.** Save a screenshot of the running circuit as `evidence/circuit.png`.

The true input was constant at 24 °C, so all normal variation in the data is ADC noise.

The sketch also injects the conditions the lab requires, and labels every one in the `sim_note` column so the raw data stays honest:
- **Spikes:** three one-sample electrical spikes at samples 30, 61 and 88.
- **Dropout:** no data at samples 45-47.
- **Short circuit:** the ADC is pinned at 1023 at samples 100-101.
- **ADC noise:** ±2 counts are added, because the simulator's ADC is perfectly clean.

The rule never reads `sim_note`. That column is used only to check the rule afterwards.

## Analyze
```bash
pip install -r requirements.txt
python analyze.py          # writes REPORT.md and results/
python -m pytest -v        # 11 tests for the parser and the rule
```

## Rejection Rule (summary)
| Rule | Condition | Decision |
|---|---|---|
| R1 | No value arrived | REJECT |
| R2 | ADC ≤ 5 or ≥ 1018 (open/shorted sensor) | REJECT |
| R3 | Not finite, or outside -40 to 125 °C | REJECT |
| R4 | Jump > 5 °C from the last accepted value, and the next reading does not confirm it | REVIEW (excluded) |
| - | Jump > 5 °C that the next reading confirms | ACCEPT as a real step change |

See `REPORT.md` for the full reasoning and the cost of the rule.

## Note on the Original Sketch
The starter code converted the reading with the TMP36 formula `(V − 0.5) × 100`, which does not match an NTC divider. At the saved setting of 72 °C, it reported about **20.7 °C "OK"**. It also labeled every temperature below 0 °C as "MISSING". Both were fixed before data collection.

## Virtual Project Link
_Paste the shareable Velxio link here, if available._

---

# Assignment 5.2 - Feed the Tool

## Which Tool and Which Input
- **Tool:** the Module 4 pipe-diameter sizing tool (`src/calculation.py`, `src/validation.py` and `src/iteration.py`), copied in **unchanged** together with its tests.
- **Input replaced:** the tool finds the pipe diameter that gives a target friction head loss. Its typed input **kinematic viscosity (mm²/s)** is now calculated from the **measured water temperature**, because viscosity is set by the temperature of the water in the pipe.
- **Inputs still typed:** flow 50 L/s, length 500 m, roughness 0.045 mm, target 10 m, D₀ 100 mm, tolerance 0.01 m and 60 iterations. These are the Module 4 defaults, kept in `DESIGN` in `sensor_to_tool.py`.

## Integration Method: CSV Replay (Option A)
```
Velxio NTC sensor -> data/raw_readings.csv -> SensorGate -> water temperature
  -> kinematic viscosity (src/water.py) -> solve_pipe_diameter (unchanged) -> log
```
```bash
python sensor_to_tool.py      # writes results/sensor_to_tool_log.csv
```
Readings are fed to the gate **one at a time**, in order, as they would arrive from a live sensor.

## Temperature → Viscosity
- **Dynamic viscosity:** Vogel equation, μ = 2.414×10⁻⁵ · 10^(247.8 / (T − 140)) Pa·s, with T in kelvin.
- **Density:** Thiesen-type fit for liquid water.
- **Kinematic viscosity:** ν = μ / ρ.
- **Verification:** the result matches standard table values at 10, 20, 40, 60 and 80 °C within 2%. At 20 °C it gives 1.004 mm²/s, the exact viscosity of the verified Module 4 reference case (D = 176.21 mm). A test confirms the sensor path reproduces that answer.

## Validation and Filtering Rules
Every reading passes through `SensorGate` before it can reach the tool:

| Rule | Condition | Decision | Origin |
|---|---|---|---|
| U | Unit is not `C` | REJECT | 5.2 |
| S | Timestamp missing, or not newer than the previous row (stale) | REJECT | 5.2 |
| R1 | No value | REJECT | 5.1 |
| R2 | ADC ≤ 5 or ≥ 1018 (open/shorted sensor) | REJECT | 5.1 |
| R3 | Outside the sensor range, -40 to 125 °C | REJECT | 5.1 |
| R5 | Outside the tool range: liquid water needs 0 < T < 100 °C | REJECT | 5.2 |
| R4 | Jump > 5 °C from the last accepted value that the next valid reading does not confirm | REVIEW | 5.1 |

**The 5.1 rule (R1-R4).** Its thresholds are imported from `analyze.py`, so the 5.1 analysis and the tool always use the same numbers. A test confirms the one-at-a-time gate makes exactly the same decision as the 5.1 batch rule for all 120 readings.
- **Why:** the 5.1 data showed normal variation of ±0.2 °C, while the faults were missing values, rail values and ±13-14 °C single-sample spikes.
- **Accepted:** the reading passes R1-R3 and R5, and either stays within 5 °C of the last accepted value or is a jump that the next valid reading confirms.
- **Rejected:** a reading that fails R1, R2, R3 or R5 is REJECTED. A jump the next reading does not confirm goes to REVIEW.
- **Effect of R4 in live use:** a jump can only be judged once the next valid reading arrives, so the decision for a jumping reading comes one sample (0.5 s) later.

**Why R5 was needed.** Module 4 validation checks that viscosity is between 0.1 and 1,000 mm²/s. It never had to ask whether the fluid is liquid water. A reading of 110 °C is valid for the sensor, but the water would be steam, so R5 stops it before the viscosity formula is used.

## What Happens to Rejected Data
- **No calculation.** A REJECT or REVIEW reading never reaches the solver. Its log row keeps the raw values and the reason, and shows `tool_status = NOT CALCULATED` with empty value, viscosity and diameter.
- **No substitution.** No value is invented or carried forward: the last valid reading is **not** reused, so no freshness rule is needed.
- **Missing input.** Each missing reading is marked `DEGRADED`. After 3 non-accepted readings in a row, the log marks the sensor `UNAVAILABLE` (sample 47 in this dataset) until a valid reading arrives.

## Traceability Log
`results/sensor_to_tool_log.csv` has one row per sample, in this order of columns:
```
raw_adc, raw_temperature_c, unit  ->  gate_decision, gate_reason  ->  value_used_temperature_c, viscosity_mm2s
  ->  tool_status, diameter_mm, head_loss_m, iterations  ->  sensor_state
```

## Results on the 5.1 Dataset
- **Gate decisions:** 120 readings: 112 ACCEPT, 5 REJECT (dropout 45-47, short circuit 100-101) and 3 REVIEW (spikes 30, 61, 88).
- **Tool runs:** the pipe tool ran 112 times and every run converged. The required diameter stayed between **175.93 and 175.98 mm**.
- **What the noise does:** the ±0.2 °C noise moves the diameter by about 0.05 mm, which is below the solver's own tolerance. Noise does not matter for this tool.
- **What the faults would do:** a 38 °C spike would have produced 175.10 mm and a 10.8 °C spike 177.05 mm. A -273.15 °C short-circuit reading would have stopped the calculation with an error. The faults, not the noise, are what the gate must stop.

## Assumptions Broken by Sensor Input
| Original Assumption | What the Sensor Did | Software Change |
|---|---|---|
| Viscosity is typed once and stays fixed | Water temperature arrives every 0.5 s, so viscosity changes with every sample | Viscosity is calculated from each accepted reading (`src/water.py`), and the tool runs once per reading |
| Input always exists | Samples 45-47 arrived with no value | R1 rejects; no calculation and no value reuse; sensor marked `UNAVAILABLE` after 3 misses |
| Input is physically possible | The short circuit reported -273.15 °C (samples 100-101) | R2 rail check rejects it before the viscosity formula runs |
| A value inside the tool's numeric limits is valid | A sensor-valid temperature (e.g. 110 °C) would mean steam; Module 4 only checked the viscosity range | R5 liquid-water range check (0 < T < 100 °C) |
| Input is stable; a change is a deliberate edit | Single-sample spikes of ±13-14 °C (samples 30, 61, 88) | R4 one-sample confirmation; unconfirmed jumps go to REVIEW and are not used |
| Input is current | A repeated or delayed reading could be reused as if new | S rule: timestamps must increase, otherwise the reading is rejected as stale |
| The unit is what the form label says | Serial text carries its own unit field | U rule: unit must be `C` |
| One input gives one answer that the user sees | 120 samples per minute, each with its own result | A per-sample log keeps the raw value, decision, value used and result together |

## Tests
`python -m pytest -v` runs 78 tests:
- **5.1 parser and rule:** 11 tests.
- **Module 4 tool:** 43 tests, unchanged.
- **5.2 integration:** 24 tests, covering:
  - a normal reading, normal variation and the boundaries (0, 0.1, 99.9 and 100 °C, and a jump of exactly 5 °C);
  - out-of-range values (110 °C and 130 °C), a spike, a confirmed step change, a missing reading and 3 misses in a row;
  - a rail fault, a stale reading, a wrong unit and preserved raw values;
  - streaming vs. batch equivalence on the real dataset;
  - a valid reading flowing through the unchanged solver to the verified 176.21 mm answer.

## Limitations
- **CSV replay only.** Live serial input is not connected.
- **Diameter only.** The tool reports an exact inside diameter, not a catalogue pipe size, the same as in Module 4.
- **Constant input.** The 5.1 dataset had a constant 24 °C input, so a real temperature change through the tool is covered only by the simulated-reading tests.
