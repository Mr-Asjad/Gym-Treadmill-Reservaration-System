"""Frame sources for the CLI runner. Kept out of the core so the pipeline stays
testable without OpenCV.
"""
from __future__ import annotations

from typing import Iterator, Tuple

from zones import utcnow


class VideoFeed:
    """Webcam (integer source) or video file (path). Yields (timestamp, frame)."""

    def __init__(self, source: str = "0") -> None:
        import cv2  # lazy: only the CLI needs OpenCV

        self._cv2 = cv2
        target = int(source) if str(source).lstrip("-").isdigit() else source
        self._cap = cv2.VideoCapture(target)
        if not self._cap.isOpened():
            raise RuntimeError(f"could not open video source {source!r}")

    def __iter__(self) -> "Iterator[Tuple[object, object]]":
        while True:
            ok, frame = self._cap.read()
            if not ok:
                break
            yield utcnow(), frame

    def release(self) -> None:
        self._cap.release()
