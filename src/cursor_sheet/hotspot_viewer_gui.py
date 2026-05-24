"""Tk GUI for inspecting cursor image pixel coordinates."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw

from cursor_sheet.parser import parse_cursor_file

MAX_CANVAS_IMAGE_SIZE = (760, 520)
CHECKER_SIZE = 8


@dataclass(frozen=True)
class HotspotPreviewFrame:
    image: Image.Image
    label: str
    hotspot: tuple[int, int] | None = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open a GUI for inspecting cursor hotspot coordinates.")
    add_arguments(parser)
    args = parser.parse_args(argv)
    return run_from_args(args, parser)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", nargs="?", type=Path, help="optional .cur/.ani/image file to open")
    parser.add_argument("--title", default="Cursor Hotspot Viewer", help="window title")


def run_from_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    del parser
    launch_hotspot_viewer(initial_file=args.input, title=args.title)
    return 0


def launch_hotspot_viewer(*, initial_file: Path | None = None, title: str = "Cursor Hotspot Viewer") -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox

    class HotspotViewer:
        def __init__(self) -> None:
            self.root = tk.Tk()
            self.root.title(title)
            self.root.minsize(900, 640)
            self.root.configure(bg="#eef2f6")
            self.frames: list[HotspotPreviewFrame] = []
            self.frame_index = 0
            self.current_path: Path | None = None
            self.image_offset = (0, 0)
            self.display_size = (1, 1)
            self.source_size = (1, 1)
            self.selected_hotspot: tuple[int, int] | None = None
            self.rendered_photo = None
            self.overlay_items: list[int] = []
            self.crosshair_items: list[int] = []

            self.status = tk.StringVar(value="打开一个 .cur/.ani 或图片文件")
            self.frame_value = tk.StringVar(value="1")
            self.info = tk.StringVar(value="")

            self._build()
            if initial_file is not None:
                self.load_file(initial_file)

        def _build(self) -> None:
            toolbar = tk.Frame(self.root, bg="#172033", padx=12, pady=10)
            toolbar.pack(fill="x")

            open_button = tk.Button(toolbar, text="打开文件", command=self.open_file, padx=12, pady=4)
            open_button.pack(side="left")

            tk.Label(toolbar, text="帧", bg="#172033", fg="#ffffff", padx=8).pack(side="left")
            self.frame_spin = tk.Spinbox(
                toolbar,
                from_=1,
                to=1,
                width=5,
                textvariable=self.frame_value,
                command=self._select_frame_from_spinbox,
                state="disabled",
            )
            self.frame_spin.pack(side="left")

            tk.Label(toolbar, textvariable=self.status, bg="#172033", fg="#ffffff", anchor="w", padx=12).pack(
                side="left", fill="x", expand=True
            )

            self.canvas = tk.Canvas(self.root, bg="#d9e0ea", highlightthickness=0)
            self.canvas.pack(fill="both", expand=True, padx=16, pady=(16, 8))
            self.canvas.bind("<Configure>", lambda _event: self.draw_current_frame())
            self.canvas.bind("<Motion>", self._on_motion)
            self.canvas.bind("<Leave>", lambda _event: self._set_overlay("移动到图像上查看坐标"))
            self.canvas.bind("<Button-1>", self._on_click)

            footer = tk.Label(
                self.root,
                textvariable=self.info,
                bg="#ffffff",
                fg="#172033",
                font=("Segoe UI", 10),
                anchor="w",
                padx=16,
                pady=8,
            )
            footer.pack(fill="x")

        def open_file(self) -> None:
            path = filedialog.askopenfilename(
                title="选择鼠标指针或图片文件",
                filetypes=(
                    ("Cursor and images", "*.cur *.ani *.png *.jpg *.jpeg *.bmp *.gif *.webp *.ico"),
                    ("Cursor files", "*.cur *.ani"),
                    ("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp *.ico"),
                    ("All files", "*.*"),
                ),
            )
            if path:
                self.load_file(Path(path))

        def load_file(self, path: Path) -> None:
            try:
                self.frames = load_hotspot_preview_frames(path)
            except Exception as exc:
                messagebox.showerror("无法打开文件", str(exc))
                return

            self.current_path = path
            self.frame_index = 0
            self.selected_hotspot = None
            self.status.set(str(path))
            self.frame_spin.configure(state="normal", from_=1, to=max(1, len(self.frames)))
            self.frame_value.set("1")
            if len(self.frames) <= 1:
                self.frame_spin.configure(state="disabled")
            self.draw_current_frame()

        def _select_frame_from_spinbox(self) -> None:
            try:
                value = int(self.frame_value.get())
            except ValueError:
                return
            self.frame_index = min(max(value - 1, 0), max(len(self.frames) - 1, 0))
            self.selected_hotspot = None
            self.draw_current_frame()

        def draw_current_frame(self) -> None:
            self.canvas.delete("all")
            self.overlay_items.clear()
            self.crosshair_items.clear()
            if not self.frames:
                self._set_overlay("打开文件后在这里查看坐标")
                self.info.set("")
                return

            frame = self.frames[self.frame_index]
            image = frame.image.convert("RGBA")
            self.source_size = image.size
            scale = choose_display_scale(image.size, _canvas_limit(self.canvas))
            self.display_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
            preview = make_checkerboard_preview(image, self.display_size)

            from PIL import ImageTk

            self.rendered_photo = ImageTk.PhotoImage(preview)
            canvas_width = max(self.canvas.winfo_width(), 1)
            canvas_height = max(self.canvas.winfo_height(), 1)
            left = max((canvas_width - self.display_size[0]) // 2, 0)
            top = max((canvas_height - self.display_size[1]) // 2, 0)
            self.image_offset = (left, top)
            self.canvas.create_image(left, top, anchor="nw", image=self.rendered_photo)

            hotspot = "无"
            if frame.hotspot is not None:
                hotspot = f"{frame.hotspot[0]},{frame.hotspot[1]}"
            self.info.set(
                f"{frame.label} | 原始尺寸 {image.width}x{image.height} | 文件热点 {hotspot} | 左键锁定当前坐标"
            )
            if frame.hotspot is not None:
                self._draw_crosshair(frame.hotspot, "#2563eb", "file-hotspot")
            self._set_overlay("移动到图像上查看坐标")

        def _on_motion(self, event) -> None:
            point = canvas_to_image_pixel(event.x, event.y, self.source_size, self.display_size, self.image_offset)
            if point is None:
                self._set_overlay("图像外")
                return
            x, y = point
            self._set_overlay(f"x={x}, y={y}   --hotspot {x},{y}")

        def _on_click(self, event) -> None:
            point = canvas_to_image_pixel(event.x, event.y, self.source_size, self.display_size, self.image_offset)
            if point is None:
                return
            self.selected_hotspot = point
            self._draw_crosshair(point, "#dc2626", "selected-hotspot")
            self._set_overlay(f"已锁定 x={point[0]}, y={point[1]}   --hotspot {point[0]},{point[1]}")

        def _draw_crosshair(self, point: tuple[int, int], color: str, tag: str) -> None:
            self.canvas.delete(tag)
            x = self.image_offset[0] + (point[0] + 0.5) * self.display_size[0] / self.source_size[0]
            y = self.image_offset[1] + (point[1] + 0.5) * self.display_size[1] / self.source_size[1]
            size = 8
            self.canvas.create_line(x - size, y, x + size, y, fill=color, width=2, tags=tag)
            self.canvas.create_line(x, y - size, x, y + size, fill=color, width=2, tags=tag)

        def _set_overlay(self, text: str) -> None:
            for item in self.overlay_items:
                self.canvas.delete(item)
            self.overlay_items.clear()
            canvas_width = max(self.canvas.winfo_width(), 1)
            padding = 10
            text_id = self.canvas.create_text(
                canvas_width - padding,
                padding,
                text=text,
                anchor="ne",
                fill="#ffffff",
                font=("Consolas", 12, "bold"),
            )
            bbox = self.canvas.bbox(text_id)
            if bbox is None:
                self.overlay_items.append(text_id)
                return
            rect_id = self.canvas.create_rectangle(
                bbox[0] - 8,
                bbox[1] - 5,
                bbox[2] + 8,
                bbox[3] + 5,
                fill="#111827",
                outline="#111827",
            )
            self.canvas.tag_raise(text_id, rect_id)
            self.overlay_items.extend([rect_id, text_id])

        def run(self) -> None:
            self.root.mainloop()

    HotspotViewer().run()


def load_hotspot_preview_frames(path: Path) -> list[HotspotPreviewFrame]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".cur", ".ani"}:
        document = parse_cursor_file(path)
        frames: list[HotspotPreviewFrame] = []
        for index, frame in enumerate(document.playback_frames):
            image = max(frame.images, key=lambda candidate: candidate.image.width * candidate.image.height)
            label = f"Frame {index + 1}/{len(document.playback_frames)}"
            if frame.delay:
                label += f" ({frame.delay:.3f}s)"
            frames.append(HotspotPreviewFrame(image=image.image.convert("RGBA"), label=label, hotspot=image.hotspot))
        return frames

    with Image.open(path) as image:
        return [HotspotPreviewFrame(image=image.convert("RGBA").copy(), label=path.name)]


def choose_display_scale(
    image_size: tuple[int, int],
    max_size: tuple[int, int] = MAX_CANVAS_IMAGE_SIZE,
    *,
    max_integer_scale: int = 12,
) -> float:
    width, height = image_size
    max_width, max_height = max_size
    if width <= 0 or height <= 0:
        raise ValueError("image size must be positive")
    if max_width <= 0 or max_height <= 0:
        return 1.0
    if width <= max_width and height <= max_height:
        return float(max(1, min(max_width // width, max_height // height, max_integer_scale)))
    return min(max_width / width, max_height / height)


def canvas_to_image_pixel(
    canvas_x: int,
    canvas_y: int,
    image_size: tuple[int, int],
    display_size: tuple[int, int],
    image_offset: tuple[int, int],
) -> tuple[int, int] | None:
    image_width, image_height = image_size
    display_width, display_height = display_size
    offset_x, offset_y = image_offset
    local_x = canvas_x - offset_x
    local_y = canvas_y - offset_y
    if local_x < 0 or local_y < 0 or local_x >= display_width or local_y >= display_height:
        return None
    pixel_x = min(image_width - 1, int(local_x * image_width / display_width))
    pixel_y = min(image_height - 1, int(local_y * image_height / display_height))
    return pixel_x, pixel_y


def make_checkerboard_preview(image: Image.Image, display_size: tuple[int, int]) -> Image.Image:
    preview = Image.new("RGBA", display_size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(preview)
    for y in range(0, display_size[1], CHECKER_SIZE):
        for x in range(0, display_size[0], CHECKER_SIZE):
            if (x // CHECKER_SIZE + y // CHECKER_SIZE) % 2:
                draw.rectangle((x, y, x + CHECKER_SIZE - 1, y + CHECKER_SIZE - 1), fill=(220, 226, 235, 255))
    resized = image.convert("RGBA").resize(display_size, Image.Resampling.NEAREST)
    preview.alpha_composite(resized)
    return preview


def _canvas_limit(canvas) -> tuple[int, int]:
    width = max(canvas.winfo_width() - 48, 1)
    height = max(canvas.winfo_height() - 48, 1)
    return width, height


if __name__ == "__main__":
    raise SystemExit(main())
