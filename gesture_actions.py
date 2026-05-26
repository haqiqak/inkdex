# gesture_actions.py — Phase 6
# CursorController and ActionController.
# InteractionModeManager now owns the high-level logic;
# these classes handle the low-level cursor math and pyautogui calls.

import pyautogui
from one_euro_filter import OneEuroCursor
from config import (
    CELL_W, CELL_H, ASCII_WIDTH, ASCII_HEIGHT,
    ENABLE_PC_CONTROL,
    OEF_FREQ, OEF_FC_MIN, OEF_BETA,
    CURSOR_DEAD_ZONE, CURSOR_MODE,
    CURSOR_RELATIVE_SPEED, CURSOR_EDGE_CLIP,
)

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.0


class CursorController:
    def __init__(self):
        self._screen_w, self._screen_h = pyautogui.size()
        self._canvas_w = ASCII_WIDTH  * CELL_W
        self._canvas_h = ASCII_HEIGHT * CELL_H
        self._oef      = OneEuroCursor(freq=OEF_FREQ, fc_min=OEF_FC_MIN, beta=OEF_BETA)
        self._last_cx  = None
        self._last_cy  = None
        self._clip_x   = self._canvas_w * CURSOR_EDGE_CLIP
        self._clip_y   = self._canvas_h * CURSOR_EDGE_CLIP

    def update(self, canvas_x, canvas_y):
        if (canvas_x < self._clip_x or canvas_x > self._canvas_w - self._clip_x or
                canvas_y < self._clip_y or canvas_y > self._canvas_h - self._clip_y):
            return
        fx, fy = self._oef.filter(canvas_x, canvas_y)
        if CURSOR_MODE == 'absolute':
            self._move_absolute(fx, fy)
        else:
            self._move_relative(fx, fy)
        self._last_cx = fx
        self._last_cy = fy

    def reset(self):
        self._oef.reset()
        self._last_cx = None
        self._last_cy = None

    def _move_absolute(self, fx, fy):
        dz_cx = self._canvas_w / 2
        dz_cy = self._canvas_h / 2
        dz_rx = self._canvas_w * CURSOR_DEAD_ZONE
        dz_ry = self._canvas_h * CURSOR_DEAD_ZONE
        if abs(fx - dz_cx) < dz_rx and abs(fy - dz_cy) < dz_ry:
            return
        sx = int(fx / self._canvas_w * self._screen_w)
        sy = int(fy / self._canvas_h * self._screen_h)
        sx = max(5, min(sx, self._screen_w - 5))
        sy = max(5, min(sy, self._screen_h - 5))
        if ENABLE_PC_CONTROL:
            pyautogui.moveTo(sx, sy, duration=0)

    def _move_relative(self, fx, fy):
        if self._last_cx is None:
            self._last_cx, self._last_cy = fx, fy
            return
        dx = fx - self._last_cx
        dy = fy - self._last_cy
        dz = self._canvas_w * 0.008
        if abs(dx) < dz: dx = 0.0
        if abs(dy) < dz: dy = 0.0
        if dx == 0.0 and dy == 0.0:
            return
        if ENABLE_PC_CONTROL:
            pyautogui.moveRel(int(dx * CURSOR_RELATIVE_SPEED),
                              int(dy * CURSOR_RELATIVE_SPEED), duration=0)


class ActionController:
    def __init__(self):
        self._dragging = False

    def _action_ctl_enabled(self):
        return ENABLE_PC_CONTROL

    def execute(self, action):
        if not ENABLE_PC_CONTROL:
            return f"[demo] {action}"
        if action == 'peace':
            pyautogui.click()
            return "LEFT CLICK"
        elif action == 'fist':
            if not self._dragging:
                pyautogui.mouseDown()
                self._dragging = True
                return "DRAG START"
            else:
                pyautogui.mouseUp()
                self._dragging = False
                return "DRAG END"
        elif action == 'open':
            if self._dragging:
                pyautogui.mouseUp()
                self._dragging = False
                return "DRAG RELEASED"
            pyautogui.scroll(3)
            return "SCROLL UP"
        elif action == 'pinch':
            pyautogui.rightClick()
            return "RIGHT CLICK"
        return f"unhandled:{action}"

    def release_drag(self):
        if self._dragging:
            pyautogui.mouseUp()
            self._dragging = False
