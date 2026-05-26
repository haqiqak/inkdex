# renderer.py — Phase 8
# Handles both camera view and board mode display.
# Board mode renders directly from board_mode.render().
# Camera view renders ASCII + overlays + full HUD panels.

import sys
import numpy as np
import cv2
from config import (
    CELL_W, CELL_H, ASCII_WIDTH, ASCII_HEIGHT,
    FONT, FONT_SCALE, FONT_THICKNESS, WINDOW_NAME,
    EDGE_COLOR, EDGE_ALPHA, MODE_CURSOR_COLORS,
)

# ── Terminal (Phase 1 compat) ─────────────────────────────────────────────────
def clear_and_render(ascii_rows):
    sys.stdout.write('\033[H' + '\n'.join(ascii_rows))
    sys.stdout.flush()

def hide_cursor():
    sys.stdout.write('\033[?25l'); sys.stdout.flush()

def show_cursor():
    sys.stdout.write('\033[?25h'); sys.stdout.flush()


# ── Canvas ────────────────────────────────────────────────────────────────────
_CANVAS_H = ASCII_HEIGHT * CELL_H
_CANVAS_W = ASCII_WIDTH  * CELL_W
_canvas   = np.zeros((_CANVAS_H, _CANVAS_W, 3), dtype=np.uint8)

_col_xs = np.arange(ASCII_WIDTH)  * CELL_W
_row_ys = (np.arange(ASCII_HEIGHT) + 1) * CELL_H


def init_window():
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN,
                          cv2.WINDOW_FULLSCREEN)


# ── ASCII renderers ───────────────────────────────────────────────────────────
def render_thermal(ascii_rows, color_grid):
    _canvas.fill(0)
    for row_idx, row_str in enumerate(ascii_rows):
        y = int(_row_ys[row_idx])
        for col_idx, char in enumerate(row_str):
            if char == ' ':
                continue
            bgr = color_grid[row_idx, col_idx]
            cv2.putText(_canvas, char, (int(_col_xs[col_idx]), y),
                        FONT, FONT_SCALE,
                        (int(bgr[0]), int(bgr[1]), int(bgr[2])),
                        FONT_THICKNESS, cv2.LINE_AA)


def render_edge(ascii_rows, color_grid, edge_mask):
    _canvas.fill(0)
    ec = np.array(EDGE_COLOR, dtype=np.float32)
    for row_idx, row_str in enumerate(ascii_rows):
        y = int(_row_ys[row_idx])
        for col_idx, char in enumerate(row_str):
            if char == ' ':
                continue
            bgr = color_grid[row_idx, col_idx]
            if edge_mask[row_idx, col_idx] > 0:
                tc    = np.array([bgr[0], bgr[1], bgr[2]], dtype=np.float32)
                mixed = ec * EDGE_ALPHA + tc * (1.0 - EDGE_ALPHA)
                color = (int(mixed[0]), int(mixed[1]), int(mixed[2]))
            else:
                color = (int(bgr[0]), int(bgr[1]), int(bgr[2]))
            cv2.putText(_canvas, char, (int(_col_xs[col_idx]), y),
                        FONT, FONT_SCALE, color, FONT_THICKNESS, cv2.LINE_AA)


# ── Board renderer ────────────────────────────────────────────────────────────
def render_board(board_frame):
    """Copy board canvas into shared canvas and display."""
    np.copyto(_canvas, board_frame)
    _show()


# ── Overlays ──────────────────────────────────────────────────────────────────
def render_draw_layer(draw_layer):
    draw_layer.render(_canvas)


def render_cursor(tip_xy, mode_name, gsm_locked=False):
    if tip_xy is None:
        return
    x, y  = tip_xy
    color = MODE_CURSOR_COLORS.get(mode_name, (200, 200, 200))
    cv2.circle(_canvas, (x, y), 10, color, 2, cv2.LINE_AA)
    cv2.circle(_canvas, (x, y), 3,  color, -1, cv2.LINE_AA)
    if gsm_locked:
        cv2.circle(_canvas, (x, y), 15, color, 1, cv2.LINE_AA)


# ── HUD ───────────────────────────────────────────────────────────────────────
_MODE_ICONS = {
    'navigate': '>',
    'select':   'V',
    'drag':     '[X]',
    'draw':     'D',
    'scroll':   '=',
}
_MODE_LABEL_COLORS = {
    'navigate': (0,   220, 160),
    'select':   (200, 100, 255),
    'drag':     (0,   180, 255),
    'draw':     (80,  80,  255),
    'scroll':   (255, 180,  50),
}
_GESTURE_COLORS_HUD = {
    'point': (0,   220, 255),
    'peace': (80,  255, 80),
    'fist':  (80,  80,  255),
    'open':  (255, 200, 0),
    'pinch': (200, 80,  255),
    'none':  (100, 100, 100),
}


def draw_hud(fps, render_mode, gsm=None, mode_mgr=None,
             last_action='', tracking_active=True,
             draw_layer=None, board_active=False,
             board=None):
    """
    Draws the full HUD onto _canvas then calls imshow.

    board_active=True   → minimal board HUD (board draws its own toolbar)
    board_active=False  → full camera-view HUD with mode + gesture panels
    """
    h, w = _canvas.shape[:2]
    TOP  = 18

    # ── Top bar ───────────────────────────────────────────────────────────────
    cv2.rectangle(_canvas, (0, 0), (w, TOP), (16, 16, 20), -1)

    if board_active:
        hint = f" FPS:{fps:4.1f}  [BOARD]  [B]=camera  [C]=clear  [Z]=undo  [Q]=quit"
        if board:
            hint += f"  strokes:{board.stroke_count}"
        cv2.putText(_canvas, hint, (4, 13),
                    FONT, 0.33, (150, 155, 170), 1, cv2.LINE_AA)
        _show()
        return

    bar_str = (f" FPS:{fps:4.1f}  [{render_mode.upper()}]"
               f"  [E]=edge  [T]=tracking  [B]=board  [Q]=quit"
               f"{'  TRACKING OFF' if not tracking_active else ''}")
    cv2.putText(_canvas, bar_str, (4, 13),
                FONT, 0.33, (160, 165, 180), 1, cv2.LINE_AA)

    if not tracking_active or mode_mgr is None:
        _show()
        return

    # ── Mode panel ────────────────────────────────────────────────────────────
    mode_name  = mode_mgr.mode_name
    mode_color = _MODE_LABEL_COLORS.get(mode_name, (160, 160, 160))
    mode_icon  = _MODE_ICONS.get(mode_name, '?')

    px, py, pw, ph = 6, TOP + 4, 138, 82
    _tr(px, py, px+pw, py+ph)
    cv2.putText(_canvas, 'MODE', (px+4, py+13),
                FONT, 0.28, (90, 92, 100), 1, cv2.LINE_AA)
    cv2.putText(_canvas, f"{mode_icon}  {mode_name.upper()}",
                (px+4, py+32), FONT, 0.50, mode_color, 1, cv2.LINE_AA)
    _pbar(px+4, py+44, pw-8, 6, mode_mgr.dwell_progress, mode_color, (35,36,42))
    cv2.putText(_canvas, f"switch {mode_mgr.dwell_progress*100:3.0f}%",
                (px+4, py+62), FONT, 0.27, (80,82,90), 1, cv2.LINE_AA)
    if mode_name == 'draw' and draw_layer:
        cv2.putText(_canvas, f"strokes:{draw_layer.stroke_count()}",
                    (px+4, py+76), FONT, 0.25, mode_color, 1, cv2.LINE_AA)

    # ── Gesture panel ─────────────────────────────────────────────────────────
    if gsm:
        gx, gy, gw, gh = 6, TOP+ph+8, 138, 70
        _tr(gx, gy, gx+gw, gy+gh)
        gesture = gsm.stable_gesture
        gc      = _GESTURE_COLORS_HUD.get(gesture, (130,132,140))
        cv2.putText(_canvas, gsm.state.name, (gx+4, gy+13),
                    FONT, 0.26, (80,82,90), 1, cv2.LINE_AA)
        cv2.putText(_canvas, gesture, (gx+4, gy+32),
                    FONT, 0.48, gc, 1, cv2.LINE_AA)
        _pbar(gx+4, gy+42, gw-8, 5,
              gsm.dwell_progress,
              (0,255,120) if not gsm.locked else (0,200,255),
              (35,36,42))
        cv2.putText(_canvas, f"dwell {gsm.dwell_progress*100:3.0f}%",
                    (gx+4, gy+59), FONT, 0.25, (80,82,90), 1, cv2.LINE_AA)

    # ── Action bar ────────────────────────────────────────────────────────────
    if last_action:
        cv2.rectangle(_canvas, (0, h-20), (w, h), (16,16,20), -1)
        ac = (0,255,180) if '[demo]' not in last_action else (150,150,0)
        cv2.putText(_canvas, f" {last_action}", (4, h-6),
                    FONT, 0.38, ac, 1, cv2.LINE_AA)

    _show()


# ── Helpers ───────────────────────────────────────────────────────────────────
def _tr(x0, y0, x1, y1, alpha=0.72, color=(12,13,18)):
    """Translucent filled rect."""
    ov = _canvas.copy()
    cv2.rectangle(ov, (x0,y0), (x1,y1), color, -1)
    cv2.addWeighted(ov, alpha, _canvas, 1-alpha, 0, _canvas)


def _pbar(x0, y0, width, height, progress, color, bg):
    cv2.rectangle(_canvas, (x0,y0), (x0+width, y0+height), bg, -1)
    fill = int(width * max(0.0, min(progress, 1.0)))
    if fill > 0:
        cv2.rectangle(_canvas, (x0,y0), (x0+fill, y0+height), color, -1)


def _show():
    cv2.imshow(WINDOW_NAME, _canvas)


def poll_keys():
    key = cv2.waitKey(1) & 0xFF
    if key == 255:        return True
    if key == ord('q'):   return 'q'
    if key == ord('e'):   return 'e'
    if key == ord('t'):   return 't'
    if key == ord('c'):   return 'c'
    if key == ord('b'):   return 'b'
    if key == ord('z'):   return 'z'
    if key == ord('d'):   return 'd'
    for k in [ord(str(i)) for i in range(1, 7)]:
        if key == k:
            return chr(key)
    return True


def close_window():
    cv2.destroyAllWindows()
