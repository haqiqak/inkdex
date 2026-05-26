# main.py — Phase 8: Touchless Teaching Board System
#
# Primary environment: Board Mode (teaching whiteboard)
# Secondary environment: Camera View (thermal/edge ASCII + Phase 6 modes)
#
# Pipeline (shared):
#   ThreadedCapture → process_frame → ascii_mapper
#   → HandTracker → GestureStateMachine → One Euro Filter
#        ↓                    ↓
#   Camera View          Board Mode
#   (interaction_mode)   (board_state + board_mode)

import time
import signal
import sys

from processor    import process_frame
from ascii_mapper import pixels_to_ascii
from renderer     import (
    init_window, render_thermal, render_edge,
    render_board, render_draw_layer, render_cursor,
    draw_hud, poll_keys, close_window, _canvas
)
from config import (
    TARGET_FPS, RENDER_MODE,
    USE_THREADED_CAPTURE, ENABLE_HAND_TRACKING,
)


def build_camera():
    if USE_THREADED_CAPTURE:
        from threaded_capture import ThreadedCapture
        return ThreadedCapture()
    from capture import WebcamCapture
    return WebcamCapture()


def main():
    camera         = build_camera()
    frame_interval = 1.0 / TARGET_FPS
    render_mode    = RENDER_MODE

    # ── Optional modules ─────────────────────────────────────────────────────
    tracker    = None
    gsm        = None
    mode_mgr   = None
    draw_layer = None
    board      = None
    oef        = None     # One Euro Filter for board tip smoothing

    if ENABLE_HAND_TRACKING:
        from hand_tracker     import HandTracker
        from gesture_state    import GestureStateMachine
        from gesture_actions  import CursorController, ActionController
        from interaction_mode import InteractionModeManager
        from draw_layer       import DrawLayer
        from board_mode       import BoardMode
        from one_euro_filter  import OneEuroCursor
        from config           import OEF_FREQ, OEF_FC_MIN, OEF_BETA

        tracker    = HandTracker()
        gsm        = GestureStateMachine()
        draw_layer = DrawLayer()
        cursor_ctl = CursorController()
        action_ctl = ActionController()
        mode_mgr   = InteractionModeManager(cursor_ctl, action_ctl, draw_layer)
        board      = BoardMode()
        oef        = OneEuroCursor(freq=OEF_FREQ, fc_min=OEF_FC_MIN, beta=OEF_BETA)

        print("Hand tracking    : ENABLED")
        print("Board mode       : ENABLED  — press B to enter")
    else:
        print("Hand tracking    : DISABLED")

    # ── Clean exit ────────────────────────────────────────────────────────────
    def on_exit(sig=None, _=None):
        if board and board.active:
            board.exit()
        if mode_mgr:
            mode_mgr.reset()
        if tracker:
            tracker.release()
        close_window()
        camera.release()
        print("\nExited cleanly.")
        sys.exit(0)

    signal.signal(signal.SIGINT, on_exit)

    print(f"Render mode : {render_mode}  |  Target FPS : {TARGET_FPS}")
    print("Keys: [B] board  [E] edge  [T] tracking  [Q] quit")
    print("Board: [C] clear  [Z] undo  [1-6] colors  [D] draw  [E] erase")
    time.sleep(1.5)
    init_window()

    # ── Runtime state ─────────────────────────────────────────────────────────
    tracking_active = ENABLE_HAND_TRACKING
    frame_count     = 0
    fps_display     = 0.0
    fps_timer       = time.time()
    last_action     = ""
    hand_results    = []
    tip_canvas      = None     # raw tip
    tip_smooth      = None     # One-Euro filtered tip

    # ── Main loop ─────────────────────────────────────────────────────────────
    while True:
        t0 = time.perf_counter()

        # ── Stage 1: Capture ─────────────────────────────────────────────────
        frame = camera.read_frame()
        if frame is None:
            print("\nCamera stalled. Exiting.")
            on_exit()

        # ── Stage 2: Image pipeline ──────────────────────────────────────────
        gray_resized, color_resized, edge_mask = process_frame(frame)
        ascii_rows = pixels_to_ascii(gray_resized)

        # ── Stage 3: Hand tracking ───────────────────────────────────────────
        hand_results = []
        tip_canvas   = None
        tip_smooth   = None

        if tracker and tracking_active:
            hand_results = tracker.process(frame)
            hand_present = len(hand_results) > 0
            raw_gesture  = hand_results[0].gesture if hand_present else 'none'

            # Gesture stabilisation (always runs)
            gsm.update(raw_gesture, hand_present)

            if hand_present:
                tip_canvas = hand_results[0].index_tip_canvas
                # One Euro filter — smooth tip for drawing
                fx, fy     = oef.filter(tip_canvas[0], tip_canvas[1])
                tip_smooth = (int(fx), int(fy))
            else:
                oef.reset()
        else:
            if gsm:    gsm.reset()
            if mode_mgr: mode_mgr.reset()

        # ── Stage 4: Environment routing ─────────────────────────────────────
        board_active = board is not None and board.active

        if board_active:
            # ──────────────────────────────────────────────────────────────────
            # BOARD ENVIRONMENT
            # Pass the smooth tip to board — it needs stable coordinates
            # for good drawing and toolbar hover.
            # ──────────────────────────────────────────────────────────────────
            if tracker and tracking_active:
                result = board.update(
                    gsm.stable_gesture if gsm else 'none',
                    tip_smooth,
                    len(hand_results) > 0
                )
                if result:
                    last_action = result
                    if result == "EXIT BOARD":
                        board_active = False

            # Render board
            render_board(board.render())

            # Skeleton on top
            if tracker and tracking_active and hand_results:
                tracker.draw_skeleton(_canvas, hand_results)

            # Minimal HUD (board has its own toolbar)
            draw_hud(fps_display, render_mode,
                     board_active=True, board=board,
                     last_action=last_action)

        else:
            # ──────────────────────────────────────────────────────────────────
            # CAMERA ENVIRONMENT — thermal/edge ASCII + Phase 6 interaction
            # ──────────────────────────────────────────────────────────────────
            if render_mode == 'thermal':
                render_thermal(ascii_rows, color_resized)
            else:
                render_edge(ascii_rows, color_resized, edge_mask)

            # Phase 6 draw layer
            if draw_layer:
                render_draw_layer(draw_layer)

            # Phase 6 interaction modes (use raw tip, not smoothed)
            if mode_mgr and tracking_active:
                r = mode_mgr.update(
                    gsm.stable_gesture if gsm else 'none',
                    tip_canvas if tip_canvas else (0, 0),
                    tip_canvas is not None
                )
                if r:
                    last_action = r

            # Skeleton
            if tracker and tracking_active and hand_results:
                tracker.draw_skeleton(_canvas, hand_results)

            # Cursor ring
            if tip_canvas and mode_mgr and tracking_active:
                render_cursor(tip_canvas, mode_mgr.mode_name,
                              gsm_locked=gsm.locked if gsm else False)

            # Full HUD
            draw_hud(
                fps             = fps_display,
                render_mode     = render_mode,
                gsm             = gsm if tracking_active else None,
                mode_mgr        = mode_mgr if tracking_active else None,
                last_action     = last_action,
                tracking_active = tracking_active,
                draw_layer      = draw_layer,
                board_active    = False,
            )

        # ── Stage 5: FPS ─────────────────────────────────────────────────────
        frame_count += 1
        elapsed = time.time() - fps_timer
        if elapsed >= 1.0:
            fps_display = frame_count / elapsed
            frame_count = 0
            fps_timer   = time.time()

        # ── Stage 6: Keys ─────────────────────────────────────────────────────
        key = poll_keys()

        if key == 'q':
            on_exit()

        elif key == 'b':
            if board:
                if board.active:
                    board.exit()
                    last_action = "CAMERA MODE"
                else:
                    board.enter()
                    last_action = "BOARD MODE"

        elif board and board.active:
            # Board consumes these keys
            if isinstance(key, str) and len(key) == 1:
                board.handle_key(ord(key))
            elif isinstance(key, int):
                board.handle_key(key)

        else:
            # Camera view keys
            if key == 'e':
                render_mode = 'edge' if render_mode == 'thermal' else 'thermal'
            elif key == 't':
                tracking_active = not tracking_active
                if not tracking_active:
                    if mode_mgr: mode_mgr.reset()
                    if oef:      oef.reset()
                last_action = ''
            elif key == 'c' and draw_layer:
                draw_layer.clear()
                last_action = 'DRAW CLEARED'

        # ── Stage 7: Frame cap ────────────────────────────────────────────────
        sleep_t = frame_interval - (time.perf_counter() - t0)
        if sleep_t > 0:
            time.sleep(sleep_t)


if __name__ == "__main__":
    main()
