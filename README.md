# Inkdex

**A Gesture-Controlled Touchless Teaching and Drawing Board System**

Inkdex is a real-time computer vision system that enables touchless freehand drawing, annotation, and whiteboard interaction using only hand gestures captured through a standard webcam. It requires no specialised hardware, no touch surface, and no physical input device. The system is designed for teaching environments, remote presentations, accessibility applications, and spatial interaction research.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Module Reference](#module-reference)
4. [Interaction Model](#interaction-model)
5. [Gesture Vocabulary](#gesture-vocabulary)
6. [Drawing System](#drawing-system)
7. [Installation](#installation)
8. [Usage](#usage)
9. [Configuration Reference](#configuration-reference)
10. [Tuning Guide](#tuning-guide)
11. [Keyboard Reference](#keyboard-reference)
12. [Project Structure](#project-structure)
13. [Research Context](#research-context)
14. [Roadmap](#roadmap)

---

## System Overview

Inkdex operates as a dual-environment system. The primary environment is the **Board Mode** — a fullscreen gesture-controlled drawing surface analogous to a digital whiteboard. The secondary environment is a **Camera View** that renders the live webcam feed as ASCII thermal art with optional gesture-based desktop interaction. Both environments share a single real-time computer vision pipeline.

The system targets 30 frames per second on consumer hardware and has been tested on Windows 10/11 with standard USB and built-in webcams.

### Core capabilities

- Touchless freehand drawing via index fingertip tracking
- Six selectable brush colors and four brush sizes
- Dedicated erase mode with configurable radius
- Gesture-operated toolbar (no keyboard or mouse required during board usage)
- Undo/clear with gesture or keyboard shortcut
- Explicit interaction state machine preventing accidental triggers
- One Euro Filter cursor smoothing for stable, low-jitter strokes
- Threaded webcam capture decoupled from the render loop
- ASCII thermal camera renderer as an optional secondary display mode

---

## Architecture

The system is structured as a layered pipeline with two parallel rendering environments that share a single tracking backend.

```
┌─────────────────────────────────────────────────────────┐
│                  Shared Tracking Pipeline                │
│  ThreadedCapture → MediaPipe → GestureStateMachine      │
│                             → One Euro Filter           │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
┌────────▼────────┐   ┌──────────▼──────────┐
│  Camera View    │   │    Board Mode        │
│  (ASCII/thermal)│   │  (teaching canvas)   │
│  interaction_   │   │  board_state.py      │
│  mode.py        │   │  board_mode.py       │
└─────────────────┘   └──────────────────────┘
```

### Data flow per frame

1. `ThreadedCapture` — camera runs in a background daemon thread, maintaining a `maxsize=1` queue so the render loop always receives the most recent frame without blocking on hardware timing.
2. `process_frame` — grayscale conversion, CLAHE contrast enhancement, resize to ASCII grid dimensions, Canny edge detection.
3. `HandTracker` — converts BGR frame to RGB, runs MediaPipe Hand Landmarker, extracts 21 landmarks per hand, returns normalised coordinates mapped to canvas pixel space.
4. `GestureStateMachine` — applies a rolling majority-vote buffer (7 frames) over raw gesture classifications to suppress single-frame outliers. Implements hysteresis to prevent dwell counter resets from transient dropouts.
5. `One Euro Filter` — adaptive low-pass filter applied to the index fingertip coordinates. Smoothing strength scales inversely with hand velocity: stationary hands receive heavy smoothing; fast movements receive minimal smoothing.
6. **Environment routing** — `main.py` routes the smoothed tip and stable gesture to either `InteractionModeManager` (camera view) or `BoardMode` + `BoardStateMachine` (board mode).
7. Rendering — ASCII layer or board canvas rendered to OpenCV canvas, overlays applied (skeleton, cursor, HUD), single `cv2.imshow()` call per frame.

---

## Module Reference

| Module | Responsibility |
|---|---|
| `main.py` | Entry point, pipeline orchestration, environment routing, key handling |
| `config.py` | All tunable constants — single source of truth |
| `capture.py` | Single-threaded webcam capture (fallback) |
| `threaded_capture.py` | Producer-consumer threaded capture with `maxsize=1` queue |
| `processor.py` | CLAHE contrast, grayscale, resize, Canny edge detection |
| `ascii_mapper.py` | Vectorised NumPy pixel → character lookup table |
| `hand_tracker.py` | MediaPipe Hand Landmarker wrapper, skeleton drawing |
| `one_euro_filter.py` | Velocity-aware adaptive low-pass filter |
| `gesture_state.py` | Gesture stability: majority vote buffer, hysteresis, dwell |
| `board_state.py` | Board interaction state machine (IDLE/CURSOR/DRAWING/ERASING/PAUSED/MENU) |
| `board_mode.py` | Drawing canvas, stroke storage, eraser, toolbar, rendering |
| `gesture_actions.py` | Cursor mapping (absolute/relative), pyautogui bridge |
| `interaction_mode.py` | Camera-view interaction modes (navigate/select/drag/draw/scroll) |
| `draw_layer.py` | Phase 6 draw overlay for camera view |
| `renderer.py` | OpenCV canvas management, ASCII rendering, HUD panels |

---

## Interaction Model

### Board state machine

The board interaction layer uses an explicit finite state machine with six states. State transitions are gated by gesture dwell (stability frames) and spatial zone detection, preventing accidental triggers from transient hand positions.

```
IDLE ──(hand appears)──▶ CURSOR
CURSOR ──(pinch, stable)──▶ DRAWING
DRAWING ──(open palm)──▶ ERASING
DRAWING ──(fist)──▶ PAUSED
CURSOR ──(enters toolbar zone)──▶ MENU
MENU ──(hover dwell complete)──▶ TOOL_SELECT ──▶ CURSOR
Any state ──(hand lost)──▶ IDLE
```

**Key design decisions:**

- `CURSOR` and `DRAWING` are explicitly separate states. A hand in the drawing zone with a `point` gesture moves the cursor but never produces a stroke. This eliminates the most common source of accidental marks.
- `DRAWING` requires `BS_DWELL_FRAMES` (default: 3) consecutive frames of a stable `pinch` gesture before activating. This prevents a pinch mid-transition from immediately starting a stroke.
- `PAUSED` (fist gesture) suppresses all drawing and erasing. The cursor freezes visually. This is intended for situations where the user needs to reposition their hand without affecting the canvas.
- The toolbar zone (top `BS_TOOLBAR_H` pixels, default: 52px) is spatially exclusive. Any hand position within this zone routes to `MENU` state regardless of gesture, preventing drawing from bleeding into the toolbar region.

### Spatial zones

```
┌──────────────────────────────────────────┐  ← y = 0
│              TOOLBAR ZONE                │  (52px)
│  Draw  Erase  Clear  Undo  Colors  Sizes │
├──────────────────────────────────────────┤  ← y = 52
│                                          │
│                                          │
│            DRAWING ZONE                  │
│                                          │
│   point  → cursor only                   │
│   pinch  → draw stroke                   │
│   open   → erase                         │
│   fist   → pause                         │
│                                          │
└──────────────────────────────────────────┘
```

---

## Gesture Vocabulary

MediaPipe detects 21 landmarks per hand. Gesture classification is rule-based using fingertip-to-knuckle vertical comparisons for finger extension, and Euclidean distance between thumb tip (landmark 4) and index tip (landmark 8) for pinch detection.

| Gesture | Classification rule | Board action |
|---|---|---|
| **Point** | Index finger extended, all others folded | Cursor movement only |
| **Pinch** | Distance(tip_4, tip_8) < 0.06 normalised | Begin/continue drawing stroke |
| **Open** | All five fingers extended | Erase strokes within radius |
| **Fist** | All fingers folded, no pinch | Pause — suppress all actions |
| **Peace** | Index + middle extended, others folded | Cursor (treated as point in board) |
| **None** | No recognised pattern | Hold current state (hysteresis) |

### Gesture stabilisation

Raw per-frame classifications pass through `GestureStateMachine` before reaching the board:

- **Rolling buffer** — a `deque` of length `GESTURE_BUFFER_SIZE` (default: 7) holds recent classifications. The output is the majority vote across the window. A gesture must appear in more than 50% of buffered frames to be reported as stable.
- **Hysteresis** — if the stable gesture drops to `none` for fewer than `GESTURE_HYSTERESIS_FRAMES` (default: 4) consecutive frames, the previous stable gesture is preserved. This prevents dwell counters from resetting during brief occlusions or tracking glitches.
- **Cooldown** — after a state transition, a `BS_STATE_COOLDOWN` (default: 0.12s) lock prevents immediate re-entry of the previous state.

---

## Drawing System

### Stroke representation

Each stroke is stored as a dictionary:

```python
{
    'pts':   [(x, y), ...],   # list of integer canvas pixel coordinates
    'color': (B, G, R),       # BGR tuple
    'size':  int,             # stroke width in pixels
}
```

Strokes accumulate in a list. The canvas is rebuilt from the full stroke list each frame, which ensures erase and undo operations are always visually correct without requiring a secondary buffer.

### Stroke interpolation

When the hand moves faster than the frame rate can sample, consecutive captured points may be spaced further apart than `BOARD_INTERP_MAX_GAP` pixels (default: 12px). In this case, the system linearly interpolates intermediate points at `BOARD_INTERP_MAX_GAP` intervals before appending the endpoint. This prevents dashed-line artefacts at high hand velocities.

### Bezier-style smoothing

Strokes are rendered not as direct polylines but through a midpoint Bezier approximation. For each consecutive triple of points A, B, C, the system computes midpoints M₁ = midpoint(A,B) and M₂ = midpoint(B,C), then draws a line from M₁ to M₂. This produces smooth curves that visually follow the hand's motion without requiring cubic spline computation.

### Cursor smoothing — One Euro Filter

The index fingertip coordinates are processed by a One Euro Filter before reaching the drawing system. The filter adapts its cutoff frequency based on signal velocity:

```
cutoff = fc_min + beta × |velocity|
alpha  = 1 / (1 + 1/(2π × cutoff × (1/freq)))
output = alpha × input + (1 - alpha) × previous_output
```

Default parameters: `fc_min = 1.0 Hz`, `beta = 0.01`, `freq = 30 Hz`.

At rest (`velocity ≈ 0`), the filter applies heavy smoothing (low cutoff), producing stable cursor behaviour. During fast movement (high velocity), smoothing is reduced, preserving responsiveness. This eliminates the core tradeoff of fixed-alpha exponential smoothing.

### Erasing

The eraser checks all stored stroke points against the eraser radius (`BOARD_ERASER_RADIUS`, default: 28px) each frame. Strokes with any point within the radius are processed:
- Strokes with fewer than 4 total points are removed entirely.
- Longer strokes are split at erased indices into surviving segments, each stored as a new independent stroke.

### Undo

Before any canvas-modifying operation (draw start, clear), the current stroke list is deep-copied onto `_undo_stack`. Up to `BOARD_UNDO_DEPTH` (default: 30) snapshots are retained. Undo restores the most recent snapshot and discards the current stroke list.

### Toolbar interaction

The toolbar contains 14 buttons arranged horizontally across the top of the board. Button activation is entirely gesture-driven: hovering the index fingertip over a button increments a dwell counter. After `BOARD_HOVER_DWELL` (default: 22) consecutive hover frames (~0.73s at 30 FPS), the button action fires. A cyan progress bar fills the bottom edge of the button as the dwell accumulates, providing visual feedback on activation progress.

---

## Installation

### Requirements

- Python 3.9 or later
- Webcam (USB or built-in)
- Windows 10/11, macOS 12+, or Linux (Ubuntu 20.04+)

### Dependencies

```
opencv-python
numpy
mediapipe==0.10.9
pyautogui
```

Install:

```bash
pip install -r requirements.txt
```

> **Note:** MediaPipe 0.10.10 and later removed the `solutions` API. Pin to `0.10.9` as specified in `requirements.txt`.

### MediaPipe model file

Inkdex uses the MediaPipe Tasks API, which requires a `.task` model file that is not bundled in the pip package. Download it once:

```bash
curl -o hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task
```

Place `hand_landmarker.task` in the same directory as `main.py`.

---

## Usage

```bash
python main.py
```

The system starts in Camera View (thermal ASCII mode). Press `B` to enter Board Mode.

### Startup sequence

1. Terminal prints tracking and mode status
2. OpenCV window opens fullscreen after 1.5 seconds
3. Camera View is active — thermal ASCII feed with gesture HUD visible
4. Press `B` or hold a peace gesture to enter the teaching board

---

## Configuration Reference

All parameters are in `config.py`. No other file needs modification for standard tuning.

### Board state machine

| Parameter | Default | Effect |
|---|---|---|
| `BS_TOOLBAR_H` | `52` | Pixel height of toolbar zone. Increase for easier toolbar targeting. |
| `BS_DWELL_FRAMES` | `3` | Frames of stable pinch before DRAWING activates. Raise to reduce accidental draw starts. |
| `BS_HYSTERESIS_FRAMES` | `6` | Frames of gesture absence before state falls back. Raise if strokes break mid-draw. |
| `BS_STATE_COOLDOWN` | `0.12` | Seconds locked after state transition. Prevents state bouncing. |

### Cursor smoothing

| Parameter | Default | Effect |
|---|---|---|
| `OEF_FC_MIN` | `1.0` | Minimum cutoff Hz. Lower = smoother at rest, more lag. |
| `OEF_BETA` | `0.01` | Speed coefficient. Higher = less lag during fast moves. |
| `OEF_FREQ` | `30.0` | Expected sample rate. Match to `TARGET_FPS`. |

### Drawing

| Parameter | Default | Effect |
|---|---|---|
| `BOARD_ERASER_RADIUS` | `28` | Eraser radius in canvas pixels. |
| `BOARD_MIN_POINT_DIST` | `2` | Minimum pixel gap between recorded stroke points. |
| `BOARD_INTERP_MAX_GAP` | `12` | Max gap before interpolation fills in points. |
| `BOARD_HOVER_DWELL` | `22` | Frames to hover before toolbar button activates. |
| `BOARD_UNDO_DEPTH` | `30` | Maximum stored undo snapshots. |
| `BOARD_BRUSH_SIZES` | `[2, 4, 8, 14]` | Available brush widths in pixels. |

### Gesture stabilisation

| Parameter | Default | Effect |
|---|---|---|
| `GESTURE_BUFFER_SIZE` | `7` | Majority-vote window length. Larger = more stable, more lag. |
| `GESTURE_DWELL_FRAMES` | `8` | Camera-view action dwell. Not used in board mode directly. |
| `GESTURE_HYSTERESIS_FRAMES` | `4` | Gesture dropout tolerance frames. |

---

## Tuning Guide

**Strokes break mid-draw (dashed line effect)**
```python
BS_HYSTERESIS_FRAMES = 8    # hold DRAWING state longer despite brief gesture dropout
BOARD_INTERP_MAX_GAP = 8    # interpolate more aggressively
```

**Accidental strokes start without intent**
```python
BS_DWELL_FRAMES = 5         # require more stable pinch frames before DRAWING activates
```

**Cursor jitter when hand is still**
```python
OEF_FC_MIN = 0.5            # heavier smoothing at rest
```

**Cursor lags behind fast hand movements**
```python
OEF_BETA = 0.02             # reduce lag at high velocity
```

**Toolbar buttons activate accidentally**
```python
BOARD_HOVER_DWELL = 35      # require longer deliberate hover
```

**Toolbar buttons take too long to activate**
```python
BOARD_HOVER_DWELL = 12      # faster activation
```

**Board appears dark / hard to see**
```python
BOARD_BG_COLOR = (240, 240, 228)    # cream/chalkboard background
```

---

## Keyboard Reference

### Global

| Key | Action |
|---|---|
| `B` | Toggle between Camera View and Board Mode |
| `Q` | Quit |

### Board Mode

| Key | Action |
|---|---|
| `C` | Clear canvas |
| `Z` | Undo last stroke group |
| `D` | Switch to draw mode |
| `E` | Switch to erase mode |
| `1` | White brush |
| `2` | Yellow brush |
| `3` | Green brush |
| `4` | Red brush |
| `5` | Blue brush |
| `6` | Magenta brush |

### Camera View

| Key | Action |
|---|---|
| `E` | Toggle thermal / edge detection render mode |
| `T` | Toggle hand tracking on/off |
| `C` | Clear camera-view draw layer |

---

## Project Structure

```
inkdex/
│
├── main.py                  # Entry point and pipeline orchestration
├── config.py                # All tunable parameters
├── requirements.txt         # Python dependencies
├── hand_landmarker.task     # MediaPipe model file (download separately)
│
├── board_state.py           # Board interaction state machine
├── board_mode.py            # Drawing canvas, toolbar, stroke rendering
│
├── gesture_state.py         # Gesture stabilisation (buffer, hysteresis, dwell)
├── gesture_actions.py       # Cursor mapping and pyautogui bridge
├── interaction_mode.py      # Camera-view interaction mode manager
│
├── one_euro_filter.py       # Velocity-aware adaptive smoothing filter
├── hand_tracker.py          # MediaPipe wrapper, skeleton overlay
│
├── capture.py               # Single-threaded webcam capture
├── threaded_capture.py      # Threaded producer-consumer capture
├── processor.py             # CLAHE, grayscale, resize, edge detection
├── ascii_mapper.py          # Pixel-to-character lookup table
├── draw_layer.py            # Camera-view drawing overlay
└── renderer.py              # OpenCV canvas, ASCII rendering, HUD
```

---

## Research Context

Inkdex is positioned within the field of **gesture-based human–computer interaction (HCI)**, specifically addressing the problem of touchless spatial input for teaching and presentation environments.

### Relevant prior work

The gesture classification approach follows the rule-based landmark comparison methodology used in foundational gesture recognition systems, prioritising interpretability and real-time performance over learned classifiers. The use of MediaPipe's Hand Landmarker is consistent with contemporary computer vision pipelines for hand tracking in resource-constrained settings.

The **One Euro Filter** implementation follows the original formulation by Casiez, Roussel and Vogel (2012), which demonstrated that velocity-adaptive low-pass filtering outperforms fixed-parameter filters for pointing tasks by simultaneously minimising lag during fast movements and jitter during slow movements.

The **gesture state machine** design reflects principles from direct manipulation interfaces (Shneiderman, 1983) and mode-based interaction design, with explicit emphasis on the tension between expressivity (many gestures, many functions) and learnability (few gestures, predictable behaviour). Inkdex resolves this tension by restricting the active vocabulary to five gestures with unambiguous visual and spatial semantics.

The **spatial zone separation** (toolbar vs. drawing area) draws from Fitts' Law considerations and the established principle that interaction targets should be spatially stable and large enough to reduce pointing cost.

### Limitations

- Gesture classification is not handedness-aware. The thumb extension heuristic is calibrated for right-hand use.
- Performance degrades under poor lighting conditions, strong backlighting, or rapid camera motion.
- The system does not persist drawings between sessions. No file I/O is currently implemented.
- Single-hand operation only. Two-hand interaction (e.g., one hand draws, one hand controls tools) is architecturally supported but not yet implemented.

---

## Roadmap

| Feature | Status |
|---|---|
| Freehand drawing with gesture control | ✅ Implemented |
| Toolbar with hover-dwell activation | ✅ Implemented |
| Undo / clear | ✅ Implemented |
| One Euro Filter cursor smoothing | ✅ Implemented |
| Explicit board interaction state machine | ✅ Implemented |
| ASCII thermal camera renderer | ✅ Implemented |
| Save drawing to image file | Planned |
| Multi-page / slide support | Planned |
| Two-hand interaction | Planned |
| Custom gesture training | Planned |
| Shape recognition (circle, line, rectangle) | Planned |
| Collaborative whiteboard over network | Planned |
| Presentation / lecture mode | Planned |
| Accessibility profile (reduced-mobility) | Planned |

---

## License

MIT License. See `LICENSE` for details.

---

## Citation

If you use Inkdex in academic work, please cite:

```
Inkdex: A Gesture-Controlled Touchless Teaching Board System
https://github.com/[your-username]/inkdex
```

---

*Built on MediaPipe, OpenCV, and NumPy.*
