# interaction_mode.py
# The interaction mode layer — sits between gesture detection and PC actions.
#
# ARCHITECTURE POSITION:
#   hand_tracker → gesture_state (raw gesture stabilisation)
#        ↓
#   InteractionModeManager  ← THIS FILE
#        ↓
#   draw_layer / CursorController / pyautogui actions
#
# WHY SEPARATE FROM gesture_state.py?
#   gesture_state handles STABILITY of a single gesture over time.
#   interaction_mode handles the MEANING of that stable gesture in context.
#   "Peace held for 8 frames" is gesture_state's job.
#   "Peace means left-click in Navigate mode, but confirm-selection in Select mode"
#   is interaction_mode's job. Clean separation of concerns.
#
# MODE DESIGN PHILOSOPHY:
#   Each mode is a named context. The same gesture can mean different things
#   in different modes — just like modifier keys on a keyboard. The user
#   always knows their mode from the cursor color in the HUD.
#
#   Modes are explicit and mutually exclusive. The system is ALWAYS in exactly
#   one mode. There is no ambiguity. This is the #1 thing that makes gesture
#   UIs feel intentional vs random.

import time
from enum import Enum, auto
from config import (
    MODE_ENTRY_GESTURES,
    MODE_DWELL_FRAMES,
    MODE_SWITCH_COOLDOWN,
    MODE_CURSOR_COLORS,
)


class InteractionMode(Enum):
    NAVIGATE = auto()   # default: move cursor
    SELECT   = auto()   # click / confirm actions
    DRAG     = auto()   # mouse-down held, cursor dragging
    DRAW     = auto()   # fingertip draws on canvas
    SCROLL   = auto()   # vertical hand motion scrolls


# Map mode enum → gesture name that enters it from Navigate
_ENTRY = {
    InteractionMode.NAVIGATE: 'point',
    InteractionMode.SELECT:   'peace',
    InteractionMode.DRAG:     'fist',
    InteractionMode.DRAW:     'pinch',
    InteractionMode.SCROLL:   'open',
}

# Map entry gesture → destination mode (inverse of above)
_GESTURE_TO_MODE = {v: k for k, v in _ENTRY.items()}


class InteractionModeManager:
    """
    Manages which interaction mode is active and drives mode transitions.

    Public interface (read by main.py every frame):
        .mode            — current InteractionMode enum value
        .mode_name       — lowercase string e.g. 'navigate'
        .cursor_color    — BGR tuple for cursor ring
        .dwell_progress  — 0.0–1.0 progress toward mode switch
        .just_switched   — True for one frame when mode changes
        .update(stable_gesture, tip_xy, hand_present) → ModeAction or None
    """

    def __init__(self, cursor_ctl, action_ctl, draw_layer):
        self.mode           = InteractionMode.NAVIGATE
        self.cursor_color   = MODE_CURSOR_COLORS['navigate']
        self.dwell_progress = 0.0
        self.just_switched  = False

        self._cursor_ctl  = cursor_ctl
        self._action_ctl  = action_ctl
        self._draw_layer  = draw_layer

        # Mode-switch dwell state
        self._candidate_mode   = None   # mode we're dwelling toward
        self._dwell_count      = 0
        self._switch_cooldown  = 0.0    # timestamp when cooldown expires

        # Drag state (for clean cleanup on mode exit)
        self._dragging = False

        # Scroll state
        self._last_scroll_y    = None
        self._scroll_accumulator = 0.0

    # ── Public update ─────────────────────────────────────────────────────────

    def update(self, stable_gesture, tip_xy, hand_present):
        """
        Call once per frame.

        stable_gesture : the majority-voted gesture from GestureStateMachine
        tip_xy         : (canvas_x, canvas_y) of the index fingertip (filtered)
        hand_present   : bool

        Returns a string describing the action taken (for HUD), or None.
        """
        self.just_switched = False

        if not hand_present:
            self._on_hand_lost()
            return None

        # Always update cursor position in navigate/draw/scroll modes
        if self.mode in (InteractionMode.NAVIGATE,
                         InteractionMode.DRAW,
                         InteractionMode.SCROLL):
            self._cursor_ctl.update(tip_xy[0], tip_xy[1])

        # Attempt mode switch based on current stable gesture
        switched = self._try_mode_switch(stable_gesture)
        if switched:
            return f"MODE → {self.mode_name.upper()}"

        # Dispatch to current mode's handler
        return self._dispatch(stable_gesture, tip_xy)

    @property
    def mode_name(self):
        return self.mode.name.lower()

    # ── Mode dispatch ─────────────────────────────────────────────────────────

    def _dispatch(self, gesture, tip_xy):
        """Call the active mode's per-frame handler."""
        if self.mode == InteractionMode.NAVIGATE:
            return self._navigate(gesture, tip_xy)
        elif self.mode == InteractionMode.SELECT:
            return self._select(gesture, tip_xy)
        elif self.mode == InteractionMode.DRAG:
            return self._drag(gesture, tip_xy)
        elif self.mode == InteractionMode.DRAW:
            return self._draw_mode(gesture, tip_xy)
        elif self.mode == InteractionMode.SCROLL:
            return self._scroll(gesture, tip_xy)
        return None

    def _navigate(self, gesture, tip_xy):
        """
        Navigate mode: cursor moves with index finger.
        No click actions here — user must switch to Select mode.
        This prevents accidental clicks while navigating.
        """
        # Cursor movement already handled above. Nothing else to do.
        return None

    def _select(self, gesture, tip_xy):
        """
        Select mode: a peace-dwell fires a left click.
        Returns to Navigate automatically after click.
        """
        if gesture == 'peace':
            result = self._action_ctl.execute('peace')
            self._switch_to(InteractionMode.NAVIGATE)
            return result
        return None

    def _drag(self, gesture, tip_xy):
        """
        Drag mode: mouse is held down, cursor follows finger.
        Stays in drag until open gesture releases.
        Cursor movement handled above (navigate/draw/scroll modes).
        We also update cursor in drag explicitly.
        """
        self._cursor_ctl.update(tip_xy[0], tip_xy[1])

        if not self._dragging:
            import pyautogui
            if self._action_ctl._action_ctl_enabled():
                pyautogui.mouseDown()
            self._dragging = True
            return "DRAG HOLD"

        if gesture == 'open':
            self._release_drag()
            self._switch_to(InteractionMode.NAVIGATE)
            return "DRAG RELEASED"

        return "DRAGGING"

    def _draw_mode(self, gesture, tip_xy):
        """
        Draw mode: index fingertip paints strokes on the canvas overlay.
        Pinch gesture adds points to active stroke.
        Open gesture clears all strokes.
        Point gesture exits draw mode.
        """
        if gesture == 'pinch':
            self._draw_layer.add_point(tip_xy[0], tip_xy[1])
            return "DRAWING"
        elif gesture == 'open':
            self._draw_layer.clear()
            return "CANVAS CLEARED"
        else:
            # Any non-pinch gesture ends current stroke (lifts the pen)
            self._draw_layer.end_stroke()
        return None

    def _scroll(self, gesture, tip_xy):
        """
        Scroll mode: vertical hand movement scrolls.
        Tracks Y delta between frames and accumulates scroll units.
        """
        cy = tip_xy[1]

        if self._last_scroll_y is None:
            self._last_scroll_y = cy
            return None

        dy = cy - self._last_scroll_y   # positive = hand moved down
        self._last_scroll_y = cy

        from config import SCROLL_SENSITIVITY
        self._scroll_accumulator += -dy * SCROLL_SENSITIVITY  # invert: hand down = scroll down

        # Only fire scroll when accumulator reaches a whole unit
        scroll_units = int(self._scroll_accumulator)
        if scroll_units != 0:
            self._scroll_accumulator -= scroll_units
            if self._action_ctl._action_ctl_enabled():
                import pyautogui
                pyautogui.scroll(scroll_units)
            return f"SCROLL {'+' if scroll_units > 0 else ''}{scroll_units}"

        return None

    # ── Mode switching ────────────────────────────────────────────────────────

    def _try_mode_switch(self, gesture):
        """
        Checks if the current gesture warrants a mode switch.
        Uses dwell to prevent accidental switches.
        Returns True if a switch happened this frame.
        """
        if time.time() < self._switch_cooldown:
            self.dwell_progress = 0.0
            return False

        target = _GESTURE_TO_MODE.get(gesture)
        if target is None or target == self.mode:
            # Unknown gesture or already in this mode — reset candidate
            if self._candidate_mode is not None:
                self._candidate_mode = None
                self._dwell_count    = 0
                self.dwell_progress  = 0.0
            return False

        # Gesture points to a different mode
        if target != self._candidate_mode:
            # New candidate — start dwell from scratch
            self._candidate_mode = target
            self._dwell_count    = 1
        else:
            self._dwell_count += 1

        self.dwell_progress = min(self._dwell_count / MODE_DWELL_FRAMES, 1.0)

        if self._dwell_count >= MODE_DWELL_FRAMES:
            self._switch_to(target)
            return True

        return False

    def _switch_to(self, new_mode):
        """Execute a mode transition. Handles cleanup of previous mode."""
        # Clean up the exiting mode
        if self.mode == InteractionMode.DRAG:
            self._release_drag()
        if self.mode == InteractionMode.SCROLL:
            self._last_scroll_y      = None
            self._scroll_accumulator = 0.0
        if self.mode == InteractionMode.DRAW:
            self._draw_layer.end_stroke()

        self.mode             = new_mode
        self.cursor_color     = MODE_CURSOR_COLORS[self.mode_name]
        self.just_switched    = True
        self._candidate_mode  = None
        self._dwell_count     = 0
        self.dwell_progress   = 0.0
        self._switch_cooldown = time.time() + MODE_SWITCH_COOLDOWN

    # ── Cleanup helpers ───────────────────────────────────────────────────────

    def _release_drag(self):
        if self._dragging:
            if self._action_ctl._action_ctl_enabled():
                import pyautogui
                pyautogui.mouseUp()
            self._dragging = False

    def _on_hand_lost(self):
        """Clean up any active state when tracking is lost."""
        self._release_drag()
        self._cursor_ctl.reset()
        self._last_scroll_y      = None
        self._scroll_accumulator = 0.0
        self._draw_layer.end_stroke()
        self._candidate_mode  = None
        self._dwell_count     = 0
        self.dwell_progress   = 0.0

    def reset(self):
        """Hard reset to Navigate mode. Call when tracking toggled off."""
        self._on_hand_lost()
        self._switch_to(InteractionMode.NAVIGATE)
        self._switch_cooldown = 0.0
