"""End-to-end dry run on the simulator. No hardware, no pylabrobot required.

Run from the repository root (the directory holding `pyproject.toml`):

    python3 -m el406_backend.demo

It drafts two plans the way the AI planning surface would, compiles them through
the policy engine, executes them on the simulator, and then shows three rejections
the boundary is supposed to produce.
"""

from __future__ import annotations

import asyncio

from .adapters import SimulatedEL406Adapter
from .compiler import compile_plan
from .ledger import VolumeLedger
from .models import DeviceCapabilityProfile, EffectUnknownError, ExecutionPlan, PolicyError, SemanticStep
from .recipes import CAMP_PLATE, IP1_PLATE, REGISTRY


def make_profile() -> DeviceCapabilityProfile:
    return DeviceCapabilityProfile(
        device_id="el406-01",
        model="el406",
        adapter_version="0.2.1",
        labware_allowlist=frozenset({IP1_PLATE, CAMP_PLATE}),
        approved_recipes=frozenset({"ip1-cell-wash-v1", "camp-detection-v1"}),
        installed_options=frozenset({"dual_action_96", "syringe_a", "syringe_b", "peristaltic"}),
    )


async def run_plan(plan: ExecutionPlan, profile, ledger: VolumeLedger, faults=None):
    compiled = compile_plan(plan, profile, REGISTRY)
    adapter = SimulatedEL406Adapter(faults=faults)
    all_evidence = []
    for step in compiled.steps:
        all_evidence.extend(await adapter.run_step(step, ledger))
    return compiled, all_evidence


async def main() -> None:
    profile = make_profile()

    print("=" * 74)
    print("IP1 wash / equilibration (all wells)")
    print("=" * 74)
    ip1 = ExecutionPlan(
        plan_id="plan-ip1-001",
        protocol_id="ip1-htrf",
        plate_binding="plate-ip1-A",
        plate_definition_id=IP1_PLATE,
        steps=(
            SemanticStep("wash-equilibrate", "gentle_media_exchange", "el406-01", "ip1-cell-wash-v1", "ALL"),
        ),
    )
    ledger = VolumeLedger(initial_volume_ul=100.0)  # 100 uL growth medium at start
    compiled, evidence = await run_plan(ip1, profile, ledger)
    print(f"planHash: {compiled.plan_hash}")
    for ev in evidence:
        print(f"  [{ev.method:<20}] {ev.step_name:<22} wells={ev.wells_affected:<3} committed={ev.effect_committed}")
    s = ledger.summary()
    print(f"  ledger: {s['known_wells']} known / {s['estimated_wells']} estimated; "
          f"volume {s['min_volume_ul']}-{s['max_volume_ul']} uL (residual uncertain after aspiration)")

    print()
    print("=" * 74)
    print("Shared cAMP detection (all wells), starting from a 45 uL cellular stage")
    print("=" * 74)
    camp = ExecutionPlan(
        plan_id="plan-camp-001",
        protocol_id="mc4r-camp",
        plate_binding="plate-camp-A",
        plate_definition_id=CAMP_PLATE,
        steps=(
            SemanticStep("detect", "bulk_dispense", "el406-01", "camp-detection-v1", "ALL"),
        ),
    )
    ledger = VolumeLedger(initial_volume_ul=45.0)
    compiled, evidence = await run_plan(camp, profile, ledger)
    for ev in evidence:
        print(f"  [{ev.method:<20}] {ev.step_name:<22} wells={ev.wells_affected}")
    s = ledger.summary()
    print(f"  ledger: all wells at {s['max_volume_ul']} uL "
          f"(expected 45 -> 60 -> 120 -> 180); known_wells={s['known_wells']}")

    print()
    print("=" * 74)
    print("Boundary checks (each SHOULD be rejected)")
    print("=" * 74)

    # 1. Per-well mask must route to STAR.
    bad_mask = ExecutionPlan(
        "plan-x", "ip1-htrf", "plate-ip1-A", IP1_PLATE,
        (SemanticStep("s", "gentle_media_exchange", "el406-01", "ip1-cell-wash-v1", "WELLS:A1,B2"),),
    )
    try:
        compile_plan(bad_mask, profile, REGISTRY)
        print("  FAIL: per-well mask was accepted")
    except PolicyError as e:
        print(f"  rejected per-well mask: {e}")

    # 2. Unapproved recipe.
    bad_recipe = ExecutionPlan(
        "plan-y", "ip1-htrf", "plate-ip1-A", IP1_PLATE,
        (SemanticStep("s", "gentle_media_exchange", "el406-01", "totally-made-up-v9", "ALL"),),
    )
    try:
        compile_plan(bad_recipe, profile, REGISTRY)
        print("  FAIL: unapproved recipe was accepted")
    except PolicyError as e:
        print(f"  rejected unapproved recipe: {e}")

    # 3. Lost acknowledgement after dispatch -> EFFECT_UNKNOWN, no retry.
    ledger = VolumeLedger(initial_volume_ul=100.0)
    try:
        await run_plan(ip1, profile, ledger, faults={"add-pbs-100": "lose_ack"})
        print("  FAIL: effect-unknown was swallowed")
    except EffectUnknownError as e:
        print(f"  halted on ambiguous effect (no auto-retry): {e}")


if __name__ == "__main__":
    asyncio.run(main())
