"""Core typed contracts for the EL406 AI-native backend.

These dataclasses are the *only* things the AI planning surface can produce or
reference. Note what is deliberately absent from `SemanticStep`: there is no
field for a raw numeric flow rate, XYZ coordinate, buffer line, or firmware
parameter. The model selects an approved `recipe_id`; the concrete hardware
parameters live in immutable `ApprovedRecipe` data that only the lab can change.
That structural gap is the safety boundary, not a runtime check that could be
bypassed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

ROWS = "ABCDEFGH"
COLS = tuple(range(1, 13))


def all_wells_96() -> Tuple[str, ...]:
    """Return the 96 well ids in column-major order (A1, B1, ... H12)."""
    return tuple(f"{r}{c}" for c in COLS for r in ROWS)


class Owner(str, Enum):
    STAR = "star"
    EL406 = "el406"
    HANDOFF = "handoff"


class EffectClass(str, Enum):
    REPLAYABLE = "REPLAYABLE"
    NON_REPLAYABLE = "NON_REPLAYABLE"


class PlrMethod(str, Enum):
    """The exact ExperimentalBioTekEL406Backend methods a recipe step may target."""

    MANIFOLD_ASPIRATE = "manifold_aspirate"
    MANIFOLD_DISPENSE = "manifold_dispense"
    MANIFOLD_WASH = "manifold_wash"
    SYRINGE_DISPENSE = "syringe_dispense"
    PERISTALTIC_DISPENSE = "peristaltic_dispense"


@dataclass(frozen=True)
class RecipeStep:
    """One commissioned hardware action, expressed as verified PyLabRobot kwargs."""

    name: str
    method: PlrMethod
    params: Dict[str, Any]
    expected_volume_delta_ul: Optional[float]
    sets_residual_unknown: bool = False
    effect_class: EffectClass = EffectClass.NON_REPLAYABLE


@dataclass(frozen=True)
class ApprovedRecipe:
    """An immutable, lab-approved sequence of hardware steps for one device+plate."""

    recipe_id: str
    title: str
    device_model: str
    plate_definition_id: str
    steps: Tuple[RecipeStep, ...]
    light_protected: bool = False


@dataclass(frozen=True)
class SemanticStep:
    """What the AI is allowed to emit. Intentionally has no numeric hardware fields."""

    step_id: str
    operation: str
    device_selector: str
    recipe_id: str
    well_mask: str  # "ALL" or "COLUMNS:1,2,3"


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    protocol_id: str
    plate_binding: str
    plate_definition_id: str
    steps: Tuple[SemanticStep, ...]

    def to_canonical(self) -> dict:
        return {
            "planId": self.plan_id,
            "protocolId": self.protocol_id,
            "plateBinding": self.plate_binding,
            "plateDefinitionId": self.plate_definition_id,
            "steps": [
                {
                    "stepId": s.step_id,
                    "operation": s.operation,
                    "deviceSelector": s.device_selector,
                    "recipeId": s.recipe_id,
                    "wellMask": s.well_mask,
                }
                for s in self.steps
            ],
        }

    def plan_hash(self) -> str:
        canon = json.dumps(self.to_canonical(), sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DeviceCapabilityProfile:
    """The exact commissioned instrument a plan is compiled against."""

    device_id: str
    model: str
    adapter_version: str
    labware_allowlist: frozenset
    approved_recipes: frozenset
    installed_options: frozenset = frozenset()


@dataclass
class ActionEvidence:
    step_name: str
    method: str
    wells_affected: int
    dispatched: bool = False
    acknowledged: bool = False
    effect_committed: bool = False
    note: str = ""


class PolicyError(Exception):
    """Raised by the compiler when a plan violates a hard safety rule."""


class EffectUnknownError(Exception):
    """A liquid-changing command was dispatched but its effect cannot be confirmed.

    This is never automatically retried: a lost acknowledgement does not make a
    physical dispense replayable.
    """


def parse_well_mask(mask: str) -> Tuple[Tuple[str, ...], str]:
    """Resolve a well mask to concrete wells, enforcing EL406 addressing limits.

    The EL406 can only address the whole plate or whole columns. Any per-well or
    row-differentiated request must be routed to the liquid handler instead, so we
    reject it here rather than silently approximating it.
    """
    m = mask.strip().upper()
    if m == "ALL":
        return all_wells_96(), "ALL"
    if m.startswith("COLUMNS:"):
        cols = []
        for part in m[len("COLUMNS:"):].split(","):
            part = part.strip()
            if not part:
                continue
            if not part.isdigit():
                raise PolicyError(f"Invalid column token {part!r} in mask {mask!r}.")
            c = int(part)
            if c not in COLS:
                raise PolicyError(f"Column {c} out of range 1-12 in mask {mask!r}.")
            cols.append(c)
        if not cols:
            raise PolicyError(f"COLUMNS mask {mask!r} lists no columns.")
        wells = tuple(f"{r}{c}" for c in cols for r in ROWS)
        return wells, "COLUMNS"
    raise PolicyError(
        f"Unsupported well mask {mask!r}. The EL406 accepts 'ALL' or 'COLUMNS:...' only; "
        "per-well or row-differentiated selection must be routed to the liquid handler."
    )
