# el406_backend -- EL406 AI-native backend (starter)

The EL406 half of the "Stephen 2" workcell: the deterministic, safety-gated backend
that sits behind PyLabRobot so an AI can plan cellular assays without ever emitting a
raw hardware command. Companion to the liquid handler package plr-cell-assays
*(private)*. It is named here and not linked, because a reader who cannot inspect the
evidence should not be shown a claim resting on it.

## What it does

```
AI  ->  ExecutionPlan (typed, references approved recipe IDs only)
        ->  compile_plan()  (hard policy engine, no hardware)
             ->  CompiledPlan  ->  EL406Port adapter
                                   |- SimulatedEL406Adapter    (default; no pylabrobot)
                                   \- PyLabRobotEL406Adapter   (real 0.2.1 backend, hardware-gated)
```

The safety property is **structural, not a runtime check you can bypass**:
`SemanticStep` has no field for a flow rate, offset, buffer line, or coordinate. The AI
picks an approved `recipe_id`; the concrete PyLabRobot kwargs live in immutable
`ApprovedRecipe` data that only the lab can edit.

## Run it

From the repository root (the directory holding `pyproject.toml`, `el406_backend/`, and
`tests/`):

```bash
python3 -m el406_backend.demo   # end-to-end dry run on the simulator
python3 -m pytest -q            # 11 tests; 1 skips when pylabrobot is not installed
```

Neither command needs this package installed: `conftest.py` puts the repository root on
`sys.path`, and the demo is run as a module from that same directory. The demo needs
nothing beyond the standard library; the test run needs `pytest`.

The demo runs IP1 wash/equilibration (100 -> residual -> +100 PBS -> residual -> +35 stim,
ending flagged *uncertain* because a residual remains after aspiration) and the shared
cAMP detection (45 -> 60 -> 120 -> 180 uL), then shows three rejections the boundary must
produce: a per-well mask (-> route to STAR), an unapproved recipe, and a lost
acknowledgement (-> `EFFECT_UNKNOWN`, never auto-retried).

## Grounded in the real API

Checked against **pylabrobot 0.2.1**'s `ExperimentalBioTekEL406Backend` (the EL406
backend *is* in the 0.2.1 release, so the `==0.2.1` pin is correct). Every
recipe kwarg is checked against the real method signatures by
`test_recipe_params_match_real_signatures`, so `manifold_aspirate`, `manifold_dispense`,
`syringe_dispense`, and `peristaltic_dispense` calls will bind on hardware. That test
skips when pylabrobot is absent, so a run with 1 skip has not checked the signatures.

## Not done here (by design)

- **All recipe numbers are placeholders.** Flow rates, vacuum times, offsets, and buffer
  lines must be replaced by lab-commissioned values (Q0-Q2) before hardware use.
- `PyLabRobotEL406Adapter` refuses to run until `hardware_confirmed=True` *and* the
  version pin matches. Do not flip that flag before qualification.
- Scheduler, event store, handoff two-phase commit, and an HTTP API are not implemented
  -- this is the plan -> compile -> execute core.

## How it fits with the STAR package

The device split is this repo's own contract, enforced in code rather than inherited from
an external document: `parse_well_mask` in `models.py` accepts only `ALL` and
`COLUMNS:...`, so any per-well or row-differentiated request is rejected here rather than
silently approximated, and must be routed to the liquid handler. The EL406 therefore owns
uniform full-plate / full-column media removal, PBS wash, and bulk detection additions;
seeding, dilution series, and patterned or selective dosing belong to the STAR side in
plr-cell-assays *(private)*.

This repo pins `pylabrobot==0.2.1` in `pyproject.toml` and stays simulation-only until
qualification. The STAR side is stated to hold the same pin and the same posture; a reader
without access to that repo cannot check it from here.

The integration seam is unresolved, not merely undocumented. It would be a single
top-level semantic plan plus a device selector and a plate handoff that both compilers
consume. Nothing in this repo implements it: there is no scheduler and no handoff
protocol, and the `Owner` enum in `models.py` (including its `HANDOFF` member) is declared
but never read by any code here.
