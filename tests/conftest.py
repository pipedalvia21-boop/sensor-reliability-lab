import pytest

# Reference design case, also used in workbook/Pipe_Diameter_GoalSeek.xlsx
BASE = dict(flow_lps=50.0, length_m=500.0, roughness_mm=0.045,
            viscosity_mm2s=1.004, target_head_loss_m=10.0)


@pytest.fixture
def base_case():
    return dict(BASE)
