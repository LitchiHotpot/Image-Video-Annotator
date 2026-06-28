"""Media abstraction: load an image or a video and yield frames as QImage."""
import os
import cv2
import numpy as np
from PyQt5.QtGui import QImage

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")
VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".m4v")


def bgr_to_qimage(frame):
    """Convert an OpenCV BGR ndarray to a QImage (RGB888, owns its data)."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb = np.ascontiguousarray(rgb)
    h, w, ch = rgb.shape
    return QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()


class MediaSource:
    def __init__(self, path):
        self.path = path
        self.kind = None          # "image" | "video"
        self.width = 0
        self.height = 0
        self.fps = 0.0
        self.frame_count = 1
        self._cap = None
        self._image = None        # QImage for image kind
        self._open()

    def _open(self):
        ext = os.path.splitext(self.path)[1].lower()
        if ext in IMAGE_EXTS:
            self.kind = "image"
            # imdecode handles non-ASCII paths on Windows
            data = np.fromfile(self.path, dtype=np.uint8)
            frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError(f"Cannot read image: {self.path}")
            self.height, self.width = frame.shape[:2]
            self._image = bgr_to_qimage(frame)
            self.frame_count = 1
        elif ext in VIDEO_EXTS:
            self.kind = "video"
            self._cap = cv2.VideoCapture(self.path)
            if not self._cap.isOpened():
                raise ValueError(f"Cannot open video: {self.path}")
            self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.fps = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
            self.frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    def get_frame(self, index):
        """Return QImage for the given frame index (images ignore the index)."""
        if self.kind == "image":
            return self._image
        index = max(0, min(self.frame_count - 1, index))
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = self._cap.read()
        if not ok:
            return None
        return bgr_to_qimage(frame)

    def release(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
