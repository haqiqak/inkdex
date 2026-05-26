# capture.py
# Responsibility: open the webcam and deliver raw frames.
# Nothing else — no processing happens here.

import cv2
from config import CAMERA_INDEX, FLIP_HORIZONTAL


class WebcamCapture:
    def __init__(self):
        self.cap = cv2.VideoCapture(CAMERA_INDEX)

        if not self.cap.isOpened():
            raise RuntimeError(
                f"Could not open camera at index {CAMERA_INDEX}.\n"
                "Try changing CAMERA_INDEX in config.py (try 1 or 2)."
            )

        # Request a common resolution from the driver.
        # The driver may ignore this — check actual size with get() if needed.
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    def read_frame(self):
        """
        Grabs one frame from the camera.
        Returns a NumPy array (height, width, 3) in BGR colour space,
        or None if the grab failed.
        """
        ret, frame = self.cap.read()

        if not ret:
            return None

        if FLIP_HORIZONTAL:
            # flipCode 1 = mirror left-right
            frame = cv2.flip(frame, 1)

        return frame

    def release(self):
        """Release the camera hardware. Always call on exit."""
        self.cap.release()
