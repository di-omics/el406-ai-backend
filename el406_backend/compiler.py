"""Deterministic compiler + hard policy engine.

Turns an AI-drafted `ExecutionPlan` into a `CompiledPlan` of concrete recipe steps,
or raises `PolicyError`. Nothing here touches hardware; this is the gate every plan
must pass before an edge agent will run it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .models import (
    ApprovedRecipe,
    DeviceCapabilityProfile,
    ExecutionPlan,
    PolicyError,
    SemanticStep,
    parse_well_mask,
)

ALLOWED_OPERATIONS = frozenset(
    {
        "gentle_media_exchange",
        "bulk_dispense",
        "media_aspirate",
        "pbs_wash",
    }
)


@dataclass(frozen=True)
class CompiledStep:
    semantic: SemanticStep
    recipe: ApprovedRecipe
    wells: Tuple[str, ...]
    mask_kind: str


@dataclass(frozen=True)
class CompiledPlan:
    plan_id: str
    plan_hash: str
    profile_device_id: str
    steps: Tuple[CompiledStep, ...]


def compile_plan(
    plan: ExecutionPlan,
    profile: DeviceCapabilityProfile,
    registry: Dict[str, ApprovedRecipe],
) -> CompiledPlan:
    if plan.plate_definition_id not in profile.labware_allowlist:
        raise PolicyError(
            f"Plate '{plan.plate_definition_id}' is not in the device labware allowlist "
            f"{sorted(profile.labware_allowlist)}."
        )

    compiled: List[CompiledStep] = []
    for s in plan.steps:
        if s.operation not in ALLOWED_OPERATIONS:
            raise PolicyError(
                f"Step {s.step_id}: operation '{s.operation}' is not allowlisted."
            )
        if s.device_selector != profile.device_id:
            raise PolicyError(
                f"Step {s.step_id}: device '{s.device_selector}' does not match profile "
                f"device '{profile.device_id}'."
            )
        if s.recipe_id not in profile.approved_recipes:
            raise PolicyError(
                f"Step {s.step_id}: recipe '{s.recipe_id}' is not approved for device "
                f"'{profile.device_id}'."
            )
        recipe = registry.get(s.recipe_id)
        if recipe is None:
            raise PolicyError(
                f"Step {s.step_id}: recipe '{s.recipe_id}' is approved but missing from the registry."
            )
        if recipe.device_model != profile.model:
            raise PolicyError(
                f"Step {s.step_id}: recipe targets model '{recipe.device_model}' but device is "
                f"'{profile.model}'."
            )
        if recipe.plate_definition_id != plan.plate_definition_id:
            raise PolicyError(
                f"Step {s.step_id}: recipe plate '{recipe.plate_definition_id}' does not match plan "
                f"plate '{plan.plate_definition_id}'."
            )
        wells, kind = parse_well_mask(s.well_mask)  # rejects per-well/row masks
        compiled.append(
            CompiledStep(semantic=s, recipe=recipe, wells=wells, mask_kind=kind)
        )

    return CompiledPlan(
        plan_id=plan.plan_id,
        plan_hash=plan.plan_hash(),
        profile_device_id=profile.device_id,
        steps=tuple(compiled),
    )
