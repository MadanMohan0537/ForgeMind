"""
A stable detector reading by itself isn't an event stream - if you just
emitted one every time the stabilizer produced a result, you'd fire
KIT_INSPECTED every frame forever once things settle. This module tracks
one state machine per zone and only emits on actual transitions:

    EMPTY -> ARRIVED -> (COMPLETE -> RELEASED -> EMPTY)
                      -> (HELD -> [changes] -> re-inspect -> COMPLETE -> RELEASED)

Generic over any recipe - "complete" just means every expected_count in the
recipe is met with no extras.
"""

from __future__ import annotations
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class KitState(Enum):
    EMPTY = "empty"
    ARRIVED = "arrived"
    HELD = "held"
    COMPLETE = "complete"
    RELEASED = "released"


@dataclass
class ZoneTracker:
    zone_name: str
    state: KitState = KitState.EMPTY
    last_counts: Dict[str, int] = field(default_factory=dict)
    last_transition_ts: float = field(default_factory=time.time)
    # fingerprint of the last (missing, extra) we actually emitted, so a
    # steady-state stable reading doesn't refire KIT_INSPECTED every frame
    _last_emitted_signature: Optional[tuple] = field(default=None, repr=False)

    def is_empty_reading(self, counts: Dict[str, int]) -> bool:
        return all(v == 0 for v in counts.values())

    def process(self, stable_counts: Optional[Dict[str, int]], missing: List[str], extra: List[str]):
        """Returns a list of (event_type, payload) tuples to emit, given this
        frame's stable reading (or None if not yet stable). Empty list means
        nothing changed worth reporting - this is what keeps a steady-state
        reading from spamming the same event every frame."""
        events = []
        now = time.time()

        if stable_counts is None:
            return events  # nothing stable yet this frame, no transition possible

        is_empty = self.is_empty_reading(stable_counts)
        is_complete = not missing and not extra

        if self.state == KitState.EMPTY and not is_empty:
            self.state = KitState.ARRIVED
            self.last_transition_ts = now
            events.append(("KIT_ARRIVED", {"detected": stable_counts}))
            # fall through - a kit can arrive already complete or already short a part

        # Re-check completeness from ARRIVED, HELD, *and* COMPLETE - a part can be
        # pulled back out of an already-complete kit before it's released (that's
        # exactly what milestone 1 is: remove a wheel from a kit sitting in the zone).
        # Only EMPTY/RELEASED are excluded, since those mean nothing is there to inspect.
        if self.state in (KitState.ARRIVED, KitState.HELD, KitState.COMPLETE) and not is_empty:
            new_state = KitState.COMPLETE if is_complete else KitState.HELD
            # signature reflects the state we're ABOUT TO BE in, not the state
            # we were in before this frame - otherwise the frame immediately
            # after a transition looks "changed" against the pre-transition
            # signature and fires a spurious duplicate event.
            signature = (new_state, tuple(sorted(missing)), tuple(sorted(extra)), is_empty)
            changed = signature != self._last_emitted_signature
            if changed:
                self.state = new_state
                self.last_transition_ts = now
                events.append((
                    "KIT_INSPECTED",
                    {
                        "detected": stable_counts,
                        "missing": [] if is_complete else missing,
                        "extra": [] if is_complete else extra,
                        "confidence": 1.0,
                    },
                ))
                self._last_emitted_signature = signature

        if self.state == KitState.COMPLETE and is_empty:
            self.state = KitState.RELEASED
            self.last_transition_ts = now
            events.append(("KIT_RELEASED", {}))
            self._last_emitted_signature = None

        if self.state == KitState.RELEASED and is_empty:
            self.state = KitState.EMPTY

        self.last_counts = stable_counts
        return events
