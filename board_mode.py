# board_mode.py — Phase 8 refactor
# Teaching board: stroke storage, erasing, toolbar, rendering.
# Interaction states are delegated to BoardStateMachine (board_state.py).
# This module owns: WHAT gets drawn, WHERE the tools are, HOW it looks.

import cv2
import numpy as np
import math
import time
import copy
from config import (
    BOARD_BG_COLOR, BOARD_COLORS, BOARD_BRUSH_SIZES, BOARD_DEFAULT_BRUSH_IDX,
    BOARD_ERASER_RADIUS, BOARD_MIN_POINT_DIST, BOARD_INTERP_MAX_GAP,
    BOARD_TOOLBAR_H, BOARD_BUTTON_W, BOARD_BUTTON_MARGIN,
    BOARD_HOVER_DWELL, BOARD_UNDO_DEPTH,
    CELL_W, CELL_H, ASCII_WIDTH, ASCII_HEIGHT,
    BS_TOOLBAR_H,
)
from board_state import BoardStateMachine, BoardState


# ── Toolbar layout ────────────────────────────────────────────────────────────
# (label, action_key, group)
_BUTTONS = [
    ('Draw',   'mode_draw',   'mode'),
    ('Erase',  'mode_erase',  'mode'),
    ('Clear',  'do_clear',    'action'),
    ('Undo',   'do_undo',     'action'),
    ('White',  'color_0',     'color'),
    ('Yellow', 'color_1',     'color'),
    ('Green',  'color_2',     'color'),
    ('Red',    'color_3',     'color'),
    ('Blue',   'color_4',     'color'),
    ('Sm',     'size_0',      'size'),
    ('Med',    'size_1',      'size'),
    ('Lg',     'size_2',      'size'),
    ('XL',     'size_3',      'size'),
    ('Exit',   'do_exit',     'action'),
]

# Visual style per group
_GROUP_COLORS = {
    'mode':   (60,  80,  60),
    'action': (60,  50,  80),
    'color':  (50,  60,  80),
    'size':   (60,  70,  60),
}


class BoardMode:
    """
    Teaching whiteboard environment.
    Driven externally by main.py with (stable_gesture, tip_xy, hand_present).
    """

    def __init__(self):
        self._cw = ASCII_WIDTH  * CELL_W
        self._ch = ASCII_HEIGHT * CELL_H

        # Stroke list and undo
        self._strokes       = []
        self._undo_stack    = []
        self._active_stroke = None

        # Tool state
        self.active        = False
        self._draw_mode    = True    # True=draw, False=erase
        self._color        = BOARD_COLORS[0]
        self._brush_idx    = BOARD_DEFAULT_BRUSH_IDX
        self._brush_size   = BOARD_BRUSH_SIZES[self._brush_idx]

        # Cursor / tip
        self._tip      = None
        self._prev_tip = None

        # State machine
        self._bsm = BoardStateMachine()

        # Toolbar hover
        self._hover_btn      = None
        self._hover_frames   = 0
        self._hover_progress = 0.0

        # Status overlay
        self._status       = ""
        self._status_until = 0.0

        # Pre-compute button rects
        self._btn_rects = self._compute_btns()

    # ── Public API ────────────────────────────────────────────────────────────

    def enter(self):
        self.active = True
        self._bsm   = BoardStateMachine()
        self._tip   = None
        self._set_status("Board mode  •  pinch=draw  •  open=erase  •  fist=pause")

    def exit(self):
        self.active = False
        if self._active_stroke:
            self._finish_stroke()

    def update(self, stable_gesture, tip_xy, hand_present):
        """
        Called once per frame. Returns status string or None.
        """
        self._tip = tip_xy

        # Drive state machine
        self._bsm.update(stable_gesture, tip_xy, hand_present)
        state = self._bsm.state

        result = None

        if state == BoardState.IDLE:
            self._on_hand_lost()

        elif state == BoardState.CURSOR:
            self._finish_stroke()   # lift pen if we were drawing

        elif state == BoardState.DRAWING:
            if self._draw_mode and tip_xy:
                result = self._do_draw(tip_xy)

        elif state == BoardState.ERASING:
            self._finish_stroke()
            if tip_xy:
                result = self._do_erase(tip_xy)

        elif state == BoardState.PAUSED:
            self._finish_stroke()
            result = "PAUSED"

        elif state == BoardState.MENU:
            self._finish_stroke()
            if tip_xy:
                result = self._update_toolbar(tip_xy)

        if state != BoardState.MENU:
            self._hover_btn      = None
            self._hover_frames   = 0
            self._hover_progress = 0.0

        self._prev_tip = tip_xy
        return result

    def render(self):
        """Build and return the display frame (H, W, 3)."""
        canvas = np.full((self._ch, self._cw, 3), BOARD_BG_COLOR, dtype=np.uint8)

        # Strokes
        for s in self._strokes:
            self._render_stroke(canvas, s)
        if self._active_stroke and len(self._active_stroke['pts']) >= 2:
            self._render_stroke(canvas, self._active_stroke)

        # Erase preview
        state = self._bsm.state
        if state == BoardState.ERASING and self._tip:
            cv2.circle(canvas, self._tip, BOARD_ERASER_RADIUS,
                       (70, 70, 70), 1, cv2.LINE_AA)

        # Cursor
        self._render_cursor(canvas)

        # Toolbar
        self._render_toolbar(canvas)

        # State indicator (small tag bottom-right)
        self._render_state_tag(canvas)

        # Status message
        if self._status and time.time() < self._status_until:
            self._render_status(canvas)

        return canvas

    def handle_key(self, key):
        if key == ord('c'):
            self._do_clear(); return True
        if key == ord('z'):
            self._do_undo(); return True
        if key == ord('d'):
            self._draw_mode = True
            self._set_status("Draw mode"); return True
        if key == ord('e'):
            self._draw_mode = False
            self._set_status("Erase mode"); return True
        for i, k in enumerate([ord('1'), ord('2'), ord('3'),
                                ord('4'), ord('5'), ord('6')]):
            if key == k and i < len(BOARD_COLORS):
                self._color = BOARD_COLORS[i]
                self._draw_mode = True
                self._set_status(f"Color {i+1}"); return True
        return False

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _do_draw(self, tip):
        if self._active_stroke is None:
            self._snapshot()
            self._active_stroke = {
                'pts':   [tip],
                'color': self._color,
                'size':  self._brush_size,
            }
        else:
            pts  = self._active_stroke['pts']
            lx, ly = pts[-1]
            dx, dy = tip[0]-lx, tip[1]-ly
            dist   = math.hypot(dx, dy)
            if dist < BOARD_MIN_POINT_DIST:
                return "DRAWING"
            # Interpolate if gap too large
            if dist > BOARD_INTERP_MAX_GAP:
                steps = int(dist / BOARD_INTERP_MAX_GAP) + 1
                for s in range(1, steps):
                    t  = s / steps
                    pts.append((int(lx + dx*t), int(ly + dy*t)))
            pts.append(tip)
        return "DRAWING"

    def _do_erase(self, tip):
        r2   = BOARD_ERASER_RADIUS ** 2
        tx, ty = tip
        kept = []
        changed = False
        for stroke in self._strokes:
            close = [i for i, (px, py) in enumerate(stroke['pts'])
                     if (px-tx)**2 + (py-ty)**2 <= r2]
            if not close:
                kept.append(stroke); continue
            changed = True
            if len(stroke['pts']) <= 3:
                continue   # short stroke — remove entirely
            # Split at erased indices
            erased = set(close)
            seg = []
            for i, pt in enumerate(stroke['pts']):
                if i in erased:
                    if len(seg) >= 2:
                        kept.append({'pts': seg, 'color': stroke['color'],
                                     'size': stroke['size']})
                    seg = []
                else:
                    seg.append(pt)
            if len(seg) >= 2:
                kept.append({'pts': seg, 'color': stroke['color'],
                             'size': stroke['size']})
        if changed:
            self._strokes = kept
        return "ERASING"

    def _finish_stroke(self):
        if self._active_stroke and len(self._active_stroke['pts']) >= 2:
            self._strokes.append(self._active_stroke)
        self._active_stroke = None

    def _on_hand_lost(self):
        self._finish_stroke()
        self._tip            = None
        self._hover_btn      = None
        self._hover_frames   = 0
        self._hover_progress = 0.0

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def _compute_btns(self):
        rects = []
        x = BOARD_BUTTON_MARGIN
        for _ in _BUTTONS:
            rects.append((x, 4, x + BOARD_BUTTON_W, BS_TOOLBAR_H - 4))
            x += BOARD_BUTTON_W + BOARD_BUTTON_MARGIN
        return rects

    def _update_toolbar(self, tip):
        tx = tip[0]
        hit = None
        for i, (x0, y0, x1, y1) in enumerate(self._btn_rects):
            if x0 <= tx <= x1:
                hit = i; break

        if hit != self._hover_btn:
            self._hover_btn      = hit
            self._hover_frames   = 0
            self._hover_progress = 0.0
            return None

        if hit is None:
            return None

        self._hover_frames   += 1
        self._hover_progress  = min(self._hover_frames / BOARD_HOVER_DWELL, 1.0)

        if self._hover_frames >= BOARD_HOVER_DWELL:
            self._hover_frames   = 0
            self._hover_progress = 0.0
            return self._fire_action(_BUTTONS[hit][1])
        return None

    def _fire_action(self, action):
        if action == 'mode_draw':
            self._draw_mode = True
            self._set_status("Draw mode")
            return "DRAW MODE"
        if action == 'mode_erase':
            self._draw_mode = False
            self._set_status("Erase mode")
            return "ERASE MODE"
        if action == 'do_clear':
            self._do_clear()
            return "CLEARED"
        if action == 'do_undo':
            self._do_undo()
            return "UNDO"
        if action == 'do_exit':
            self.exit()
            return "EXIT BOARD"
        if action.startswith('color_'):
            idx = int(action.split('_')[1])
            if idx < len(BOARD_COLORS):
                self._color     = BOARD_COLORS[idx]
                self._draw_mode = True
                self._set_status(f"Color {idx+1}")
                return f"COLOR {idx+1}"
        if action.startswith('size_'):
            idx = int(action.split('_')[1])
            if idx < len(BOARD_BRUSH_SIZES):
                self._brush_idx  = idx
                self._brush_size = BOARD_BRUSH_SIZES[idx]
                self._set_status(f"Brush {self._brush_size}px")
                return f"BRUSH {self._brush_size}px"
        return None

    def _do_clear(self):
        self._snapshot()
        self._strokes       = []
        self._active_stroke = None
        self._set_status("Board cleared")

    def _do_undo(self):
        if self._undo_stack:
            self._strokes       = self._undo_stack.pop()
            self._active_stroke = None
            self._set_status(f"Undo  ({len(self._undo_stack)} left)")
        else:
            self._set_status("Nothing to undo")

    def _snapshot(self):
        if len(self._undo_stack) >= BOARD_UNDO_DEPTH:
            self._undo_stack.pop(0)
        self._undo_stack.append(copy.deepcopy(self._strokes))

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render_stroke(self, canvas, stroke):
        """Smooth bezier-style rendering through midpoints."""
        pts   = stroke['pts']
        color = stroke['color']
        size  = stroke['size']
        n     = len(pts)
        if n < 2:
            return
        if n == 2:
            cv2.line(canvas, pts[0], pts[1], color, size, cv2.LINE_AA)
            return
        for i in range(1, n-1):
            mx0 = ((pts[i-1][0]+pts[i][0])//2, (pts[i-1][1]+pts[i][1])//2)
            mx1 = ((pts[i][0]+pts[i+1][0])//2, (pts[i][1]+pts[i+1][1])//2)
            cv2.line(canvas, mx0, mx1, color, size, cv2.LINE_AA)
            cv2.circle(canvas, pts[i], max(1, size//2), color, -1, cv2.LINE_AA)
        m0 = ((pts[0][0]+pts[1][0])//2, (pts[0][1]+pts[1][1])//2)
        cv2.line(canvas, pts[0], m0, color, size, cv2.LINE_AA)
        m1 = ((pts[-2][0]+pts[-1][0])//2, (pts[-2][1]+pts[-1][1])//2)
        cv2.line(canvas, m1, pts[-1], color, size, cv2.LINE_AA)

    def _render_cursor(self, canvas):
        if not self._tip:
            return
        tx, ty = self._tip
        if ty < BS_TOOLBAR_H + 4:
            return
        state = self._bsm.state

        if state == BoardState.DRAWING:
            r = max(2, self._brush_size//2)
            cv2.circle(canvas, (tx, ty), r+3, self._color, 1, cv2.LINE_AA)
            cv2.circle(canvas, (tx, ty), r,   self._color, -1, cv2.LINE_AA)
        elif state == BoardState.ERASING:
            cv2.circle(canvas, (tx, ty), BOARD_ERASER_RADIUS, (80,80,80), 1, cv2.LINE_AA)
            cv2.circle(canvas, (tx, ty), 3, (100,100,100), -1, cv2.LINE_AA)
        elif state == BoardState.PAUSED:
            cv2.circle(canvas, (tx, ty), 8, (100,100,100), 1, cv2.LINE_AA)
            cv2.line(canvas, (tx-4, ty), (tx+4, ty), (100,100,100), 2)
        elif state == BoardState.CURSOR:
            color = self._color if self._draw_mode else (100,100,100)
            cv2.circle(canvas, (tx, ty), 6, color, 1, cv2.LINE_AA)
            cv2.circle(canvas, (tx, ty), 2, color, -1, cv2.LINE_AA)
        else:
            cv2.circle(canvas, (tx, ty), 5, (160,160,160), 1, cv2.LINE_AA)

    def _render_toolbar(self, canvas):
        h, w = canvas.shape[:2]
        # Background
        ov = canvas.copy()
        cv2.rectangle(ov, (0, 0), (w, BS_TOOLBAR_H), (20, 22, 28), -1)
        cv2.addWeighted(ov, 0.90, canvas, 0.10, 0, canvas)
        cv2.line(canvas, (0, BS_TOOLBAR_H), (w, BS_TOOLBAR_H), (55, 58, 70), 1)

        font = cv2.FONT_HERSHEY_SIMPLEX

        for i, ((label, action, group), rect) in enumerate(zip(_BUTTONS, self._btn_rects)):
            x0, y0, x1, y1 = rect
            bh = y1 - y0
            bw = x1 - x0

            is_active  = self._btn_active(action)
            is_hovered = (i == self._hover_btn)

            if is_active:
                bg  = (45, 80, 55)
                bdr = (80, 200, 100)
                tc  = (200, 240, 210)
            elif is_hovered:
                bg  = (38, 42, 58)
                bdr = (110, 120, 180)
                tc  = (200, 200, 220)
            else:
                bg  = _GROUP_COLORS.get(group, (32, 32, 40))
                bdr = (48, 52, 65)
                tc  = (155, 158, 170)

            cv2.rectangle(canvas, (x0, y0), (x1, y1), bg,  -1)
            cv2.rectangle(canvas, (x0, y0), (x1, y1), bdr,  1)

            # Color swatch for color buttons
            if action.startswith('color_'):
                idx = int(action.split('_')[1])
                sc  = BOARD_COLORS[idx] if idx < len(BOARD_COLORS) else (200,200,200)
                sw  = 8
                sy  = y0 + bh//2
                cv2.rectangle(canvas, (x0+4, sy-sw//2), (x0+4+sw, sy+sw//2), sc, -1)
                cv2.putText(canvas, label, (x0+16, sy+4), font, 0.28, tc, 1, cv2.LINE_AA)
            else:
                cy = y0 + bh//2 + 4
                cv2.putText(canvas, label, (x0+5, cy), font, 0.30, tc, 1, cv2.LINE_AA)

            # Dwell fill bar (bottom of button)
            if is_hovered and self._hover_progress > 0:
                fw = int(bw * self._hover_progress)
                fo = canvas.copy()
                cv2.rectangle(fo, (x0, y1-4), (x0+fw, y1), (100, 210, 255), -1)
                cv2.addWeighted(fo, 0.75, canvas, 0.25, 0, canvas)

        # Current tool indicator (right of last button)
        ix = self._btn_rects[-1][2] + 14
        if ix + 90 < w:
            cv2.circle(canvas, (ix+8, BS_TOOLBAR_H//2),
                       max(2, self._brush_size//2+1), self._color, -1, cv2.LINE_AA)
            mode_str = "DRAW" if self._draw_mode else "ERASE"
            cv2.putText(canvas, mode_str, (ix+20, BS_TOOLBAR_H//2+4),
                        font, 0.30, (140,145,160), 1, cv2.LINE_AA)

    def _render_state_tag(self, canvas):
        """Small state label bottom-right corner."""
        h, w = canvas.shape[:2]
        state_str = self._bsm.state_name.upper()
        cv2.putText(canvas, state_str, (w-80, h-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.30, (55, 60, 70), 1, cv2.LINE_AA)

    def _render_status(self, canvas):
        h, w = canvas.shape[:2]
        txt  = self._status
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
        tx   = (w - tw) // 2
        ty   = h - 22
        ov   = canvas.copy()
        cv2.rectangle(ov, (tx-10, ty-th-6), (tx+tw+10, ty+6), (18,20,26), -1)
        cv2.addWeighted(ov, 0.82, canvas, 0.18, 0, canvas)
        cv2.putText(canvas, txt, (tx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (190,192,200), 1, cv2.LINE_AA)

    def _btn_active(self, action):
        if action == 'mode_draw'  and self._draw_mode:       return True
        if action == 'mode_erase' and not self._draw_mode:   return True
        if action.startswith('color_'):
            idx = int(action.split('_')[1])
            return idx < len(BOARD_COLORS) and BOARD_COLORS[idx] == self._color
        if action.startswith('size_'):
            return int(action.split('_')[1]) == self._brush_idx
        return False

    def _set_status(self, msg, sec=2.2):
        self._status       = msg
        self._status_until = time.time() + sec

    # ── Properties ────────────────────────────────────────────────────────────
    @property
    def bsm(self):
        return self._bsm

    @property
    def stroke_count(self):
        return len(self._strokes) + (1 if self._active_stroke else 0)
