# config.py — unified config for all phases.
import cv2

# ── Camera ────────────────────────────────────────────────────────────────────
CAMERA_INDEX    = 0
FLIP_HORIZONTAL = True

# ── ASCII grid ────────────────────────────────────────────────────────────────
ASCII_WIDTH  = 120
ASCII_HEIGHT = 45
ASCII_CHARS  = " .`'^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhaeo*#MW&8%B@$"

# ── Frame rate ────────────────────────────────────────────────────────────────
TARGET_FPS = 30

# ── Render mode ───────────────────────────────────────────────────────────────
RENDER_MODE = 'thermal'   # 'thermal' | 'edge' — ASCII is secondary

# ── Colormap ──────────────────────────────────────────────────────────────────
COLORMAP = cv2.COLORMAP_INFERNO

# ── Edge detection ────────────────────────────────────────────────────────────
CANNY_LOW  = 50
CANNY_HIGH = 150
EDGE_COLOR = (0, 255, 255)
EDGE_ALPHA = 0.85

# ── Font / window ─────────────────────────────────────────────────────────────
FONT           = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE     = 0.4
FONT_THICKNESS = 1
CELL_W         = 7
CELL_H         = 13
WINDOW_NAME    = "Touchless Teaching Board"

# ── Performance ───────────────────────────────────────────────────────────────
USE_THREADED_CAPTURE = True

# ── Hand tracking ─────────────────────────────────────────────────────────────
HAND_DETECTION_CONFIDENCE = 0.7
HAND_TRACKING_CONFIDENCE  = 0.6
MAX_HANDS                 = 1
ENABLE_HAND_TRACKING      = True

# ── One Euro Filter ───────────────────────────────────────────────────────────
OEF_FREQ   = 30.0
OEF_FC_MIN = 1.0
OEF_BETA   = 0.01

# ── Gesture state machine (Phase 5) ──────────────────────────────────────────
GESTURE_BUFFER_SIZE       = 7
GESTURE_DWELL_FRAMES      = 8
GESTURE_HYSTERESIS_FRAMES = 4
GESTURE_COOLDOWN_SEC      = 0.8

# ── Camera-view interaction (Phase 6) ────────────────────────────────────────
ENABLE_PC_CONTROL     = False
CURSOR_DEAD_ZONE      = 0.04
CURSOR_MODE           = 'relative'
CURSOR_RELATIVE_SPEED = 2.5
CURSOR_EDGE_CLIP      = 0.08
SCROLL_SENSITIVITY    = 0.15

MODE_ENTRY_GESTURES = {
    'navigate': 'point',
    'select':   'peace',
    'drag':     'fist',
    'draw':     'pinch',
    'scroll':   'open',
}
MODE_DWELL_FRAMES    = 10
MODE_SWITCH_COOLDOWN = 1.2
MODE_CURSOR_COLORS   = {
    'navigate': (0,   220, 160),
    'select':   (200, 100, 255),
    'drag':     (0,   180, 255),
    'draw':     (80,  80,  255),
    'scroll':   (255, 180,  50),
}

# ── Phase 6 draw layer (camera view) ─────────────────────────────────────────
DRAW_MAX_STROKES      = 50
DRAW_MIN_POINT_DIST   = 3
DRAW_STROKE_THICKNESS = 2
DRAW_STROKE_COLOR     = None
DRAW_STROKE_FADE_SEC  = 0.0

# ── Board state machine (Phase 8) ────────────────────────────────────────────
# Height of toolbar zone in pixels. Hand above this line → MENU state.
BS_TOOLBAR_H        = 52

# Frames a gesture must be stable before DRAWING/ERASING state activates.
# Raise to reduce accidental drawing start. Lower for faster response.
# At 30 FPS: 3 frames ≈ 100ms.
BS_DWELL_FRAMES     = 3

# Frames without recognisable gesture before falling back to CURSOR.
BS_HYSTERESIS_FRAMES = 6

# Seconds to ignore new state transitions after entering a state.
# Prevents instant bouncing between states.
BS_STATE_COOLDOWN   = 0.12

# ── Board visuals ─────────────────────────────────────────────────────────────
BOARD_BG_COLOR          = (22, 24, 30)    # near-black board
BOARD_COLORS = [
    (255, 255, 255),   # white
    (80,  220, 255),   # warm yellow (BGR)
    (80,  220, 100),   # green
    (80,  80,  255),   # red
    (255, 160, 60),    # blue
    (220, 80,  220),   # magenta
]
BOARD_BRUSH_SIZES       = [2, 4, 8, 14]
BOARD_DEFAULT_BRUSH_IDX = 1
BOARD_ERASER_RADIUS     = 28
BOARD_MIN_POINT_DIST    = 2
BOARD_INTERP_MAX_GAP    = 12
BOARD_TOOLBAR_H         = BS_TOOLBAR_H    # alias
BOARD_BUTTON_W          = 68
BOARD_BUTTON_MARGIN     = 6
BOARD_HOVER_DWELL       = 22
BOARD_UNDO_DEPTH        = 30
