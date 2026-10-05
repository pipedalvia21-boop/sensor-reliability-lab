"""Sensor gate: decides, reading by reading, whether a sensor value may enter the pipe tool.

It applies the Assignment 5.1 rule (R1-R4, thresholds imported from analyze.py so the
two can never drift apart) plus three checks that only matter once the value feeds a tool:

    U   unit is not "C"                                 -> REJECT
    S   timestamp missing or not newer than the last row (stale) -> REJECT
    R1  missing value                                   -> REJECT
    R2  ADC at a rail (open / shorted sensor)           -> REJECT
    R3  outside the sensor range -40..125 °C            -> REJECT
    R5  outside the tool range: liquid water, 0..100 °C exclusive -> REJECT
    R4  jump > MAX_JUMP_C from last accepted value, not confirmed by the next reading -> REVIEW

Readings are processed one at a time. R4 needs to see the next valid reading, so a
reading that jumps is HELD and decided when the next valid reading arrives
(one-sample delay). flush() decides anything still held when the data ends.
"""
import math

from analyze import ADC_RAIL_HIGH, ADC_RAIL_LOW, MAX_JUMP_C, SPEC_MAX_C, SPEC_MIN_C
from src.water import WATER_MAX_C, WATER_MIN_C

EXPECTED_UNIT = "C"


class SensorGate:
    def __init__(self, max_jump=MAX_JUMP_C):
        self.max_jump = max_jump
        self.last_accepted = None      # temperature of the last ACCEPTED reading
        self.last_timestamp = None     # timestamp of the last row seen (any status)
        self.held = None               # reading waiting for confirmation (R4)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _decided(row, decision, reason):
        return dict(row, decision=decision, reason=reason)

    def _absolute_checks(self, row):
        """Checks that need only this reading. Returns a reason string, or None if it passes."""
        if row.get("unit") != EXPECTED_UNIT:
            return f"U unexpected unit {row.get('unit')!r} (expected 'C')"
        ts = row.get("timestamp_ms")
        if ts is None:
            return "S no timestamp"
        if self.last_timestamp is not None and ts <= self.last_timestamp:
            return f"S stale: timestamp {ts} ms is not newer than {self.last_timestamp} ms"
        t, raw = row.get("temperature_c"), row.get("raw_adc")
        if t is None or raw is None:
            return "R1 missing value"
        if raw <= ADC_RAIL_LOW or raw >= ADC_RAIL_HIGH:
            return f"R2 ADC at rail ({raw}) - open/shorted sensor"
        if not math.isfinite(t) or not SPEC_MIN_C <= t <= SPEC_MAX_C:
            return "R3 outside sensor range -40..125 C"
        if not WATER_MIN_C < t < WATER_MAX_C:
            return "R5 outside tool range: liquid water needs 0 < T < 100 C"
        return None

    # ------------------------------------------------------------------ main API
    def process(self, row):
        """Feed one raw reading. Returns the list of readings decided by this call (0-2 items)."""
        out = []
        reason = self._absolute_checks(row)
        if row.get("timestamp_ms") is not None and (
                self.last_timestamp is None or row["timestamp_ms"] > self.last_timestamp):
            self.last_timestamp = row["timestamp_ms"]

        if reason:                      # rejected rows never confirm or cancel a held reading
            out.append(self._decided(row, "REJECT", reason))
            return out

        t = row["temperature_c"]
        if self.held is not None:       # this reading decides the held one
            held_t = self.held["temperature_c"]
            if abs(t - held_t) <= self.max_jump:
                out.append(self._decided(self.held, "ACCEPT",
                                         f"step change {held_t - self.last_accepted:+.2f} C "
                                         "confirmed by next reading"))
                self.last_accepted = held_t
            else:
                out.append(self._decided(self.held, "REVIEW",
                                         f"R4 spike {held_t - self.last_accepted:+.2f} C, "
                                         "not confirmed by next reading"))
            self.held = None

        if self.last_accepted is None or abs(t - self.last_accepted) <= self.max_jump:
            out.append(self._decided(row, "ACCEPT", ""))
            self.last_accepted = t
        else:
            self.held = row             # wait for the next valid reading
        return out

    def flush(self):
        """Call at end of data. A held reading can no longer be confirmed."""
        if self.held is None:
            return []
        row, self.held = self.held, None
        return [self._decided(row, "REVIEW",
                              f"R4 spike {row['temperature_c'] - self.last_accepted:+.2f} C, "
                              "data ended before confirmation")]
