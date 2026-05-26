# board_state.py
# Explicit interaction state machine for the teaching board.
# Completely separate from gesture_state.py (which handles gesture
# STABILITY) — this handles interaction SEMANTICS.
#
# WHY SEPARATE FROM board_mode.py?
#   board_mode.py owns drawing data, stroke storage, toolbar layout.
#   board_state.py owns the rules for WHEN to transition between
#   interaction states. Keeping them apart means you can tune
#   interaction feel without touching drawing logic, and vice versa.
#
# GESTURE → STATE mapping:
#   point  → CURSOR    (move only, never draw)
#   pinch  → DRAWING   (active stroke in drawing zone)
#   open   → ERASING   (in drawing zone) or MENU (in toolbar zone)
#   fist   → PAUSED    (freeze current state, suppress actions)
#   none   → hold current state with hysteresis

import time
from enum import Enum, auto
from config import (
    BS_DWELL_FRAMES, BS_HYSTERESIS_FRAMES,
    BS_STATE_COOLDOWN, BS_TOOLBAR_H,
)


class BoardState(Enum):
    IDLE          = auto()   # no hand detected
    CURSOR        = auto()   # hand present, point gesture — move cursor only
    DRAWING       = auto()   # pinch in drawing zone — active stroke
    ERASING       = auto()   # open in drawing zone — erase strokes
    PAUSED        = auto()   # fist — freeze, suppress all drawing
    MENU          = auto()   # hand in toolbar zone — tool hover active
    TOOL_SELECT   = auto()   # dwell on toolbar button complete — activating


# Which gesture should trigger each state (from drawing zone)
_DRAW_ZONE_MAP = {
    'point':  BoardState.CURSOR,
    'pinch':  BoardState.DRAWING,
    'open':   BoardState.ERASING,
    'fist':   BoardState.PAUSED,
    'peace':  BoardState.CURSOR,   # peace = point equivalent
    'none':   None,                # hold current state
}


class BoardStateMachine:
    """
    Manages the current board interaction state.

    Public interface:
        .state           — current BoardState
        .state_name      — lowercase string
        .update(gesture, tip_xy, hand_present) → None
        .just_entered    — True for one frame when state changes
        .frames_in_state — frames spent in current state
    """

    def __init__(self):
        self.state           = BoardState.IDLE
        self.just_entered    = False
        self.frames_in_state = 0

        self._candidate      = None    # state we're dwelling toward
        self._candidate_frames = 0
        self._hysteresis     = 0       # frames without current gesture
        self._cooldown_until = 0.0

    def update(self, stable_gesture, tip_xy, hand_present):
        self.just_entered = False
        self.frames_in_state += 1

        if not hand_present:
            if self.state != BoardState.IDLE:
                self._enter(BoardState.IDLE)
            return

        # Determine target zone
        in_toolbar = (tip_xy is not None and tip_xy[1] < BS_TOOLBAR_H)

        if in_toolbar:
            target = BoardState.MENU
        else:
            target = _DRAW_ZONE_MAP.get(stable_gesture)

        # None target = hold current state (hysteresis)
        if target is None:
            self._hysteresis += 1
            if self._hysteresis >= BS_HYSTERESIS_FRAMES:
                # Extended no-gesture: fall back to CURSOR if we were drawing
                if self.state == BoardState.DRAWING:
                    self._enter(BoardState.CURSOR)
            return

        self._hysteresis = 0

        # Already in target state
        if target == self.state:
            self._candidate        = None
            self._candidate_frames = 0
            return

        # Cooldown guard
        if time.time() < self._cooldown_until:
            return

        # Instant transitions (no dwell needed)
        instant = {BoardState.CURSOR, BoardState.MENU, BoardState.IDLE, BoardState.PAUSED}
        if target in instant:
            self._enter(target)
            return

        # Dwell-gated transitions (DRAWING, ERASING need stability)
        if target != self._candidate:
            self._candidate        = target
            self._candidate_frames = 1
        else:
            self._candidate_frames += 1

        if self._candidate_frames >= BS_DWELL_FRAMES:
            self._enter(target)
            self._candidate        = None
            self._candidate_frames = 0

    @property
    def state_name(self):
        return self.state.name.lower()

    @property
    def dwell_progress(self):
        """0.0–1.0 progress toward a dwell-gated transition."""
        if self._candidate is None:
            return 0.0
        return min(self._candidate_frames / BS_DWELL_FRAMES, 1.0)

    def _enter(self, new_state):
        self.state           = new_state
        self.just_entered    = True
        self.frames_in_state = 0
        self._cooldown_until = time.time() + BS_STATE_COOLDOWN
