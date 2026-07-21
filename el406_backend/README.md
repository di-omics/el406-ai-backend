# el406_backend — EL406 AI-native backend (starter)

The EL406 half of the "Stephen 2" workcell: the deterministic, safety-gated backend
that sits behind PyLabRobot so an AI can plan cellular assays without ever emitting a
raw hardware command. Companion to the liquid handler package (`../plr-cell-assays/`)
and the design doc (`../EL406_PyLabRobot_AI_Native_Backend_Approach.docx`).

## What it does

```
AI  →  ExecutionPlan (typed, references approved recipe IDs only)
        →  compile_plan()  (hard policy engine, no hardware)
             →  CompiledPlan  →  EL406Port adapter
                                   ├─ SimulatedEL406Adapter   (default; no pylabrobot)
                                   └─ PyLabRobotEL406Adapter   (real 0.2.1 backend, hardware-gated)
```

The safety property is **structural, not a runtime check you can bypass**:
`SemanticStep` has no field for a flow rate, offset, buffer line, or coordinate. The AI
picks an approved `recipe_id`; the concrete PyLabRobot kwargs live in immutable
`ApprovedRecipe` data that only the lab can edit.

## Run it

From the `stephen/` directory:

```bash
python3 -m el406_backend.demo        # end-to-end dry run on the simulator
python3 -m pytest tests/ -q          # 11 tests
```

The demo runs IP1 wash/equilibration (100 → residual → +100 PBS → residual → +35 stim,
ending flagged *uncertain* because a residual remains after aspiration) and the shared
cAMP detection (45 → 60 → 120 → 180 µL), then shows three rejections the boundary must
produce: a per-well mask (→ route to STAR), an unapproved recipe, and a lost
acknowledgement (→ `EFFECT_UNKNOWN`, never auto-retried).

## Grounded in the real API

Verified against the installed **pylabrobot 0.2.1** `ExperimentalBioTekEL406Backend`
(the EL406 backend *is* in the 0.2.1 release — the `==0.2.1` pin is correct). Every
recipe kwarg is checked against the real method signatures by
`test_recipe_params_match_real_signatures`, so `manifold_aspirate`, `manifold_dispense`,
`syringe_dispense`, and `peristaltic_dispense` calls will bind on hardware.

## Not done here (by design)

- **All recipe numbers are placeholders.** Flow rates, vacuum times, offsets, and buffer
  lines must be replaced by lab-commissioned values (Q0–Q2) before hardware use.
- `PyLabRobotEL406Adapter` refuses to run until `hardware_confirmed=True` *and* the
  version pin matches. Do not flip that flag before qualification.
- Scheduler, event store, handoff two-phase commit, and the HTTP API from the design doc
  are not implemented yet — this is the plan→compile→execute core.

## How it fits with the STAR package

The device split follows the design doc: STAR (the sibling `plr-cell-assays` repo) owns
seeding, dilution series, and patterned/selective dosing; the EL406 owns uniform
full-plate / full-column media removal, PBS wash, and bulk detection additions. The two
share the `pylabrobot==0.2.1` pin and a simulation-only, qualification-gated posture. The
open integration seam is a single top-level semantic plan + device selector + plate
handoff that both compilers consume — see the note in the parent conversation.
