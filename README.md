<a id="english"></a>
# Image & Video Annotator / 图像·视频标注工具

**English** | [中文](#chinese)

A simple image/video annotation tool supporting **point annotation** and **box annotation (with classes)**. Annotations are exported to JSON that maps back to the original media file. It also includes a **dual-view point-pair tool** for feature matching / coordinate reconstruction. Ships as source and can be packaged into a standalone Windows `.exe`.

## Features

- **Point annotation** — click to record a single point on an image/video frame.
- **Box annotation** — drag to draw a bounding box and assign a class.
- **Class management** — add / rename / delete classes; each class has its own color.
- **Images and videos**:
  - Image: single-frame annotation.
  - Video: per-frame annotation with play / pause / prev frame / next frame / seek slider; each frame stores its own annotations.
- **Batch folder annotation** — open a whole folder, annotate files one by one from the left file list, and move with the **Next / Prev** buttons (or **← →** arrow keys, also A / D). No need to reopen each file. Annotated files are marked with ✓.
  - With **Auto-save** on (default), switching files writes the annotation JSON next to each original; **Export All** does a one-shot batch export.
- **Point-pair annotation (dual view)** — toolbar **⇄ Point-Pair** opens a side-by-side view. Open two images/videos and mark **corresponding point pairs** for feature matching / coordinate reconstruction.
  - Click a point on the left, then the matching point on the right to form a pair (same color, same number). Each side zooms/pans independently and videos step frames independently.
  - Video point-pairs record their frame number and only show on that frame. Right-click to delete a pair; **Export Pairs** saves to JSON. Remaining pairs are always renumbered 1..N.
- **Export / Import** — annotations are saved as JSON (recording original filename and image size) and can be re-imported to keep editing.
- Right-click an annotation to delete it; you can also select and delete from the side list.

## Run from source

```bash
pip install -r requirements.txt
python main.py
```

## Usage

1. Toolbar **Open Image / Open Video / Open Folder**. After opening a folder, the left list shows all files; switch with the **⟨ Prev / Next ⟩** buttons or by clicking the list.
2. In the right **Classes** panel, add classes and pick the **current class**.
3. Choose **● Point** or **▭ Box** mode from the toolbar:
   - Point: left-click to place a point.
   - Box: left-drag to draw a box.
   - Right-click: delete the annotation near the cursor.
4. Zoom/pan: **mouse wheel** zooms centered on the cursor, **middle-mouse drag** pans; toolbar **➕ Zoom in / ➖ Zoom out / ⤢ Fit** also work. Zooming never changes the stored image-pixel coordinates.
5. Video: use the bottom control bar to step frames / play; each frame is annotated independently.
6. Toolbar **Export** saves JSON (by default next to the original, named `<file>_annotations.json`).

### Keyboard shortcuts

**Main window (single file / folder):**

| Key | Action |
|-----|--------|
| ← / → | Video: prev / next **frame**; Image: prev / next **file** |
| A / D | Prev / next file (always; handy for video folders) |
| , / . | Prev / next frame (always) |
| Space | Play / pause video |

**Point-pair window:**

| Key | Action |
|-----|--------|
| ← / → | Step **both** videos one frame **together** |
| A / D | Step left (A) video only |
| J / L | Step right (B) video only |

## Build a Windows EXE

Double-click `build.bat`, or run manually:

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name Annotator --collect-submodules cv2 main.py
```

The executable is produced at `dist\Annotator.exe`.

## Export format

**Image:**
```json
{
  "type": "image",
  "file": "xxx.png",
  "file_path": "D:/.../xxx.png",
  "width": 1920, "height": 1080,
  "classes": ["object", "person"],
  "points": [{"x": 10.0, "y": 20.0, "class": 0}],
  "boxes":  [{"x1": 5.0, "y1": 5.0, "x2": 100.0, "y2": 80.0, "class": 1}]
}
```

**Video** (keyed by frame number; only frames with annotations are saved):
```json
{
  "type": "video",
  "file": "xxx.mp4",
  "width": 1920, "height": 1080, "fps": 30.0, "frame_count": 900,
  "classes": ["object"],
  "frames": {
    "0":  {"points": [...], "boxes": [...]},
    "42": {"points": [...], "boxes": [...]}
  }
}
```

**Point pairs (dual-view export):**
```json
{
  "type": "point_pairs",
  "media_a": {"file": "a.png", "path": "...", "kind": "image", "width": 1920, "height": 1080, ...},
  "media_b": {"file": "b.mp4", "path": "...", "kind": "video", "frame_count": 600, "fps": 30.0, ...},
  "pairs": [
    {"id": 1, "a": {"frame": 0, "x": 30.0, "y": 40.0}, "b": {"frame": 12, "x": 55.0, "y": 66.0}}
  ],
  "matches": [[30.0, 40.0, 55.0, 66.0]]
}
```
> `matches` is a flat array `[xa, ya, xb, yb]`, ready to feed into `cv2.findHomography` / triangulation, etc.

> All coordinates are in original image pixels and map one-to-one to the original image/video frame, independent of on-screen zoom.

## Project structure

| File | Description |
|------|-------------|
| `main.py`   | Main app & UI (single-file / folder annotation) |
| `canvas.py` | Canvas widgets: `ImageView` base + `Canvas` (point/box) + `PairCanvas` (point pairs) |
| `pair_window.py` | Dual-view point-pair window |
| `media.py`  | Image/video loading abstraction |
| `requirements.txt` | Dependencies |
| `build.bat` | One-click packaging script |

---

<a id="chinese"></a>
# 中文说明

[English](#english) | **中文**

一个简单的图像/视频标注软件，支持**单点标注**和**画框标注（带类别）**，可导出标注信息并与原文件对应；并内置**双视图点对标注**工具，用于特征匹配 / 坐标重建。提供源码运行，也可打包为独立的 Windows `.exe`。

## 功能

- **点标注**：在图像/视频上点击，记录单点坐标信息。
- **框标注**：拖拽画出 bounding box，并标明类别。
- **类别管理**：添加 / 重命名 / 删除类别，每个类别有独立颜色。
- **图像与视频**：
  - 图像：单张标注。
  - 视频：逐帧标注，支持播放 / 暂停 / 上一帧 / 下一帧 / 进度条跳转，每帧独立保存标注。
- **文件夹批量标注**：一次打开整个文件夹，左侧文件列表依次标注，点「下一张 / 上一张」（或 **方向键 ← →**，也可用 A / D）即可切换，无需反复打开。已标注的文件用 ✓ 标记。
  - 「自动保存」开启时（默认），切换文件会自动把标注写入同目录 JSON；也可用「导出全部」一次性批量导出。
- **点对标注（双视图）**：工具栏「⇄ 点对标注」打开左右双视图，可分别打开两个图像/视频，标注它们之间的**对应点对**，用于特征匹配 / 坐标重建。
  - 在左图点一下放点，再到右图点击对应位置即组成一个点对（同色、同编号）。两侧均可独立缩放/平移、视频独立逐帧。
  - 视频点对会记录所在帧号，仅在对应帧显示。右键删除点对，「导出点对」保存为 JSON。删除后编号始终重排为从 1 开始连续。
- **导出 / 导入**：标注以 JSON 保存，记录原文件名与图像尺寸，可重新导入继续编辑。
- 右键点击标注可删除；右侧列表也可选中删除。

## 运行（源码）

```bash
pip install -r requirements.txt
python main.py
```

## 操作说明

1. 工具栏「打开图像」「打开视频」或「打开文件夹」加载文件。打开文件夹后，左侧列表显示所有文件，用工具栏「⟨ 上一张 / 下一张 ⟩」或列表点击切换。
2. 右侧「类别」面板添加类别，并选择「当前类别」。
3. 工具栏选择「● 点标注」或「▭ 框标注」模式：
   - 点标注：左键单击放置点。
   - 框标注：左键拖拽画框。
   - 右键：删除鼠标附近的标注。
4. 缩放查看：**鼠标滚轮**以光标为中心放大/缩小，**按住鼠标中键拖动**平移；工具栏「➕放大 / ➖缩小 / ⤢适应窗口」也可操作。缩放不影响标注的原图坐标。
5. 视频：底部控制条切换帧 / 播放，每帧标注独立。
6. 工具栏「导出标注」保存为 JSON（默认与原文件同目录、同名 + `_annotations.json`）。

### 快捷键

**主窗口（单文件 / 文件夹标注）：**

| 按键 | 作用 |
|------|------|
| ← / → | 视频时：上一帧 / 下一帧；图像时：上一张 / 下一张文件 |
| A / D | 上一张 / 下一张文件（任何时候，适合视频文件夹）|
| , / . | 上一帧 / 下一帧（任何时候）|
| 空格 | 播放 / 暂停视频 |

**点对标注窗口：**

| 按键 | 作用 |
|------|------|
| ← / → | **同步**移动左右两个视频各一帧 |
| A / D | 仅左侧(A)视频 上一帧 / 下一帧 |
| J / L | 仅右侧(B)视频 上一帧 / 下一帧 |

## 打包为 EXE

双击运行 `build.bat`，或手动执行：

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name Annotator --collect-submodules cv2 main.py
```

生成的可执行文件位于 `dist\Annotator.exe`。

## 导出格式

**图像：**
```json
{
  "type": "image",
  "file": "xxx.png",
  "file_path": "D:/.../xxx.png",
  "width": 1920, "height": 1080,
  "classes": ["object", "person"],
  "points": [{"x": 10.0, "y": 20.0, "class": 0}],
  "boxes":  [{"x1": 5.0, "y1": 5.0, "x2": 100.0, "y2": 80.0, "class": 1}]
}
```

**视频：**（按帧号组织，仅保存有标注的帧）
```json
{
  "type": "video",
  "file": "xxx.mp4",
  "width": 1920, "height": 1080, "fps": 30.0, "frame_count": 900,
  "classes": ["object"],
  "frames": {
    "0":  {"points": [...], "boxes": [...]},
    "42": {"points": [...], "boxes": [...]}
  }
}
```

**点对（双视图导出）：**
```json
{
  "type": "point_pairs",
  "media_a": {"file": "a.png", "path": "...", "kind": "image", "width": 1920, "height": 1080, ...},
  "media_b": {"file": "b.mp4", "path": "...", "kind": "video", "frame_count": 600, "fps": 30.0, ...},
  "pairs": [
    {"id": 1, "a": {"frame": 0, "x": 30.0, "y": 40.0}, "b": {"frame": 12, "x": 55.0, "y": 66.0}}
  ],
  "matches": [[30.0, 40.0, 55.0, 66.0]]
}
```
> `matches` 为扁平数组 `[xa, ya, xb, yb]`，方便直接喂给 cv2.findHomography / 三角化等。

> 坐标均为原始图像像素坐标，与原图/视频帧一一对应，不受窗口缩放影响。

## 文件结构

| 文件 | 说明 |
|------|------|
| `main.py`   | 主程序与界面（单文件/文件夹标注）|
| `canvas.py` | 画布控件：`ImageView` 基类 + `Canvas`（点/框）+ `PairCanvas`（点对）|
| `pair_window.py` | 点对标注双视图窗口 |
| `media.py`  | 图像/视频加载抽象 |
| `requirements.txt` | 依赖 |
| `build.bat` | 一键打包脚本 |
