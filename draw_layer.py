# draw_layer.py
# Stores polyline strokes drawn in Draw mode and renders them onto the canvas.
#
# DESIGN:
#   A stroke is a list of (x, y, timestamp) points. The DrawLayer holds a list
#   of completed strokes plus one active (in-progress) stroke. Rendering walks
#   every stroke and draws connected line segments onto the OpenCV canvas.
#
# WHY STORE TIMESTAMPS?
#   Supports optional stroke fading (DRAW_STROKE_FADE_SEC). Even if fading is
#   off (set to 0), timestamps cost nothing and make the feature trivially
#   addable later without changing the data model.

import time
import math
import cv2
from config import (
    DRAW_MAX_STROKES,
    DRAW_MIN_POINT_DIST,
    DRAW_STROKE_THICKNESS,
    DRAW_STROKE_COLOR,
    DRAW_STROKE_FADE_SEC,
    MODE_CURSOR_COLORS,
)

# Default stroke color: use Draw mode cursor color if config says None
_DEFAULT_COLOR = DRAW_STROKE_COLOR or MODE_CURSOR_COLORS['draw']


class DrawLayer:
    def __init__(self):
        self._strokes = []        # list of completed strokes
        self._active  = []        # current in-progress stroke: [(x, y, t), ...]

    # ── Public API ────────────────────────────────────────────────────────────

    def add_point(self, x, y):
        """
        Append a point to the active stroke.
        Ignores the point if it's too close to the previous one
        (DRAW_MIN_POINT_DIST) — prevents thousands of duplicate points
        when hand moves slowly, keeping data lean.
        """
        pt = (int(x), int(y), time.time())

        if self._active:
            lx, ly, _ = self._active[-1]
            dist = math.hypot(x - lx, y - ly)
            if dist < DRAW_MIN_POINT_DIST:
                return   # too close — skip

        self._active.append(pt)

    def end_stroke(self):
        """
        Finalise the active stroke (pen lift).
        Moves it to the completed list. Short strokes (< 2 points) are
        discarded — they're likely accidental touches, not intentional marks.
        """
        if len(self._active) >= 2:
            self._strokes.append(list(self._active))
            # Trim old strokes if we've hit the limit
            if len(self._strokes) > DRAW_MAX_STROKES:
                self._strokes = self._strokes[-DRAW_MAX_STROKES:]
        self._active = []

    def clear(self):
        """Remove all strokes including the active one."""
        self._strokes = []
        self._active  = []

    def render(self, canvas):
        """
        Draw all strokes onto the provided canvas (in-place).
        Called after the ASCII layer is rendered, before the HUD,
        so strokes appear on top of characters but under the HUD.
        """
        now = time.time()

        # Render completed strokes
        for stroke in self._strokes:
            self._draw_stroke(canvas, stroke, now, completed=True)

        # Render active stroke (brighter, no fade)
        if len(self._active) >= 2:
            self._draw_stroke(canvas, self._active, now, completed=False)

    def stroke_count(self):
        return len(self._strokes) + (1 if self._active else 0)

    # ── Internal rendering ────────────────────────────────────────────────────

    def _draw_stroke(self, canvas, stroke, now, completed):
        """
        Draw one polyline stroke.

        Fading: if DRAW_STROKE_FADE_SEC > 0, compute alpha from the age of
        the stroke's most recent point. Old strokes fade toward zero opacity.
        We use cv2.addWeighted for blending instead of per-pixel ops — faster.

        Tapering: lines get slightly thinner near the ends, giving strokes
        a calligraphic feel that makes the drawing look more natural.
        """
        if len(stroke) < 2:
            return

        # Compute fade alpha
        alpha = 1.0
        if completed and DRAW_STROKE_FADE_SEC > 0:
            age = now - stroke[-1][2]
            alpha = max(0.0, 1.0 - age / DRAW_STROKE_FADE_SEC)
            if alpha <= 0.01:
                return   # fully faded — skip draw

        color = _DEFAULT_COLOR
        n     = len(stroke)

        for i in range(1, n):
            x0, y0, _ = stroke[i - 1]
            x1, y1, _ = stroke[i]

            # Taper thickness: full at middle, 60% at ends
            t = i / n
            taper  = 0.6 + 0.4 * math.sin(t * math.pi)
            thick  = max(1, int(DRAW_STROKE_THICKNESS * taper))

            if alpha < 1.0:
                # Draw segment to a temp layer and blend
                overlay = canvas.copy()
                cv2.line(overlay, (x0, y0), (x1, y1), color, thick, cv2.LINE_AA)
                cv2.addWeighted(overlay, alpha, canvas, 1 - alpha, 0, canvas)
            else:
                cv2.line(canvas, (x0, y0), (x1, y1), color, thick, cv2.LINE_AA)

            # Small dot at each point for smoother appearance
            cv2.circle(canvas, (x1, y1), max(1, thick // 2), color, -1, cv2.LINE_AA)
