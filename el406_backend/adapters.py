"""EL406 execution adapters behind one semantic port.

`SimulatedEL406Adapter` runs entirely in-process (no pylabrobot, no hardware) and
is the default for development, CI, and dry runs. `PyLabRobotEL406Adapter` maps the
same approved recipes onto the real `ExperimentalBioTekEL406Backend` and is gated so
it cannot move real liquid until a qualified operator flips `hardware_confirmed`.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Protocol, runtime_checkable

from .compiler import CompiledStep
from .ledger import VolumeLedger
from .models import ActionEvidence, EffectUnknownError


@runtime_checkable
class EL406Port(Protocol):
    async def identify(self) -> dict: ...
    async def run_step(self, step: CompiledStep, ledger: VolumeLedger) -> List[ActionEvidence]: ...
    async def safe_stop(self, reason: str) -> ActionEvidence: ...


class SimulatedEL406Adapter:
    """Behavior-level simulator with optional fault injection.

    `faults` maps a `RecipeStep.name` to a failure mode:
      * "lose_ack": the effect reaches the ledger, but the acknowledgement is lost,
        so we raise `EffectUnknownError`. This models a dropped USB ack after a real
        dispense — the physical effect may or may not have happened, and it must not
        be retried.
    """

    def __init__(
        self,
        device_id: str = "el406-sim",
        faults: Optional[Dict[str, str]] = None,
    ) -> None:
        self.device_id = device_id
        self._faults = dict(faults or {})

    async def identify(self) -> dict:
        return {"deviceId": self.device_id, "model": "el406", "adapter": "simulated"}

    async def run_step(self, step: CompiledStep, ledger: VolumeLedger) -> List[ActionEvidence]:
        evidence: List[ActionEvidence] = []
        for rs in step.recipe.steps:
            ev = ActionEvidence(
                step_name=rs.name, method=rs.method.value, wells_affected=len(step.wells)
            )
            ev.dispatched = True
            ledger.apply(rs, step.wells)  # the physical effect happens at the device here
            if self._faults.get(rs.name) == "lose_ack":
                ev.note = "acknowledgement lost after dispatch"
                evidence.append(ev)
                raise EffectUnknownError(
                    f"{rs.name}: dispatched but not acknowledged. Effect is UNKNOWN; do not retry."
                )
            ev.acknowledged = True
            ev.effect_committed = True
            evidence.append(ev)
        return evidence

    async def safe_stop(self, reason: str) -> ActionEvidence:
        return ActionEvidence(
            step_name="safe_stop",
            method="stop",
            wells_affected=0,
            dispatched=True,
            acknowledged=True,
            effect_committed=True,
            note=reason,
        )


class PyLabRobotEL406Adapter:
    """Maps approved recipes onto the real EL406 backend (pylabrobot 0.2.1).

    Hardware-gated on purpose: `run_step`/`identify` refuse to proceed unless
    `hardware_confirmed=True` AND the installed pylabrobot version matches the pin,
    because these calls move real liquid on real cells.
    """

    PINNED_ADAPTER_VERSION = "0.2.1"

    def __init__(
        self,
        device_id: Optional[str] = None,
        *,
        timeout_s: float = 15.0,
        hardware_confirmed: bool = False,
    ) -> None:
        self.device_id = device_id
        self.timeout_s = timeout_s
        self.hardware_confirmed = hardware_confirmed
        self._backend = None

    def _require_gate(self) -> None:
        if not self.hardware_confirmed:
            raise RuntimeError(
                "PyLabRobotEL406Adapter is hardware-gated. Set hardware_confirmed=True only after "
                "Q0-Q3 qualification (serial, manifold, plate geometry, coordinates) for this exact "
                "instrument."
            )
        try:
            import pylabrobot
        except ImportError as e:  # pragma: no cover - depends on environment
            raise RuntimeError("pylabrobot is not installed.") from e
        if pylabrobot.__version__ != self.PINNED_ADAPTER_VERSION:
            raise RuntimeError(
                f"pylabrobot {pylabrobot.__version__} does not match pinned version "
                f"{self.PINNED_ADAPTER_VERSION}."
            )

    async def identify(self) -> dict:
        self._require_gate()
        import pylabrobot

        return {
            "deviceId": self.device_id,
            "model": "el406",
            "adapter": "pylabrobot",
            "version": pylabrobot.__version__,
        }

    async def _ensure_backend(self):  # pragma: no cover - requires hardware
        if self._backend is None:
            from pylabrobot.plate_washing.biotek.el406.backend import (
                ExperimentalBioTekEL406Backend,
            )

            self._backend = ExperimentalBioTekEL406Backend(
                timeout=self.timeout_s, device_id=self.device_id
            )
            await self._backend.setup(skip_reset=False)
        return self._backend

    async def run_step(  # pragma: no cover - requires hardware
        self,
        step: CompiledStep,
        ledger: VolumeLedger,
        *,
        plate=None,
    ) -> List[ActionEvidence]:
        self._require_gate()
        if plate is None:
            raise RuntimeError("A pylabrobot Plate resource is required for hardware execution.")
        backend = await self._ensure_backend()
        evidence: List[ActionEvidence] = []
        async with backend.batch(plate):
            for rs in step.recipe.steps:
                method = getattr(backend, rs.method.value)
                ev = ActionEvidence(
                    step_name=rs.name, method=rs.method.value, wells_affected=len(step.wells)
                )
                ev.dispatched = True
                await method(plate, **rs.params)  # verified, approved PLR kwargs only
                ev.acknowledged = True
                ev.effect_committed = True
                ledger.apply(rs, step.wells)
                evidence.append(ev)
        return evidence

    async def safe_stop(self, reason: str) -> ActionEvidence:  # pragma: no cover - requires hardware
        if self._backend is not None:
            await self._backend.stop()
        return ActionEvidence("safe_stop", "stop", 0, True, True, True, reason)
