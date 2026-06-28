"""Canvas widgets.

``ImageView``  - base widget: shows an image/frame with fit / zoom / pan and
                maps between widget and original-image pixel coordinates.
``Canvas``     - point / box annotation (single media tool).
``PairCanvas`` - lightweight click surface for point-pair annotation
                (used by the dual-view matching tool).
"""
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QRectF, pyqtSignal, QPointF
from PyQt5.QtGui import QPainter, QPen, QColor, QBrush, QImage, QPixmap, QFont

MODE_POINT = "point"
MODE_BOX = "box"

# Palette cycled by class / pair index.
PALETTE = [
    (231, 76, 60), (46, 204, 113), (52, 152, 219), (241, 196, 15),
    (155, 89, 182), (26, 188, 156), (230, 126, 34), (52, 73, 94),
    (236, 64, 122), (124, 179, 66), (0, 172, 193), (255, 112, 67),
]


def class_color(index):
    if index < 0:
        return QColor(180, 180, 180)
    r, g, b = PALETTE[index % len(PALETTE)]
    return QColor(r, g, b)


class ImageView(QWidget):
    """Displays a frame and handles fit / zoom / pan + coordinate mapping.

    Subclasses implement the interaction hooks ``on_left_press`` /
    ``on_right_press`` / ``on_move`` / ``on_left_release`` (all receive image
    coordinates) and ``paint_overlay`` for their own drawing.
    """

    statusMessage = pyqtSignal(str)

    MIN_SCALE = 0.02
    MAX_SCALE = 80.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._pixmap = None
        self._img_w = 0
        self._img_h = 0

        self._scale = 1.0
        self._off_x = 0.0
        self._off_y = 0.0
        self._fit_scale = 1.0
        self._user_zoomed = False
        self._media_dims = None

        self._panning = False
        self._pan_start = None
        self._pan_off0 = (0.0, 0.0)

        self._placeholder = "打开文件开始"

    # ---- image ----
    def set_image(self, qimage):
        if qimage is not None:
            self._pixmap = QPixmap.fromImage(qimage)
            self._img_w = qimage.width()
            self._img_h = qimage.height()
        else:
            self._pixmap = None
            self._img_w = self._img_h = 0
        dims = (self._img_w, self._img_h)
        if dims != self._media_dims:
            self._media_dims = dims
            self._fit()
        else:
            self._compute_fit_scale()
        self.update()

    @property
    def has_image(self):
        return self._pixmap is not None

    # ---- transform ----
    def resizeEvent(self, e):
        self._compute_fit_scale()
        if not self._user_zoomed:
            self._fit()
        super().resizeEvent(e)

    def _compute_fit_scale(self):
        if self._img_w == 0 or self._img_h == 0:
            return
        sw, sh = self.width(), self.height()
        self._fit_scale = min(sw / self._img_w, sh / self._img_h)

    def _fit(self):
        if self._img_w == 0 or self._img_h == 0:
            return
        self._compute_fit_scale()
        sw, sh = self.width(), self.height()
        self._scale = self._fit_scale
        self._off_x = (sw - self._img_w * self._scale) / 2.0
        self._off_y = (sh - self._img_h * self._scale) / 2.0
        self._user_zoomed = False

    def reset_view(self):
        self._fit()
        self.update()

    def zoom_at(self, widget_x, widget_y, factor):
        new_scale = max(self.MIN_SCALE, min(self.MAX_SCALE, self._scale * factor))
        factor = new_scale / self._scale
        if factor == 1.0:
            return
        self._off_x = widget_x - (widget_x - self._off_x) * factor
        self._off_y = widget_y - (widget_y - self._off_y) * factor
        self._scale = new_scale
        self._user_zoomed = True
        self.update()

    def wheelEvent(self, e):
        if self._pixmap is None:
            return
        step = e.angleDelta().y()
        if step == 0:
            return
        factor = 1.25 if step > 0 else 0.8
        pos = e.position() if hasattr(e, "position") else e.posF()
        self.zoom_at(pos.x(), pos.y(), factor)
        pct = self._scale / self._fit_scale * 100 if self._fit_scale else 100
        self.statusMessage.emit(f"缩放 {pct:.0f}%")

    def _to_img(self, pos):
        if self._scale == 0:
            return QPointF(0, 0)
        x = (pos.x() - self._off_x) / self._scale
        y = (pos.y() - self._off_y) / self._scale
        x = max(0.0, min(self._img_w, x))
        y = max(0.0, min(self._img_h, y))
        return QPointF(x, y)

    def _to_widget(self, x, y):
        return QPointF(x * self._scale + self._off_x, y * self._scale + self._off_y)

    def _inside_image(self, pos):
        return (self._off_x <= pos.x() <= self._off_x + self._img_w * self._scale and
                self._off_y <= pos.y() <= self._off_y + self._img_h * self._scale)

    def img_hit_radius(self, px=10):
        return px / max(self._scale, 1e-6)

    # ---- mouse dispatch ----
    def mousePressEvent(self, e):
        if self._pixmap is None:
            return
        if e.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = e.pos()
            self._pan_off0 = (self._off_x, self._off_y)
            self.setCursor(Qt.ClosedHandCursor)
            return
        if not self._inside_image(e.pos()):
            return
        ip = self._to_img(e.pos())
        if e.button() == Qt.RightButton:
            self.on_right_press(ip)
        elif e.button() == Qt.LeftButton:
            self.on_left_press(ip)

    def mouseMoveEvent(self, e):
        if self._pixmap is None:
            return
        if self._panning:
            d = e.pos() - self._pan_start
            self._off_x = self._pan_off0[0] + d.x()
            self._off_y = self._pan_off0[1] + d.y()
            self._user_zoomed = True
            self.update()
            return
        ip = self._to_img(e.pos())
        self.statusMessage.emit(f"x={ip.x():.1f}, y={ip.y():.1f}")
        self.on_move(ip)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self.unsetCursor()
            return
        if self._pixmap is None:
            return
        if e.button() == Qt.LeftButton:
            self.on_left_release(self._to_img(e.pos()))

    # ---- hooks (override in subclasses) ----
    def on_left_press(self, ip):
        pass

    def on_right_press(self, ip):
        pass

    def on_move(self, ip):
        pass

    def on_left_release(self, ip):
        pass

    def paint_overlay(self, painter):
        pass

    # ---- painting ----
    def paintEvent(self, e):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(40, 40, 40))
        if self._pixmap is None:
            painter.setPen(QColor(160, 160, 160))
            painter.setFont(QFont("Arial", 13))
            painter.drawText(self.rect(), Qt.AlignCenter, self._placeholder)
            return
        target = QRectF(self._off_x, self._off_y,
                        self._img_w * self._scale, self._img_h * self._scale)
        painter.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))
        painter.setRenderHint(QPainter.Antialiasing)
        self.paint_overlay(painter)

    def _draw_label(self, painter, pos, text, col):
        painter.setFont(QFont("Arial", 9, QFont.Bold))
        fm = painter.fontMetrics()
        w = fm.horizontalAdvance(text) + 8
        h = fm.height() + 2
        bg = QRectF(pos.x(), pos.y() - h, w, h)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(col))
        painter.drawRect(bg)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(bg, Qt.AlignCenter, text)


class Canvas(ImageView):
    """Point / box annotation surface for the single-media tool."""

    annotationsChanged = pyqtSignal()
    HANDLE = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 480)
        self.points = []
        self.boxes = []
        self.mode = MODE_POINT
        self.current_class = 0
        self.class_names = []
        self._drawing = False
        self._start = None
        self._cur = None
        self.selected = None
        self._placeholder = "打开图像或视频开始标注"

    # ---- data ----
    def set_frame(self, qimage, points, boxes):
        self.points = points
        self.boxes = boxes
        self.selected = None
        self._drawing = False
        self.set_image(qimage)

    def clear(self):
        self.points = []
        self.boxes = []
        self.set_image(None)

    def set_mode(self, mode):
        self.mode = mode
        self._drawing = False
        self.update()

    def set_classes(self, names):
        self.class_names = names

    def set_current_class(self, idx):
        self.current_class = idx

    def select(self, kind, index):
        self.selected = (kind, index)
        self.update()

    # ---- interaction ----
    def on_left_press(self, ip):
        if self.mode == MODE_POINT:
            self.points.append({"x": round(ip.x(), 2), "y": round(ip.y(), 2),
                                "class": self.current_class})
            self.annotationsChanged.emit()
            self.update()
        elif self.mode == MODE_BOX:
            self._drawing = True
            self._start = ip
            self._cur = ip
            self.update()

    def on_right_press(self, ip):
        self._delete_at(ip)

    def on_move(self, ip):
        if self._drawing:
            self._cur = ip
            self.update()

    def on_left_release(self, ip):
        if not self._drawing:
            return
        self._drawing = False
        x1, x2 = sorted((self._start.x(), self._cur.x()))
        y1, y2 = sorted((self._start.y(), self._cur.y()))
        if abs(x2 - x1) >= 3 and abs(y2 - y1) >= 3:
            self.boxes.append({"x1": round(x1, 2), "y1": round(y1, 2),
                               "x2": round(x2, 2), "y2": round(y2, 2),
                               "class": self.current_class})
            self.annotationsChanged.emit()
        self._start = self._cur = None
        self.update()

    def _delete_at(self, ip):
        r = self.img_hit_radius(self.HANDLE)
        for i, p in enumerate(self.points):
            if abs(p["x"] - ip.x()) <= r and abs(p["y"] - ip.y()) <= r:
                del self.points[i]
                self.annotationsChanged.emit()
                self.update()
                return
        for i, b in enumerate(self.boxes):
            if (b["x1"] - r <= ip.x() <= b["x2"] + r and
                    b["y1"] - r <= ip.y() <= b["y2"] + r):
                del self.boxes[i]
                self.annotationsChanged.emit()
                self.update()
                return

    def _cname(self, idx):
        if 0 <= idx < len(self.class_names):
            return self.class_names[idx]
        return str(idx)

    def paint_overlay(self, painter):
        for i, b in enumerate(self.boxes):
            col = class_color(b["class"])
            rect = QRectF(self._to_widget(b["x1"], b["y1"]),
                          self._to_widget(b["x2"], b["y2"]))
            sel = self.selected == ("box", i)
            painter.setPen(QPen(col, 3 if sel else 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)
            self._draw_label(painter, rect.topLeft(), self._cname(b["class"]), col)

        if self._drawing and self._start and self._cur:
            col = class_color(self.current_class)
            painter.setPen(QPen(col, 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(self._to_widget(self._start.x(), self._start.y()),
                                    self._to_widget(self._cur.x(), self._cur.y())))

        for i, p in enumerate(self.points):
            col = class_color(p["class"])
            c = self._to_widget(p["x"], p["y"])
            sel = self.selected == ("point", i)
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.setBrush(QBrush(col))
            rad = 7 if sel else 5
            painter.drawEllipse(c, rad, rad)
            self._draw_label(painter, QPointF(c.x() + 8, c.y() - 8),
                             self._cname(p["class"]), col)


class PairCanvas(ImageView):
    """Click surface for one side of the point-pair matching tool.

    It only displays markers it is handed and reports clicks in image
    coordinates; the owning window holds the pair data model.
    """

    clicked = pyqtSignal(float, float)
    rightClicked = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.markers = []  # list of dicts: {x, y, label, color_index, active}
        self._placeholder = "打开图像/视频（该侧）"

    def set_markers(self, markers):
        self.markers = markers
        self.update()

    def on_left_press(self, ip):
        self.clicked.emit(ip.x(), ip.y())

    def on_right_press(self, ip):
        self.rightClicked.emit(ip.x(), ip.y())

    def paint_overlay(self, painter):
        for m in self.markers:
            col = class_color(m["color_index"])
            c = self._to_widget(m["x"], m["y"])
            # crosshair
            painter.setPen(QPen(col, 1.5))
            painter.drawLine(QPointF(c.x() - 10, c.y()), QPointF(c.x() + 10, c.y()))
            painter.drawLine(QPointF(c.x(), c.y() - 10), QPointF(c.x(), c.y() + 10))
            # dot
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.setBrush(QBrush(col))
            rad = 7 if m.get("active") else 5
            painter.drawEllipse(c, rad, rad)
            if m.get("active"):
                painter.setPen(QPen(QColor(255, 255, 0), 2, Qt.DashLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(c, 12, 12)
            self._draw_label(painter, QPointF(c.x() + 10, c.y() - 10),
                             str(m["label"]), col)
