# threaded_capture.py
# A drop-in replacement for WebcamCapture that runs the camera read
# in a background thread.
#
# Why this helps:
#   cap.read() blocks for ~33ms waiting for the next camera frame.
#   In single-threaded mode that stall freezes your entire render loop.
#   Here Thread 1 always keeps the queue filled with the freshest frame.
#   Thread 2 (your main loop) just does queue.get() — never blocks on camera.
#
# Queue design:
#   maxsize=1  — we only ever want the LATEST frame, not a backlog.
#   When the queue is full and a new frame arrives, we discard the old one.
#   This means we trade frame history for freshness — correct for real-time.

import cv2
import threading
import queue
from config import CAMERA_INDEX, FLIP_HORIZONTAL


class ThreadedCapture:
    def __init__(self):
        self.cap = cv2.VideoCapture(CAMERA_INDEX)

        if not self.cap.isOpened():
            raise RuntimeError(
                f"Could not open camera at index {CAMERA_INDEX}.\n"
                "Try changing CAMERA_INDEX in config.py (try 1 or 2)."
            )

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # Queue holds at most 1 frame. Producer replaces stale frames
        # rather than building a buffer.
        self._q = queue.Queue(maxsize=1)

        # Daemon=True means this thread dies automatically when main exits.
        # Without daemon=True, your program won't quit even after Ctrl+C
        # because Python waits for all threads to finish.
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._producer, daemon=True)
        self._thread.start()

    def _producer(self):
        """
        Runs in Thread 1.
        Continuously reads frames and pushes the latest one to the queue.
        Old frames are discarded when a newer one arrives.
        """
        while not self._stop_event.is_set():
            ret, frame = self.cap.read()
            if not ret:
                continue

            if FLIP_HORIZONTAL:
                frame = cv2.flip(frame, 1)

            # If queue is full (consumer is slow), discard the old frame
            # and put the new one in — always stay fresh.
            if self._q.full():
                try:
                    self._q.get_nowait()   # discard stale frame
                except queue.Empty:
                    pass

            try:
                self._q.put_nowait(frame)
            except queue.Full:
                pass   # race condition safety — just skip this frame

    def read_frame(self):
        """
        Called by Thread 2 (main loop).
        Blocks for up to 0.5s waiting for the next frame.
        Returns None on timeout (camera stalled or disconnected).
        
        0.5s timeout: generous enough to handle brief camera hiccups,
        short enough to still detect disconnection quickly.
        """
        try:
            return self._q.get(timeout=0.5)
        except queue.Empty:
            return None

    def release(self):
        """Stop the producer thread and release the camera."""
        self._stop_event.set()
        self._thread.join(timeout=2.0)
        self.cap.release()
