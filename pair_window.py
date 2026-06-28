"""Point-pair annotation tool: open two images/videos side by side and mark
corresponding point pairs (for feature matching / coordinate reconstruction)."""
import os
import json

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSlider, QStyle, QFileDialog, QMessageBox, QDockWidget, QListWidget,
    QListWidgetItem, QShortcut,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon, QKeySequence

from canvas import PairCanvas, class_color
from media import MediaSource

MEDIA_FILTER = ("Media (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp "
                "*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.m4v)")


class MediaPane(QWidget):
    """One side: open button + canvas + (for video) a frame control bar."""

    frameChanged = pyqtSignal()
    mediaOpened = pyqtSignal()

    def __init__(self, title):
        super().__init__()
        self.title = title
        self.media = None
        self.path = None
        self.frame_index = 0

        self.canvas = PairCanvas()
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._tick)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)

        top = QHBoxLayout()
        self.title_label = QLabel(f"<b>{title}</b>  (未打开)")
        self.title_label.setTextFormat(Qt.RichText)
        btn_open = QPushButton("打开…")
        btn_open.clicked.connect(self.open_dialog)
        top.addWidget(self.title_label, 1)
        top.addWidget(btn_open)
        lay.addLayout(top)

        lay.addWidget(self.canvas, 1)

        st = self.style()
        self.bar = QWidget()
        bl = QHBoxLayout(self.bar)
        bl.setContentsMargins(0, 0, 0, 0)
        self.btn_prev = QPushButton(); self.btn_prev.setIcon(st.standardIcon(QStyle.SP_MediaSkipBackward))
        self.btn_prev.clicked.connect(self.prev_frame)
        self.btn_play = QPushButton(); self.btn_play.setIcon(st.standardIcon(QStyle.SP_MediaPlay))
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_next = QPushButton(); self.btn_next.setIcon(st.standardIcon(QStyle.SP_MediaSkipForward))
        self.btn_next.clicked.connect(self.next_frame)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(self._on_slider)
        self.flabel = QLabel("0 / 0")
        for w in (self.btn_prev, self.btn_play, self.btn_next):
            bl.addWidget(w)
        bl.addWidget(self.slider, 1)
        bl.addWidget(self.flabel)
        lay.addWidget(self.bar)
        self.bar.setVisible(False)

    # ---- open / frames ----
    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, f"打开 {self.title}", "", MEDIA_FILTER)
        if path:
            self.open(path)

    def open(self, path):
        try:
            media = MediaSource(path)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开:\n{path}\n{e}")
            return False
        self.stop_play()
        if self.media:
            self.media.release()
        self.media = media
        self.path = path
        self.frame_index = 0
        self.bar.setVisible(media.kind == "video")
        self.slider.blockSignals(True)
        self.slider.setMaximum(max(0, media.frame_count - 1))
        self.slider.setValue(0)
        self.slider.blockSignals(False)
        self.title_label.setText(
            f"<b>{self.title}</b>  {os.path.basename(path)}  "
            f"({media.width}x{media.height})")
        self.show_frame(0)
        self.mediaOpened.emit()
        return True

    def show_frame(self, index):
        if not self.media:
            return
        index = max(0, min(self.media.frame_count - 1, index))
        self.frame_index = index
        self.canvas.set_image(self.media.get_frame(index))
        self.flabel.setText(f"{index + 1} / {self.media.frame_count}")
        self.slider.blockSignals(True)
        self.slider.setValue(index)
        self.slider.blockSignals(False)
        self.frameChanged.emit()

    def _on_slider(self, v):
        if self.media and v != self.frame_index:
            self.show_frame(v)

    def prev_frame(self):
        if self.media:
            self.show_frame(self.frame_index - 1)

    def next_frame(self):
        if self.media:
            self.show_frame(self.frame_index + 1)

    def _tick(self):
        if not self.media or self.frame_index >= self.media.frame_count - 1:
            self.stop_play()
            return
        self.show_frame(self.frame_index + 1)

    def toggle_play(self):
        if self.play_timer.isActive():
            self.stop_play()
        elif self.media and self.media.kind == "video":
            self.play_timer.start(max(15, int(1000 / (self.media.fps or 25))))
            self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))

    def stop_play(self):
        self.play_timer.stop()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))

    def current_frame(self):
        return self.frame_index

    def meta(self):
        if not self.media:
            return {}
        m = self.media
        return {"file": os.path.basename(self.path), "path": self.path,
                "kind": m.kind, "width": m.width, "height": m.height,
                "fps": m.fps, "frame_count": m.frame_count}


class PairWindow(QMainWindow):
    """Dual-view window for annotating corresponding point pairs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("点对标注 - 特征匹配 / 坐标重建")
        self.resize(1400, 850)

        # data model
        self.pairs = []     # {"id": int, "a": {frame,x,y}|None, "b": {...}|None}
        self.active = None  # index of pair currently being edited
        self.next_id = 1

        self.pane_a = MediaPane("左 A")
        self.pane_b = MediaPane("右 B")

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.pane_a)
        split.addWidget(self.pane_b)
        split.setSizes([700, 700])
        self.setCentralWidget(split)

        self._build_toolbar()
        self._build_dock()
        self._build_shortcuts()
        self.statusBar().showMessage(
            "在左图点击放点 → 在右图点击对应位置，即组成一个点对。"
            "← → 同步移动两个视频的帧；右键删除，中键拖动平移，滚轮缩放。")

        # wiring
        for side, pane in (("a", self.pane_a), ("b", self.pane_b)):
            pane.canvas.clicked.connect(
                lambda x, y, s=side, p=pane: self.on_click(s, p, x, y))
            pane.canvas.rightClicked.connect(
                lambda x, y, s=side, p=pane: self.on_right(s, p, x, y))
            pane.canvas.statusMessage.connect(self.statusBar().showMessage)
            pane.frameChanged.connect(self.refresh)

    # ---- UI ----
    def _build_toolbar(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        st = self.style()
        tb.addAction(st.standardIcon(QStyle.SP_DialogOpenButton), "导入点对").triggered.connect(self.import_pairs)
        tb.addAction(st.standardIcon(QStyle.SP_DialogSaveButton), "导出点对").triggered.connect(self.export_pairs)
        tb.addSeparator()
        tb.addAction("⤢ 适应窗口").triggered.connect(self.fit_both)
        tb.addSeparator()
        tb.addAction("删除选中").triggered.connect(self.delete_selected)
        tb.addAction("清空全部").triggered.connect(self.clear_all)

    def _build_dock(self):
        dock = QDockWidget("点对列表 Point Pairs", self)
        w = QWidget()
        lay = QVBoxLayout(w)
        self.count_label = QLabel("0 个点对")
        lay.addWidget(self.count_label)
        self.pair_list = QListWidget()
        self.pair_list.currentRowChanged.connect(self.on_select_pair)
        lay.addWidget(self.pair_list, 1)
        hint = QLabel("提示：选中某个点对后，再次在对应视图点击\n可重新放置该侧的点。")
        hint.setStyleSheet("color:#888;")
        lay.addWidget(hint)
        b_del = QPushButton("删除选中点对")
        b_del.clicked.connect(self.delete_selected)
        lay.addWidget(b_del)
        dock.setWidget(w)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    # ---- interaction ----
    def on_click(self, side, pane, x, y):
        if not pane.media:
            return
        pt = {"frame": pane.current_frame(), "x": round(x, 2), "y": round(y, 2)}
        ap = self.pairs[self.active] if self.active is not None else None
        if ap is None or (ap["a"] and ap["b"]):
            pair = {"id": self.next_id, "a": None, "b": None}
            self.next_id += 1
            pair[side] = pt
            self.pairs.append(pair)
            self.active = len(self.pairs) - 1
        else:
            ap[side] = pt
            if ap["a"] and ap["b"]:
                self.active = None  # completed -> next click starts a new pair
        self.refresh()

    def on_right(self, side, pane, x, y):
        if not pane.media:
            return
        r = pane.canvas.img_hit_radius(10)
        cf = pane.current_frame()
        for i, p in enumerate(self.pairs):
            pt = p[side]
            if pt and pt["frame"] == cf and abs(pt["x"] - x) <= r and abs(pt["y"] - y) <= r:
                self._remove_pair(i)
                return

    def _remove_pair(self, i):
        del self.pairs[i]
        if self.active == i:
            self.active = None
        elif self.active is not None and self.active > i:
            self.active -= 1
        self._renumber()
        self.refresh()

    def _renumber(self):
        """Keep ids consecutive 1..N so labels/colors have no gaps."""
        for i, p in enumerate(self.pairs):
            p["id"] = i + 1
        self.next_id = len(self.pairs) + 1

    def delete_selected(self):
        row = self.pair_list.currentRow()
        if not (0 <= row < len(self.pairs)) and self.active is not None:
            row = self.active
        if 0 <= row < len(self.pairs):
            self._remove_pair(row)
        else:
            self.statusBar().showMessage("请先在列表中选中一个点对")

    def clear_all(self):
        if not self.pairs:
            return
        if QMessageBox.question(self, "清空", "确定删除所有点对?") == QMessageBox.Yes:
            self.pairs = []
            self.active = None
            self.next_id = 1
            self.refresh()

    def on_select_pair(self, row):
        if 0 <= row < len(self.pairs):
            self.active = row
            self.refresh()

    def fit_both(self):
        self.pane_a.canvas.reset_view()
        self.pane_b.canvas.reset_view()

    # ---- shortcuts ----
    def _build_shortcuts(self):
        # Left / Right = step BOTH videos one frame together.
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=lambda: self.step_both(-1))
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=lambda: self.step_both(1))
        # Per-side stepping: A/D for left, J/L for right.
        QShortcut(QKeySequence(Qt.Key_A), self, activated=lambda: self.step_pane(self.pane_a, -1))
        QShortcut(QKeySequence(Qt.Key_D), self, activated=lambda: self.step_pane(self.pane_a, 1))
        QShortcut(QKeySequence(Qt.Key_J), self, activated=lambda: self.step_pane(self.pane_b, -1))
        QShortcut(QKeySequence(Qt.Key_L), self, activated=lambda: self.step_pane(self.pane_b, 1))

    def step_pane(self, pane, delta):
        if pane.media and pane.media.kind == "video":
            pane.show_frame(pane.current_frame() + delta)

    def step_both(self, delta):
        self.step_pane(self.pane_a, delta)
        self.step_pane(self.pane_b, delta)

    # ---- refresh views ----
    def _markers_for(self, side, pane):
        cf = pane.current_frame()
        out = []
        for i, p in enumerate(self.pairs):
            pt = p[side]
            if pt and pt["frame"] == cf:
                out.append({"x": pt["x"], "y": pt["y"], "label": p["id"],
                            "color_index": p["id"] - 1, "active": i == self.active})
        return out

    def refresh(self):
        self.pane_a.canvas.set_markers(self._markers_for("a", self.pane_a))
        self.pane_b.canvas.set_markers(self._markers_for("b", self.pane_b))
        self._refresh_list()

    def _refresh_list(self):
        self.pair_list.blockSignals(True)
        self.pair_list.clear()
        complete = 0
        for p in self.pairs:
            a, b = p["a"], p["b"]
            if a and b:
                complete += 1
            ta = f"A帧{a['frame']}({a['x']:.0f},{a['y']:.0f})" if a else "A:缺"
            tb = f"B帧{b['frame']}({b['x']:.0f},{b['y']:.0f})" if b else "B:缺"
            item = QListWidgetItem(f"#{p['id']}  {ta}  ↔  {tb}")
            pm = QPixmap(14, 14); pm.fill(class_color(p["id"] - 1))
            item.setIcon(QIcon(pm))
            self.pair_list.addItem(item)
        # restore selection so it survives the rebuild (otherwise currentRow
        # resets to -1 and "delete selected" has nothing to act on)
        if self.active is not None and 0 <= self.active < self.pair_list.count():
            self.pair_list.setCurrentRow(self.active)
        else:
            self.pair_list.clearSelection()
        self.pair_list.blockSignals(False)
        self.count_label.setText(
            f"{len(self.pairs)} 个点对（完整 {complete} 个）")

    # ---- import / export ----
    def export_pairs(self):
        if not (self.pane_a.media and self.pane_b.media):
            QMessageBox.information(self, "提示", "请先在左右两侧都打开图像/视频。")
            return
        complete = [p for p in self.pairs if p["a"] and p["b"]]
        if not complete:
            QMessageBox.information(self, "提示", "没有完整的点对（每对需左右各一个点）。")
            return
        base = os.path.splitext(self.pane_a.path)[0] + "_pairs.json"
        path, _ = QFileDialog.getSaveFileName(self, "导出点对", base, "JSON (*.json)")
        if not path:
            return
        out = {
            "type": "point_pairs",
            "media_a": self.pane_a.meta(),
            "media_b": self.pane_b.meta(),
            "pairs": [{"id": p["id"], "a": p["a"], "b": p["b"]} for p in complete],
            # convenience flat array: [xa, ya, xb, yb] (frame 0 / current usage)
            "matches": [[p["a"]["x"], p["a"]["y"], p["b"]["x"], p["b"]["y"]]
                        for p in complete],
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败:\n{e}")
            return
        self.statusBar().showMessage(f"已导出 {len(complete)} 个点对: {path}")
        QMessageBox.information(self, "完成", f"已导出 {len(complete)} 个点对到:\n{path}")

    def import_pairs(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入点对", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"读取失败:\n{e}")
            return
        self.pairs = []
        for p in data.get("pairs", []):
            self.pairs.append({"id": 0, "a": p.get("a"), "b": p.get("b")})
        self.active = None
        self._renumber()
        self.refresh()
        self.statusBar().showMessage(f"已导入 {len(self.pairs)} 个点对")

    def closeEvent(self, e):
        if self.pane_a.media:
            self.pane_a.media.release()
        if self.pane_b.media:
            self.pane_b.media.release()
        super().closeEvent(e)
