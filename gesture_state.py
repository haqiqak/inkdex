# gesture_state.py
# The gesture state machine — the brain of the interaction layer.
#
# WHY A STATE MACHINE?
#   Without one, gesture logic is scattered across if-elif chains in main.py.
#   That works for 2 gestures. It breaks for 6+. With a state machine:
#     - Every possible system state is explicit and named
#     - Every transition has a defined trigger condition
#     - The system is always in exactly one state — no ambiguity
#     - Adding a new gesture means adding a new transition, not editing existing ones
#     - Bugs are easy to find: "the machine entered COOLDOWN unexpectedly" is debuggable
#
# STATES:
#   IDLE           — no hand in frame, system dormant
#   TRACKING       — hand visible, cursor moving, gesture being sampled
#   GESTURE_LOCKED — same gesture held for DWELL_FRAMES, ready to fire action
#   COOLDOWN       — action just fired, ignoring input for COOLDOWN_SEC
#
# GESTURE BUFFER (inside TRACKING):
#   We keep a deque of the last BUFFER_SIZE gesture classifications.
#   The "stable gesture" is the majority vote across that window.
#   This kills the "none" flickering — one bad frame doesn't change the gesture.
#
# HYSTERESIS:
#   A gesture is only "lost" after HYSTERESIS_FRAMES consecutive frames of it
#   being absent. This prevents dwell counter reset from single-frame dropouts.

import time
from collections import deque
from enum import Enum, auto
from config import (
    GESTURE_DWELL_FRAMES,
    GESTURE_COOLDOWN_SEC,
    GESTURE_BUFFER_SIZE,
    GESTURE_HYSTERESIS_FRAMES,
)


class GSMState(Enum):
    IDLE           = auto()
    TRACKING       = auto()
    GESTURE_LOCKED = auto()
    COOLDOWN       = auto()


class GestureStateMachine:
    def __init__(self):
        self.state           = GSMState.IDLE
        self._buffer         = deque(maxlen=GESTURE_BUFFER_SIZE)
        self._dwell_count    = 0
        self._hysteresis     = 0     # frames since stable gesture was last seen
        self._cooldown_until = 0.0
        self._locked_gesture = None  # gesture that is currently locked in

        # Public: read these from outside to drive UI and actions
        self.stable_gesture  = 'none'
        self.dwell_progress  = 0.0   # 0.0 → 1.0, for UI progress bar
        self.locked          = False  # True when in GESTURE_LOCKED state

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self, raw_gesture, hand_present):
        """
        Call once per frame with:
            raw_gesture  — the raw classification string from hand_tracker
            hand_present — bool, whether any hand was detected this frame

        Returns the action to fire (string) or None.
        """
        if self.state == GSMState.IDLE:
            return self._from_idle(hand_present, raw_gesture)

        elif self.state == GSMState.TRACKING:
            return self._from_tracking(hand_present, raw_gesture)

        elif self.state == GSMState.GESTURE_LOCKED:
            return self._from_locked(hand_present, raw_gesture)

        elif self.state == GSMState.COOLDOWN:
            return self._from_cooldown(hand_present, raw_gesture)

    def reset(self):
        """Force back to IDLE — call when camera stalls or tracking disabled."""
        self.state           = GSMState.IDLE
        self._buffer.clear()
        self._dwell_count    = 0
        self._hysteresis     = 0
        self._locked_gesture = None
        self.stable_gesture  = 'none'
        self.dwell_progress  = 0.0
        self.locked          = False

    # ── State handlers ────────────────────────────────────────────────────────

    def _from_idle(self, hand_present, raw_gesture):
        if hand_present:
            self._enter_tracking()
        return None

    def _from_tracking(self, hand_present, raw_gesture):
        if not hand_present:
            self._enter_idle()
            return None

        # Feed raw gesture into rolling buffer
        self._buffer.append(raw_gesture)
        stable = self._majority_vote()
        self.stable_gesture = stable

        if stable == 'none':
            # No consensus gesture — keep cursor moving but reset dwell
            self._dwell_count = 0
            self._hysteresis  = 0
            self.dwell_progress = 0.0
            return None

        # Check if the stable gesture matches what we were dwelling on
        if stable == self._locked_gesture:
            # Hysteresis: sustained gesture, no dropout
            self._hysteresis = 0
            self._dwell_count += 1
            self.dwell_progress = min(self._dwell_count / GESTURE_DWELL_FRAMES, 1.0)

            if self._dwell_count >= GESTURE_DWELL_FRAMES:
                self._enter_gesture_locked(stable)
        else:
            # Different gesture appeared — hysteresis before resetting dwell
            self._hysteresis += 1
            if self._hysteresis >= GESTURE_HYSTERESIS_FRAMES:
                # Commit to the gesture change
                self._locked_gesture = stable
                self._dwell_count    = 0
                self._hysteresis     = 0
                self.dwell_progress  = 0.0

        return None

    def _from_locked(self, hand_present, raw_gesture):
        if not hand_present:
            self._enter_idle()
            return None

        self._buffer.append(raw_gesture)
        stable = self._majority_vote()
        self.stable_gesture = stable

        # If gesture changed, drop back to tracking
        if stable != self._locked_gesture and stable != 'none':
            self._enter_tracking()
            return None

        # Fire the action — transition to cooldown
        action = self._locked_gesture
        self._enter_cooldown()
        return action

    def _from_cooldown(self, hand_present, raw_gesture):
        if time.time() >= self._cooldown_until:
            # Cooldown expired — go back to tracking if hand present, idle if not
            if hand_present:
                self._enter_tracking()
            else:
                self._enter_idle()
        return None  # No actions during cooldown

    # ── State entry helpers ───────────────────────────────────────────────────

    def _enter_idle(self):
        self.state           = GSMState.IDLE
        self._buffer.clear()
        self._dwell_count    = 0
        self._locked_gesture = None
        self.stable_gesture  = 'none'
        self.dwell_progress  = 0.0
        self.locked          = False

    def _enter_tracking(self):
        self.state           = GSMState.TRACKING
        self._buffer.clear()
        self._dwell_count    = 0
        self._hysteresis     = 0
        self._locked_gesture = None
        self.dwell_progress  = 0.0
        self.locked          = False

    def _enter_gesture_locked(self, gesture):
        self.state           = GSMState.GESTURE_LOCKED
        self._locked_gesture = gesture
        self.dwell_progress  = 1.0
        self.locked          = True

    def _enter_cooldown(self):
        self.state           = GSMState.COOLDOWN
        self._cooldown_until = time.time() + GESTURE_COOLDOWN_SEC
        self._dwell_count    = 0
        self.dwell_progress  = 0.0
        self.locked          = False
        self._buffer.clear()

    # ── Gesture buffer ────────────────────────────────────────────────────────

    def _majority_vote(self):
        """
        Returns the most common gesture in the buffer.
        Returns 'none' if buffer is empty or 'none' wins.

        WHY MAJORITY VOTE NOT JUST LATEST?
            A single outlier frame (hand partially occluded, tracking glitch)
            classifies as 'none'. With majority vote, one bad frame out of
            8 buffer frames doesn't change the output at all.
        """
        if not self._buffer:
            return 'none'

        counts = {}
        for g in self._buffer:
            counts[g] = counts.get(g, 0) + 1

        winner = max(counts, key=counts.get)
        # Only declare a winner if it has true majority (> 50%)
        if counts[winner] > len(self._buffer) / 2:
            return winner
        return 'none'

    # ── Debug info ────────────────────────────────────────────────────────────

    def debug_str(self):
        """One-line summary for HUD display."""
        return (
            f"state:{self.state.name:<16} "
            f"gesture:{self.stable_gesture:<8} "
            f"dwell:{self.dwell_progress*100:4.0f}%"
        )
