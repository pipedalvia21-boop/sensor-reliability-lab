"""Water properties from temperature - the bridge between the sensor and the pipe tool.

The pipe tool (Module 4) takes kinematic viscosity in mm²/s as a typed input.
Viscosity of water depends strongly on temperature, so a measured water temperature
can replace that typed value.

Dynamic viscosity (Vogel equation):
    mu = A * 10^(B / (T - C)),  A = 2.414e-5 Pa·s, B = 247.8 K, C = 140 K, T in K
Density (Thiesen-type fit for liquid water at 1 atm):
    rho = 1000 * (1 - (t + 288.9414) / (508929.2 * (t + 68.12963)) * (t - 3.9863)^2),  t in °C
Kinematic viscosity:
    nu = mu / rho   (m²/s)  ->  x 1e6 for mm²/s

Supported range: liquid water at atmospheric pressure, above 0 °C and below 100 °C.
"""
WATER_MIN_C = 0.0     # exclusive: at 0 °C water may be ice
WATER_MAX_C = 100.0   # exclusive: at 100 °C water boils

_A, _B, _C = 2.414e-5, 247.8, 140.0


def is_liquid_water(temp_c):
    return WATER_MIN_C < temp_c < WATER_MAX_C


def dynamic_viscosity_pa_s(temp_c):
    return _A * 10 ** (_B / (temp_c + 273.15 - _C))


def density_kg_m3(temp_c):
    t = temp_c
    return 1000.0 * (1 - (t + 288.9414) / (508929.2 * (t + 68.12963)) * (t - 3.9863) ** 2)


def kinematic_viscosity_mm2s(temp_c):
    """Kinematic viscosity of water (mm²/s) at temp_c (°C). Raises ValueError outside 0-100 °C."""
    if not is_liquid_water(temp_c):
        raise ValueError(f"{temp_c} °C is outside the liquid-water range (0-100 °C, exclusive).")
    return dynamic_viscosity_pa_s(temp_c) / density_kg_m3(temp_c) * 1e6
