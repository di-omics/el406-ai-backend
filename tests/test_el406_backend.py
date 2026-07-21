"""Tests for the EL406 backend starter. Run: python3 -m pytest -q  (from stephen/)."""

from __future__ import annotations

import asyncio

import pytest

from el406_backend.adapters import PyLabRobotEL406Adapter, SimulatedEL406Adapter
from el406_backend.compiler import compile_plan
from el406_backend.ledger import VolumeLedger
from el406_backend.models import (
    DeviceCapabilityProfile,
    EffectUnknownError,
    ExecutionPlan,
    PolicyError,
    SemanticStep,
)
from el406_backend.recipes import CAMP_PLATE, IP1_PLATE, REGISTRY


def profile() -> DeviceCapabilityProfile:
    return DeviceCapabilityProfile(
        device_id="el406-01",
        model="el406",
        adapter_version="0.2.1",
        labware_allowlist=frozenset({IP1_PLATE, CAMP_PLATE}),
        approved_recipes=frozenset({"ip1-cell-wash-v1", "camp-detection-v1"}),
    )


def ip1_plan(mask: str = "ALL", recipe: str = "ip1-cell-wash-v1", plate: str = IP1_PLATE):
    return ExecutionPlan(
        "plan-ip1", "ip1-htrf", "plate-A", plate,
        (SemanticStep("s1", "gentle_media_exchange", "el406-01", recipe, mask),),
    )


async def _run(plan, prof, ledger, faults=None):
    compiled = compile_plan(plan, prof, REGISTRY)
    adapter = SimulatedEL406Adapter(faults=faults)
    ev = []
    for step in compiled.steps:
        ev.extend(await adapter.run_step(step, ledger))
    return compiled, ev


def test_ip1_volume_invariant_and_residual_uncertainty():
    ledger = VolumeLedger(initial_volume_ul=100.0)
    _, ev = asyncio.run(_run(ip1_plan(), profile(), ledger))
    assert [e.step_name for e in ev] == [
        "remove-growth-medium", "add-pbs-100", "aspirate-pbs", "add-stim-buffer-35",
    ]
    # Every well ends at the 35 uL stimulation volume...
    assert ledger.volume("A1") == 35.0
    # ...but the total is flagged uncertain because a residual remained after aspiration.
    assert ledger.is_known("A1") is False
    assert ledger.summary()["estimated_wells"] == 96


def test_camp_volume_invariant():
    ledger = VolumeLedger(initial_volume_ul=45.0)
    camp = ExecutionPlan(
        "plan-camp", "mc4r-camp", "plate-C", CAMP_PLATE,
        (SemanticStep("s1", "bulk_dispense", "el406-01", "camp-detection-v1", "ALL"),),
    )
    _, _ = asyncio.run(_run(camp, profile(), ledger))
    assert ledger.volume("H12") == 180.0  # 45 -> 60 -> 120 -> 180
    assert ledger.is_known("H12") is True  # no aspiration in this recipe


def test_per_well_mask_rejected():
    with pytest.raises(PolicyError, match="per-well"):
        compile_plan(ip1_plan(mask="WELLS:A1,B2"), profile(), REGISTRY)


def test_full_column_mask_allowed():
    compiled = compile_plan(ip1_plan(mask="COLUMNS:1,2"), profile(), REGISTRY)
    assert len(compiled.steps[0].wells) == 16  # 2 columns x 8 rows
    assert compiled.steps[0].mask_kind == "COLUMNS"


def test_unapproved_recipe_rejected():
    with pytest.raises(PolicyError, match="not approved"):
        compile_plan(ip1_plan(recipe="totally-made-up-v9"), profile(), REGISTRY)


def test_labware_not_allowlisted_rejected():
    prof = DeviceCapabilityProfile(
        "el406-01", "el406", "0.2.1",
        labware_allowlist=frozenset({CAMP_PLATE}),  # IP1 plate deliberately absent
        approved_recipes=frozenset({"ip1-cell-wash-v1"}),
    )
    with pytest.raises(PolicyError, match="labware allowlist"):
        compile_plan(ip1_plan(), prof, REGISTRY)


def test_wrong_device_selector_rejected():
    bad = ExecutionPlan(
        "plan-z", "ip1-htrf", "plate-A", IP1_PLATE,
        (SemanticStep("s1", "gentle_media_exchange", "el406-99", "ip1-cell-wash-v1", "ALL"),),
    )
    with pytest.raises(PolicyError, match="does not match profile"):
        compile_plan(bad, profile(), REGISTRY)


def test_effect_unknown_halts_without_retry():
    ledger = VolumeLedger(initial_volume_ul=100.0)
    with pytest.raises(EffectUnknownError):
        asyncio.run(_run(ip1_plan(), profile(), ledger, faults={"add-pbs-100": "lose_ack"}))
    # The PBS add reached the ledger before the ack was lost; nothing was retried.
    assert ledger.volume("A1") == 100.0
    assert ledger.is_known("A1") is False


def test_plan_hash_changes_when_plan_edited():
    h1 = ip1_plan(mask="ALL").plan_hash()
    h2 = ip1_plan(mask="COLUMNS:1").plan_hash()
    assert h1 != h2
    assert ip1_plan(mask="ALL").plan_hash() == h1  # stable/deterministic


def test_plr_adapter_is_hardware_gated():
    adapter = PyLabRobotEL406Adapter(device_id="el406-01", hardware_confirmed=False)
    with pytest.raises(RuntimeError, match="hardware-gated"):
        asyncio.run(adapter.identify())


def test_recipe_params_match_real_signatures():
    """Every recipe kwarg must be accepted by the real pylabrobot 0.2.1 method."""
    pytest.importorskip("pylabrobot")
    import inspect

    from pylabrobot.plate_washing.biotek.el406.backend import ExperimentalBioTekEL406Backend as B

    for recipe in REGISTRY.values():
        for rs in recipe.steps:
            fn = getattr(B, rs.method.value)
            sig = inspect.signature(fn)
            # self, plate, then the recipe's approved kwargs. Raises TypeError on a bad name.
            sig.bind_partial(None, None, **rs.params)
