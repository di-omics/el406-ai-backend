"""Approved recipe registry for the first two EL406 slices.

WARNING: every numeric parameter below (flow rates, vacuum times, buffer-line
letters, offsets) is a PLACEHOLDER. It exists so the compiler and simulator have
concrete, typed data to operate on and so `test_recipe_params_match_real_signatures`
can prove each kwarg is accepted by the real backend. These values MUST be replaced
by lab-commissioned values before the PyLabRobot adapter is ever pointed at hardware.
The qualification levels the lab commissions against (Q0-Q2) are defined by the lab and
are not recorded in this repository. The `param names` are real; the `values` are not
qualified.
"""

from __future__ import annotations

from .models import ApprovedRecipe, EffectClass, PlrMethod, RecipeStep

# Placeholder labware ids -- replace with the lab's exact catalog numbers + geometry hash.
IP1_PLATE = "corning-3903-white-96"
CAMP_PLATE = "greiner-655098-white-96"

# Manifold buffer line assigned to PBS on this instrument (commission-specific).
PBS_LINE = "B"


IP1_CELL_WASH_V1 = ApprovedRecipe(
    recipe_id="ip1-cell-wash-v1",
    title="IP1: remove growth medium, single 100 uL PBS wash, 35 uL stimulation-buffer equilibration",
    device_model="el406",
    plate_definition_id=IP1_PLATE,
    light_protected=False,
    steps=(
        RecipeStep(
            "remove-growth-medium",
            PlrMethod.MANIFOLD_ASPIRATE,
            dict(vacuum_time=30.0, travel_rate="3"),
            expected_volume_delta_ul=None,
            sets_residual_unknown=True,
        ),
        RecipeStep(
            "add-pbs-100",
            PlrMethod.MANIFOLD_DISPENSE,
            dict(volume=100.0, buffer=PBS_LINE, flow_rate=5),
            expected_volume_delta_ul=100.0,
        ),
        RecipeStep(
            "aspirate-pbs",
            PlrMethod.MANIFOLD_ASPIRATE,
            dict(vacuum_time=25.0, travel_rate="3"),
            expected_volume_delta_ul=None,
            sets_residual_unknown=True,
        ),
        RecipeStep(
            "add-stim-buffer-35",
            PlrMethod.SYRINGE_DISPENSE,
            dict(volume=35.0, syringe="A", flow_rate=2),
            expected_volume_delta_ul=35.0,
        ),
    ),
)


CAMP_DETECTION_V1 = ApprovedRecipe(
    recipe_id="camp-detection-v1",
    title="Shared cAMP detection: 15 uL antibody, 60 uL detection reagent, 60 uL Solution A (all wells)",
    device_model="el406",
    plate_definition_id=CAMP_PLATE,
    light_protected=True,
    steps=(
        RecipeStep(
            "add-antibody-15",
            PlrMethod.SYRINGE_DISPENSE,
            dict(volume=15.0, syringe="A", flow_rate=2),
            expected_volume_delta_ul=15.0,
        ),
        RecipeStep(
            "add-detection-60",
            PlrMethod.SYRINGE_DISPENSE,
            dict(volume=60.0, syringe="B", flow_rate=2),
            expected_volume_delta_ul=60.0,
        ),
        RecipeStep(
            "add-solution-a-60",
            PlrMethod.PERISTALTIC_DISPENSE,
            dict(volume=60.0, flow_rate="Low", cassette="Any"),
            expected_volume_delta_ul=60.0,
        ),
    ),
)


REGISTRY = {r.recipe_id: r for r in (IP1_CELL_WASH_V1, CAMP_DETECTION_V1)}
