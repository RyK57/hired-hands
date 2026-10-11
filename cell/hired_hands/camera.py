"""The wrist camera on the head arm."""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from .config import settings


class CameraError(RuntimeError):
    pass


class Camera:
    def __init__(self, index: int | None = None, width: int = 640, height: int = 480):
        self.index = settings().camera_index if index is None else index
        self.width = width
        self.height = height
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> "Camera":
        cap = cv2.VideoCapture(self.index, cv2.CAP_AVFOUNDATION)
        if not cap.isOpened():
            raise CameraError(
                f"camera {self.index} did not open; check the USB connection and the camera permission of this terminal"
            )
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap = cap
        return self

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self) -> "Camera":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    def read(self, settle_frames: int = 6) -> np.ndarray:
        """A fresh frame: the first few are discarded so exposure has settled after a move."""
        if self._cap is None:
            self.open()
        assert self._cap is not None
        frame = None
        for _ in range(settle_frames + 1):
            ok, frame = self._cap.read()
            if not ok or frame is None:
                time.sleep(0.05)
        if frame is None:
            raise CameraError(f"camera {self.index} returned no frame")
        return frame

    def capture(self, path: Path, settle_frames: int = 6) -> Path:
        frame = self.read(settle_frames)
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
        return path
