"""Image / Video annotation tool.

Two annotation modes:
  * Point  - click to drop a single point with the current class.
  * Box    - drag to draw a bounding box with the current class.

Works on a single image or a video (frame-by-frame, with playback).
Annotations are stored in original image-pixel coordinates and exported to a
JSON file that references the original media file.
"""
import os
import sys
import json

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QMessageBox, QInputDialog,
    QListWidget, QListWidgetItem, QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QDockWidget, QSlider, QComboBox, QColorDialog, QStyle, QAbstractItemView,
)
from PyQt5.QtWidgets import QShortcut
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QIcon, QPixmap, QKeySequence

from canvas import Canvas, MODE_POINT, MODE_BOX, class_color
from media import MediaSource, IMAGE_EXTS, VIDEO_EXTS
from pair_window import PairWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("图像/视频标注工具  Image & Video Annotator")
        self.resize(1280, 800)

        self.media = None
        self.media_path = None
        self.frame_index = 0
        # annotations per frame: {frame_index: {"points": [...], "boxes": [...]}}
        self.annotations = {}
        self.classes = ["object"]

        # folder / batch workflow
        self.file_list = []          # ordered list of media paths
        self.file_index = -1
        self.store = {}              # path -> {frame_index: {points, boxes}}
        self.meta = {}              # path -> {kind, width, height, fps, frame_count}
        self.auto_save = True        # auto-write JSON when leaving a file

        self.canvas = Canvas()
        self.canvas.set_classes(self.classes)
        self.canvas.annotationsChanged.connect(self.on_annotations_changed)
        self.canvas.statusMessage.connect(self.show_coord)
        self.setCentralWidget(self.canvas)

        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self.next_frame_play)

        self._build_toolbar()
        self._build_file_dock()
        self._build_class_dock()
        self._build_annotation_dock()
        self._build_statusbar()
        self._build_video_bar()
        self._build_shortcuts()

        self.pair_window = None
        self.update_ui_state()

    def _build_shortcuts(self):
        # Left / Right arrows = previous / next frame for video, else file nav.
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=self.key_prev)
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=self.key_next)
        # A / D = always previous / next file (useful for folders of videos).
        QShortcut(QKeySequence(Qt.Key_A), self, activated=self.prev_file)
        QShortcut(QKeySequence(Qt.Key_D), self, activated=self.next_file)
        # , / . = step video frame regardless of media kind.
        QShortcut(QKeySequence(Qt.Key_Comma), self, activated=self.prev_frame)
        QShortcut(QKeySequence(Qt.Key_Period), self, activated=self.next_frame)
        # Space = play / pause video.
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self.toggle_play)

    def key_prev(self):
        if self.media and self.media.kind == "video":
            self.prev_frame()
        else:
            self.prev_file()

    def key_next(self):
        if self.media and self.media.kind == "video":
            self.next_frame()
        else:
            self.next_file()

    # ------------------------------------------------------------------ UI
    def _build_toolbar(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        st = self.style()

        act_img = tb.addAction(st.standardIcon(QStyle.SP_FileIcon), "打开图像")
        act_img.triggered.connect(self.open_image)
        act_vid = tb.addAction(st.standardIcon(QStyle.SP_MediaPlay), "打开视频")
        act_vid.triggered.connect(self.open_video)
        act_dir = tb.addAction(st.standardIcon(QStyle.SP_DirOpenIcon), "打开文件夹")
        act_dir.triggered.connect(self.open_folder)
        tb.addSeparator()

        self.act_prev_file = tb.addAction(
            st.standardIcon(QStyle.SP_ArrowBack), "⟨ 上一张")
        self.act_prev_file.triggered.connect(self.prev_file)
        self.act_next_file = tb.addAction(
            st.standardIcon(QStyle.SP_ArrowForward), "下一张 ⟩")
        self.act_next_file.triggered.connect(self.next_file)
        tb.addSeparator()

        self.act_point = tb.addAction("● 点标注")
        self.act_point.setCheckable(True)
        self.act_point.setChecked(True)
        self.act_point.triggered.connect(lambda: self.set_mode(MODE_POINT))

        self.act_box = tb.addAction("▭ 框标注")
        self.act_box.setCheckable(True)
        self.act_box.triggered.connect(lambda: self.set_mode(MODE_BOX))
        tb.addSeparator()

        tb.addAction("➖ 缩小").triggered.connect(self.zoom_out)
        tb.addAction("➕ 放大").triggered.connect(self.zoom_in)
        tb.addAction("⤢ 适应窗口").triggered.connect(self.canvas.reset_view)
        tb.addSeparator()

        act_load = tb.addAction(st.standardIcon(QStyle.SP_DialogOpenButton), "导入标注")
        act_load.triggered.connect(self.import_annotations)
        act_save = tb.addAction(st.standardIcon(QStyle.SP_DialogSaveButton), "导出当前")
        act_save.triggered.connect(self.export_annotations)
        act_save_all = tb.addAction(
            st.standardIcon(QStyle.SP_DriveHDIcon), "导出全部")
        act_save_all.triggered.connect(self.export_all)

        self.act_auto = tb.addAction("自动保存")
        self.act_auto.setCheckable(True)
        self.act_auto.setChecked(True)
        self.act_auto.setToolTip("切换文件时自动把标注写入同目录 JSON")
        self.act_auto.toggled.connect(self._set_auto_save)
        tb.addSeparator()

        act_pair = tb.addAction("⇄ 点对标注")
        act_pair.setToolTip("打开双视图，标注两个图像/视频之间的对应点对")
        act_pair.triggered.connect(self.open_pair_tool)

    def _build_file_dock(self):
        dock = QDockWidget("文件列表 Files", self)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        w = QWidget()
        lay = QVBoxLayout(w)
        self.file_count_label = QLabel("未打开文件夹")
        lay.addWidget(self.file_count_label)
        self.file_list_widget = QListWidget()
        self.file_list_widget.currentRowChanged.connect(self.on_file_row_changed)
        lay.addWidget(self.file_list_widget, 1)
        row = QHBoxLayout()
        b_prev = QPushButton("⟨ 上一张")
        b_prev.clicked.connect(self.prev_file)
        b_next = QPushButton("下一张 ⟩")
        b_next.clicked.connect(self.next_file)
        row.addWidget(b_prev); row.addWidget(b_next)
        lay.addLayout(row)
        dock.setWidget(w)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def _build_class_dock(self):
        dock = QDockWidget("类别 Classes", self)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        w = QWidget()
        lay = QVBoxLayout(w)

        lay.addWidget(QLabel("当前类别 (用于新标注):"))
        self.class_combo = QComboBox()
        self.class_combo.currentIndexChanged.connect(self.on_class_selected)
        lay.addWidget(self.class_combo)

        self.class_list = QListWidget()
        lay.addWidget(self.class_list, 1)

        row = QHBoxLayout()
        b_add = QPushButton("添加")
        b_add.clicked.connect(self.add_class)
        b_ren = QPushButton("重命名")
        b_ren.clicked.connect(self.rename_class)
        b_del = QPushButton("删除")
        b_del.clicked.connect(self.delete_class)
        row.addWidget(b_add); row.addWidget(b_ren); row.addWidget(b_del)
        lay.addLayout(row)

        dock.setWidget(w)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.refresh_classes()

    def _build_annotation_dock(self):
        dock = QDockWidget("本帧标注 Annotations", self)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        w = QWidget()
        lay = QVBoxLayout(w)
        self.ann_list = QListWidget()
        self.ann_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ann_list.currentRowChanged.connect(self.on_ann_selected)
        lay.addWidget(self.ann_list, 1)
        b_del = QPushButton("删除选中标注")
        b_del.clicked.connect(self.delete_selected_annotation)
        lay.addWidget(b_del)
        b_clear = QPushButton("清空本帧")
        b_clear.clicked.connect(self.clear_frame_annotations)
        lay.addWidget(b_clear)
        dock.setWidget(w)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _build_video_bar(self):
        self.video_dock = QDockWidget("视频控制 Video", self)
        self.video_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        w = QWidget()
        lay = QHBoxLayout(w)
        st = self.style()

        self.btn_prev = QPushButton()
        self.btn_prev.setIcon(st.standardIcon(QStyle.SP_MediaSkipBackward))
        self.btn_prev.clicked.connect(self.prev_frame)
        self.btn_play = QPushButton()
        self.btn_play.setIcon(st.standardIcon(QStyle.SP_MediaPlay))
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_next = QPushButton()
        self.btn_next.setIcon(st.standardIcon(QStyle.SP_MediaSkipForward))
        self.btn_next.clicked.connect(self.next_frame)

        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.sliderMoved.connect(self.seek_frame)
        self.frame_slider.valueChanged.connect(self.seek_frame)

        self.frame_label = QLabel("0 / 0")

        for x in (self.btn_prev, self.btn_play, self.btn_next):
            lay.addWidget(x)
        lay.addWidget(self.frame_slider, 1)
        lay.addWidget(self.frame_label)
        self.video_dock.setWidget(w)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.video_dock)

    def _build_statusbar(self):
        self.coord_label = QLabel("")
        self.statusBar().addPermanentWidget(self.coord_label)
        self.statusBar().showMessage("就绪  Ready")

    # ------------------------------------------------------------- open/save
    def open_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开图像", "",
            "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp)")
        if path:
            self._set_file_list([path], 0)

    def open_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开视频", "",
            "Videos (*.mp4 *.avi *.mov *.mkv *.flv *.wmv *.m4v)")
        if path:
            self._set_file_list([path], 0)

    def open_folder(self):
        d = QFileDialog.getExistingDirectory(self, "打开文件夹")
        if not d:
            return
        exts = IMAGE_EXTS + VIDEO_EXTS
        try:
            names = sorted(os.listdir(d))
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法读取文件夹:\n{e}")
            return
        files = [os.path.join(d, n) for n in names
                 if os.path.splitext(n)[1].lower() in exts]
        if not files:
            QMessageBox.information(self, "提示", "该文件夹内没有支持的图像/视频文件。")
            return
        self._set_file_list(files, 0)
        self.statusBar().showMessage(f"已打开文件夹: {d}  ({len(files)} 个文件)")

    # ---- file list / navigation ----
    def _set_file_list(self, files, index):
        self.stop_play()
        self._save_current()
        self.file_list = files
        self.refresh_file_list()
        self.file_index = -1
        self.load_file_index(index)

    def load_file_index(self, index):
        if not (0 <= index < len(self.file_list)):
            return
        self.stop_play()
        if index != self.file_index:
            self._save_current()
        path = self.file_list[index]
        if not self._open_path(path):
            return
        self.file_index = index
        self.file_list_widget.blockSignals(True)
        self.file_list_widget.setCurrentRow(index)
        self.file_list_widget.blockSignals(False)
        self.update_nav_state()

    def _open_path(self, path):
        try:
            media = MediaSource(path)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开文件:\n{path}\n{e}")
            return False
        if self.media:
            self.media.release()
        self.media = media
        self.media_path = path
        self.annotations = self.store.setdefault(path, {})
        self.meta[path] = {"kind": media.kind, "width": media.width,
                           "height": media.height, "fps": media.fps,
                           "frame_count": media.frame_count}
        self.frame_index = 0
        self.frame_slider.blockSignals(True)
        self.frame_slider.setMaximum(max(0, media.frame_count - 1))
        self.frame_slider.setValue(0)
        self.frame_slider.blockSignals(False)
        self.show_frame(0)
        self.update_ui_state()
        pos = f"[{self.file_index_display()}] " if len(self.file_list) > 1 else ""
        self.setWindowTitle(f"{pos}{os.path.basename(path)} - 图像/视频标注工具")
        self.statusBar().showMessage(
            f"已加载 {media.kind}: {os.path.basename(path)}  "
            f"({media.width}x{media.height}, {media.frame_count} 帧)")
        return True

    def file_index_display(self):
        # human 1-based using the row that's about to be set
        idx = self.file_list.index(self.media_path) if self.media_path in self.file_list else 0
        return f"{idx + 1}/{len(self.file_list)}"

    def next_file(self):
        if self.file_index < len(self.file_list) - 1:
            self.load_file_index(self.file_index + 1)
        else:
            self.statusBar().showMessage("已是最后一个文件")

    def prev_file(self):
        if self.file_index > 0:
            self.load_file_index(self.file_index - 1)
        else:
            self.statusBar().showMessage("已是第一个文件")

    def on_file_row_changed(self, row):
        if row >= 0 and row != self.file_index:
            self.load_file_index(row)

    def _file_item_text(self, path):
        mark = "✓ " if self._has_annotations(self.store.get(path, {})) else "    "
        return mark + os.path.basename(path)

    def refresh_file_list(self):
        self.file_list_widget.blockSignals(True)
        self.file_list_widget.clear()
        for p in self.file_list:
            self.file_list_widget.addItem(QListWidgetItem(self._file_item_text(p)))
        self.file_list_widget.blockSignals(False)
        n = len(self.file_list)
        self.file_count_label.setText(f"{n} 个文件" if n else "未打开文件夹")

    def refresh_file_marks(self):
        for i, p in enumerate(self.file_list):
            item = self.file_list_widget.item(i)
            if item:
                item.setText(self._file_item_text(p))

    def update_nav_state(self):
        multi = len(self.file_list) > 1
        self.act_prev_file.setEnabled(multi and self.file_index > 0)
        self.act_next_file.setEnabled(multi and self.file_index < len(self.file_list) - 1)

    @staticmethod
    def _has_annotations(ann):
        return any(d.get("points") or d.get("boxes") for d in ann.values())

    def _save_current(self):
        """Persist current annotations into the store and (optionally) to disk."""
        if not self.media_path:
            return
        self.store[self.media_path] = self.annotations
        if self.auto_save and self.media_path in self.meta and \
                self._has_annotations(self.annotations):
            try:
                self._write_json_for(self.media_path)
            except Exception as e:
                self.statusBar().showMessage(f"自动保存失败: {e}")
        self.refresh_file_marks()

    def _set_auto_save(self, on):
        self.auto_save = on

    def open_pair_tool(self):
        if self.pair_window is None:
            self.pair_window = PairWindow(self)
        self.pair_window.show()
        self.pair_window.raise_()
        self.pair_window.activateWindow()

    def frame_data(self, index):
        return self.annotations.setdefault(index, {"points": [], "boxes": []})

    def show_frame(self, index):
        if not self.media:
            return
        self.frame_index = index
        qimg = self.media.get_frame(index)
        data = self.frame_data(index)
        self.canvas.set_frame(qimg, data["points"], data["boxes"])
        self.frame_label.setText(f"{index + 1} / {self.media.frame_count}")
        self.refresh_annotation_list()

    # --------------------------------------------------------------- classes
    def refresh_classes(self):
        self.class_combo.blockSignals(True)
        self.class_combo.clear()
        self.class_list.clear()
        for i, name in enumerate(self.classes):
            self.class_combo.addItem(self._color_icon(i), name)
            item = QListWidgetItem(self._color_icon(i), name)
            self.class_list.addItem(item)
        self.class_combo.blockSignals(False)
        self.canvas.set_classes(self.classes)
        self.canvas.set_current_class(self.class_combo.currentIndex())

    def _color_icon(self, idx):
        pm = QPixmap(16, 16)
        pm.fill(class_color(idx))
        return QIcon(pm)

    def on_class_selected(self, idx):
        if idx >= 0:
            self.canvas.set_current_class(idx)

    def add_class(self):
        name, ok = QInputDialog.getText(self, "添加类别", "类别名称:")
        if ok and name.strip():
            self.classes.append(name.strip())
            self.refresh_classes()
            self.class_combo.setCurrentIndex(len(self.classes) - 1)

    def rename_class(self):
        row = self.class_list.currentRow()
        if row < 0:
            return
        name, ok = QInputDialog.getText(self, "重命名类别", "新名称:",
                                        text=self.classes[row])
        if ok and name.strip():
            self.classes[row] = name.strip()
            self.refresh_classes()
            self.canvas.update()

    def delete_class(self):
        row = self.class_list.currentRow()
        if row < 0:
            return
        if len(self.classes) == 1:
            QMessageBox.information(self, "提示", "至少需要保留一个类别。")
            return
        used = self._class_in_use(row)
        if used:
            QMessageBox.warning(self, "无法删除",
                                "该类别已被标注使用，请先删除相关标注。")
            return
        del self.classes[row]
        # shift indices of annotations referencing classes after the removed one
        for data in self.annotations.values():
            for a in data["points"] + data["boxes"]:
                if a["class"] > row:
                    a["class"] -= 1
        self.refresh_classes()
        self.show_frame(self.frame_index)

    def _class_in_use(self, idx):
        for data in self.annotations.values():
            for a in data["points"] + data["boxes"]:
                if a["class"] == idx:
                    return True
        return False

    # ----------------------------------------------------------- annotations
    def on_annotations_changed(self):
        self.refresh_annotation_list()
        self.refresh_file_marks()

    def refresh_annotation_list(self):
        self.ann_list.blockSignals(True)
        self.ann_list.clear()
        data = self.frame_data(self.frame_index)
        for i, p in enumerate(data["points"]):
            cname = self.classes[p["class"]] if p["class"] < len(self.classes) else "?"
            self.ann_list.addItem(
                QListWidgetItem(self._color_icon(p["class"]),
                                f"点 #{i}  [{cname}]  ({p['x']:.0f}, {p['y']:.0f})"))
        for i, b in enumerate(data["boxes"]):
            cname = self.classes[b["class"]] if b["class"] < len(self.classes) else "?"
            self.ann_list.addItem(
                QListWidgetItem(self._color_icon(b["class"]),
                                f"框 #{i}  [{cname}]  "
                                f"({b['x1']:.0f},{b['y1']:.0f})-({b['x2']:.0f},{b['y2']:.0f})"))
        self.ann_list.blockSignals(False)

    def on_ann_selected(self, row):
        if row < 0:
            return
        data = self.frame_data(self.frame_index)
        np_ = len(data["points"])
        if row < np_:
            self.canvas.select("point", row)
        else:
            self.canvas.select("box", row - np_)

    def delete_selected_annotation(self):
        row = self.ann_list.currentRow()
        if row < 0:
            return
        data = self.frame_data(self.frame_index)
        np_ = len(data["points"])
        if row < np_:
            del data["points"][row]
        else:
            del data["boxes"][row - np_]
        self.show_frame(self.frame_index)

    def clear_frame_annotations(self):
        data = self.frame_data(self.frame_index)
        if not data["points"] and not data["boxes"]:
            return
        if QMessageBox.question(self, "清空", "确定清空本帧所有标注?") == QMessageBox.Yes:
            data["points"].clear()
            data["boxes"].clear()
            self.show_frame(self.frame_index)

    # ------------------------------------------------------------------ mode
    def set_mode(self, mode):
        self.canvas.set_mode(mode)
        self.act_point.setChecked(mode == MODE_POINT)
        self.act_box.setChecked(mode == MODE_BOX)

    def show_coord(self, text):
        self.coord_label.setText(text)

    def zoom_in(self):
        self.canvas.zoom_at(self.canvas.width() / 2, self.canvas.height() / 2, 1.25)

    def zoom_out(self):
        self.canvas.zoom_at(self.canvas.width() / 2, self.canvas.height() / 2, 0.8)

    # ----------------------------------------------------------------- video
    def update_ui_state(self):
        is_video = self.media is not None and self.media.kind == "video"
        self.video_dock.setVisible(is_video)
        self.update_nav_state()

    def prev_frame(self):
        if self.media and self.frame_index > 0:
            self.frame_slider.setValue(self.frame_index - 1)

    def next_frame(self):
        if self.media and self.frame_index < self.media.frame_count - 1:
            self.frame_slider.setValue(self.frame_index + 1)

    def next_frame_play(self):
        if not self.media:
            return
        if self.frame_index >= self.media.frame_count - 1:
            self.stop_play()
            return
        self.frame_slider.setValue(self.frame_index + 1)

    def seek_frame(self, value):
        if self.media and value != self.frame_index:
            self.show_frame(value)

    def toggle_play(self):
        if self.play_timer.isActive():
            self.stop_play()
        else:
            if self.media and self.media.kind == "video":
                interval = int(1000 / (self.media.fps or 25))
                self.play_timer.start(max(15, interval))
                self.btn_play.setIcon(
                    self.style().standardIcon(QStyle.SP_MediaPause))

    def stop_play(self):
        self.play_timer.stop()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))

    # ----------------------------------------------------------- import/export
    def _json_path_for(self, path):
        return os.path.splitext(path)[0] + "_annotations.json"

    def _build_export_dict(self, path):
        ann = self.store.get(path, {})
        m = self.meta.get(path, {})
        out = {
            "type": m.get("kind"),
            "file": os.path.basename(path),
            "file_path": path,
            "width": m.get("width"),
            "height": m.get("height"),
            "classes": self.classes,
        }
        if m.get("kind") == "image":
            d = ann.get(0, {"points": [], "boxes": []})
            out["points"] = d.get("points", [])
            out["boxes"] = d.get("boxes", [])
        else:
            out["fps"] = m.get("fps")
            out["frame_count"] = m.get("frame_count")
            frames = {}
            for idx, d in sorted(ann.items()):
                if d.get("points") or d.get("boxes"):
                    frames[str(idx)] = d
            out["frames"] = frames
        return out

    def _write_json_for(self, path):
        data = self._build_export_dict(path)
        jp = self._json_path_for(path)
        with open(jp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jp

    def export_annotations(self):
        if not self.media:
            QMessageBox.information(self, "提示", "请先打开图像或视频。")
            return
        self.store[self.media_path] = self.annotations
        default = self._json_path_for(self.media_path)
        path, _ = QFileDialog.getSaveFileName(self, "导出当前标注", default,
                                              "JSON (*.json)")
        if not path:
            return
        out = self._build_export_dict(self.media_path)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败:\n{e}")
            return
        self.statusBar().showMessage(f"已导出: {path}")
        QMessageBox.information(self, "完成", f"标注已导出到:\n{path}")

    def export_all(self):
        if self.media_path:
            self.store[self.media_path] = self.annotations
        targets = [p for p in self.file_list
                   if self._has_annotations(self.store.get(p, {}))]
        if not targets:
            QMessageBox.information(self, "提示", "没有可导出的标注。")
            return
        written, errs = 0, []
        for p in targets:
            try:
                self._write_json_for(p)
                written += 1
            except Exception as e:
                errs.append(f"{os.path.basename(p)}: {e}")
        self.refresh_file_marks()
        msg = f"已导出 {written} 个文件的标注 JSON\n(保存在各自原文件同目录)"
        if errs:
            msg += "\n\n失败:\n" + "\n".join(errs)
        self.statusBar().showMessage(f"批量导出完成: {written} 个文件")
        QMessageBox.information(self, "完成", msg)

    def import_annotations(self):
        if not self.media:
            QMessageBox.information(self, "提示", "请先打开对应的图像或视频。")
            return
        path, _ = QFileDialog.getOpenFileName(self, "导入标注", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"读取失败:\n{e}")
            return
        self.classes = data.get("classes", ["object"]) or ["object"]
        self.annotations = {}
        if data.get("type") == "image":
            self.annotations[0] = {"points": data.get("points", []),
                                   "boxes": data.get("boxes", [])}
        else:
            for k, v in data.get("frames", {}).items():
                self.annotations[int(k)] = {"points": v.get("points", []),
                                            "boxes": v.get("boxes", [])}
        self.store[self.media_path] = self.annotations
        self.refresh_classes()
        self.show_frame(self.frame_index)
        self.refresh_file_marks()
        self.statusBar().showMessage(f"已导入: {path}")

    def closeEvent(self, e):
        self._save_current()
        if self.media:
            self.media.release()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Image & Video Annotator")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
