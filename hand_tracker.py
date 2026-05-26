import cv2
import numpy as np
import mediapipe as mp

from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from config import (
    ASCII_WIDTH,
    ASCII_HEIGHT,
    CELL_W,
    CELL_H,
    HAND_DETECTION_CONFIDENCE
)

# Landmark indices
WRIST        = 0
THUMB_TIP    = 4
INDEX_TIP    = 8
MIDDLE_TIP   = 12
RING_TIP     = 16
PINKY_TIP    = 20

THUMB_MCP    = 2
INDEX_MCP    = 5
MIDDLE_MCP   = 9
RING_MCP     = 13
PINKY_MCP    = 17


class HandTracker:
    def __init__(self):

        # Canvas scaling
        self._canvas_h = ASCII_HEIGHT * CELL_H
        self._canvas_w = ASCII_WIDTH * CELL_W

        # --- MediaPipe Tasks API setup ---
        base_options = python.BaseOptions(
            model_asset_path="hand_landmarker.task"
        )

        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=2,
            min_hand_detection_confidence=HAND_DETECTION_CONFIDENCE,
            min_tracking_confidence=0.5
        )

        self.detector = vision.HandLandmarker.create_from_options(options)

    def process(self, frame_bgr):

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb
        )

        result = self.detector.detect(mp_image)

        if not result.hand_landmarks:
            return []

        hand_results = []

        for hand_landmarks in result.hand_landmarks:
            hr = self._extract(hand_landmarks, frame_bgr.shape)
            hand_results.append(hr)

        return hand_results

    def _extract(self, landmarks, frame_shape):

        fh, fw = frame_shape[:2]

        lms = np.array([
            [lm.x, lm.y] for lm in landmarks
        ])

        frame_pts = np.array([
            [x * fw, y * fh] for x, y in lms
        ])

        canvas_pts = np.array([
            [x * self._canvas_w, y * self._canvas_h]
            for x, y in lms
        ])

        # NO smoothing here anymore.
        # Phase 5 moved smoothing into one_euro_filter.py
        raw_x, raw_y = canvas_pts[INDEX_TIP]
        tip_point = (int(raw_x), int(raw_y))

        fingers_up = self._fingers_extended(lms)
        gesture = self._classify_gesture(fingers_up, lms)

        return HandResult(
            landmarks_frame=frame_pts,
            landmarks_canvas=canvas_pts,
            fingers_up=fingers_up,
            gesture=gesture,
            index_tip_canvas=tip_point,
            raw_landmarks=landmarks
        )

    def _fingers_extended(self, lms):

        def up(tip, mcp):
            return lms[tip][1] < lms[mcp][1]

        return {
            "thumb": abs(
                lms[THUMB_TIP][0] - lms[THUMB_MCP][0]
            ) > 0.08,

            "index": up(INDEX_TIP, INDEX_MCP),
            "middle": up(MIDDLE_TIP, MIDDLE_MCP),
            "ring": up(RING_TIP, RING_MCP),
            "pinky": up(PINKY_TIP, PINKY_MCP),
        }

    def _classify_gesture(self, fingers_up, lms):

        i = fingers_up["index"]
        m = fingers_up["middle"]
        r = fingers_up["ring"]
        p = fingers_up["pinky"]

        thumb_tip = lms[THUMB_TIP]
        index_tip = lms[INDEX_TIP]

        pinch = (
            (thumb_tip[0] - index_tip[0]) ** 2 +
            (thumb_tip[1] - index_tip[1]) ** 2
        ) ** 0.5

        if pinch < 0.06:
            return "pinch"

        if i and not m and not r and not p:
            return "point"

        if i and m and not r and not p:
            return "peace"

        if not i and not m and not r and not p:
            return "fist"

        if i and m and r and p:
            return "open"

        return "none"

    def release(self):
        pass

    def draw_skeleton(self, canvas, hand_results):

        for hr in hand_results:

            pts = hr.landmarks_canvas.astype(int)

            connections = [
                (0, 5), (5, 6), (6, 7), (7, 8),
                (9, 10), (10, 11), (11, 12),
                (13, 14), (14, 15), (15, 16),
                (17, 18), (18, 19), (19, 20),
                (0, 2), (2, 4),
            ]

            for a, b in connections:
                cv2.line(
                    canvas,
                    tuple(pts[a]),
                    tuple(pts[b]),
                    (80, 80, 80),
                    1,
                    cv2.LINE_AA
                )

            for idx, point in enumerate(pts):

                radius = 5 if idx in [4, 8, 12, 16, 20] else 3

                cv2.circle(
                    canvas,
                    tuple(point),
                    radius,
                    (0, 200, 255),
                    -1
                )

            cv2.circle(
                canvas,
                hr.index_tip_canvas,
                8,
                (0, 255, 255),
                2,
                cv2.LINE_AA
            )

            wrist = tuple(pts[0])

            cv2.putText(
                canvas,
                hr.gesture,
                (wrist[0] - 30, wrist[1] + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 200),
                1,
                cv2.LINE_AA
            )


class HandResult:

    __slots__ = [
        "landmarks_frame",
        "landmarks_canvas",
        "fingers_up",
        "gesture",
        "index_tip_canvas",
        "raw_landmarks",
    ]

    def __init__(self, **kwargs):

        for k, v in kwargs.items():
            setattr(self, k, v)