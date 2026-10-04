// Temperature Sensor Reliability Lab  (Velxio, Arduino Uno + NTC temperature sensor on A0)
//
// Sensor model: 10 kOhm NTC thermistor (Beta = 3950) in series with a 10 kOhm resistor,
// output on OUT -> A0. Conversion uses the Beta equation for that divider.
// (The previous version applied a TMP36 formula, which does not match this sensor:
//  at a true 72 C it reported about 20.7 C and labeled it "OK".)
//
// Output (CSV over Serial, 9600 baud):
//   sample,timestamp_ms,raw_adc,temperature_c,unit,status,sim_note
// status   = what the board itself can tell: OK, OUT_OF_SPEC, SENSOR_FAULT, NO_DATA
// sim_note = labels every condition this sketch injects on purpose, so the raw file is honest.
//            The analysis rule in analyze.py does NOT read this column.

#include <math.h>

const int SENSOR_PIN = A0;
const float BETA = 3950.0;              // must match the sensor's beta attribute
const int TOTAL_SAMPLES = 120;          // stop after this many rows
const unsigned long INTERVAL_MS = 500;  // 2 readings per second -> about 60 s run

// The simulator's ADC is ideal (no electrical noise). A real 10-bit ADC typically
// wanders by 1-2 counts, so +/-2 counts of noise are added to make normal variation visible.
const bool ADD_ADC_NOISE = true;
const bool INJECT_FAULTS = true;        // spikes, a dropout and a short circuit (see schedule below)

const float SPEC_MIN_C = -40.0;         // NTC module operating range
const float SPEC_MAX_C = 125.0;

int sample = 1;
bool finished = false;

float adcToCelsius(int raw) {
  // Beta equation: 1/T = ln(R/R0)/BETA + 1/T0, with R/R0 = 1 / (1023/raw - 1)
  return 1.0 / (log(1.0 / (1023.0 / raw - 1.0)) / BETA + 1.0 / 298.15) - 273.15;
}

void setup() {
  Serial.begin(9600);
  randomSeed(42);  // repeatable noise
  Serial.println("sample,timestamp_ms,raw_adc,temperature_c,unit,status,sim_note");
}

void loop() {
  if (sample > TOTAL_SAMPLES) {
    if (!finished) { Serial.println("# DONE"); finished = true; }
    return;
  }

  unsigned long t = millis();
  String note = "";

  // ---- Simulated dropout: no reading arrives (e.g. loose wire, bus timeout) ----
  if (INJECT_FAULTS && sample >= 45 && sample <= 47) {
    Serial.print(sample); Serial.print(","); Serial.print(t);
    Serial.println(",,,C,NO_DATA,injected_dropout");
    sample++;
    delay(INTERVAL_MS);
    return;
  }

  int raw = analogRead(SENSOR_PIN);
  if (ADD_ADC_NOISE) raw = constrain(raw + random(-2, 3), 0, 1023);

  // ---- Simulated electrical spikes (one sample each) ----
  if (INJECT_FAULTS && (sample == 30 || sample == 88)) { raw = constrain(raw - 150, 0, 1023); note = "injected_spike"; }
  if (INJECT_FAULTS && sample == 61)                   { raw = constrain(raw + 150, 0, 1023); note = "injected_spike"; }
  // ---- Simulated short circuit for two samples (ADC pinned at the rail) ----
  if (INJECT_FAULTS && (sample == 100 || sample == 101)) { raw = 1023; note = "injected_short"; }

  float tempC = adcToCelsius(raw);
  String status;
  if (raw <= 5 || raw >= 1018) {
    status = "SENSOR_FAULT";            // divider pinned to a rail: open or shorted sensor
  } else if (tempC < SPEC_MIN_C || tempC > SPEC_MAX_C) {
    status = "OUT_OF_SPEC";
  } else {
    status = "OK";
  }

  Serial.print(sample);        Serial.print(",");
  Serial.print(t);             Serial.print(",");
  Serial.print(raw);           Serial.print(",");
  Serial.print(tempC, 2);      Serial.print(",C,");
  Serial.print(status);        Serial.print(",");
  Serial.println(note);

  sample++;
  delay(INTERVAL_MS);
}
