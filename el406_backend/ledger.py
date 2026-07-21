"""Per-well volume ledger with explicit known/estimated provenance.

The design principle is "expected is not observed": after an aspiration we do not
know the residual volume, so the well is flagged as an estimate rather than being
presented as physical truth. Dispenses onto an unknown residual keep the total
uncertain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from .models import RecipeStep, all_wells_96


@dataclass
class WellState:
    volume_ul: float = 0.0
    known: bool = True


class VolumeLedger:
    def __init__(
        self,
        wells: Optional[Iterable[str]] = None,
        initial_volume_ul: float = 0.0,
    ) -> None:
        well_ids = tuple(wells) if wells is not None else all_wells_96()
        self._wells: Dict[str, WellState] = {
            w: WellState(initial_volume_ul, True) for w in well_ids
        }

    def apply(self, step: RecipeStep, wells: Iterable[str]) -> None:
        for w in wells:
            st = self._wells.get(w)
            if st is None:
                continue  # well outside the tracked plate; ignore defensively
            if step.sets_residual_unknown:
                st.volume_ul = 0.0
                st.known = False
            elif step.expected_volume_delta_ul is not None:
                st.volume_ul = round(st.volume_ul + step.expected_volume_delta_ul, 3)
                # known stays as-is: adding a known volume to an unknown residual
                # is still unknown in total.

    def volume(self, well: str) -> float:
        return self._wells[well].volume_ul

    def is_known(self, well: str) -> bool:
        return self._wells[well].known

    def summary(self) -> dict:
        states = list(self._wells.values())
        vols = [s.volume_ul for s in states]
        known = sum(1 for s in states if s.known)
        return {
            "wells": len(states),
            "known_wells": known,
            "estimated_wells": len(states) - known,
            "min_volume_ul": min(vols) if vols else 0.0,
            "max_volume_ul": max(vols) if vols else 0.0,
        }
