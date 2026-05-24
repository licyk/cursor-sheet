"""GIF export helpers for parsed cursor frames."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PIL import Image, ImageColor

from cursor_sheet.models import CursorFrame, CursorImage


def write_gif(
    frames: Sequence[CursorFrame],
    output_file: str | Path,
    *,
    scale: float = 1.0,
    delay_ms: int = 100,
    loop: int = 0,
    background: str = "transparent",
) -> Path:
    """Write cursor frames as a GIF file."""

    images = render_gif_frames(frames, scale=scale, background=background)
    durations = [_frame_duration_ms(frame, delay_ms) for frame in frames]
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        path,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=loop,
        disposal=2,
    )
    return path


def render_gif_frames(
    frames: Sequence[CursorFrame],
    *,
    scale: float = 1.0,
    background: str = "transparent",
) -> list[Image.Image]:
    """Render cursor frames onto same-sized RGBA canvases suitable for GIF saving."""

    if not frames:
        raise ValueError("at least one frame is required")
    if scale <= 0:
        raise ValueError("scale must be greater than zero")

    prepared = [_prepare_image(_largest_image(frame), scale) for frame in frames]
    canvas_width = max(image.width for image in prepared)
    canvas_height = max(image.height for image in prepared)
    background_color = _parse_background(background)

    rendered: list[Image.Image] = []
    for image in prepared:
        canvas = Image.new("RGBA", (canvas_width, canvas_height), background_color)
        paste_x = (canvas_width - image.width) // 2
        paste_y = (canvas_height - image.height) // 2
        canvas.alpha_composite(image, (paste_x, paste_y))
        rendered.append(canvas)
    return rendered


def _largest_image(frame: CursorFrame) -> CursorImage:
    if not frame.images:
        raise ValueError("cursor frame does not contain images")
    return max(frame.images, key=lambda item: (item.image.width * item.image.height, item.nominal_size))


def _prepare_image(cursor_image: CursorImage, scale: float) -> Image.Image:
    image = cursor_image.image.convert("RGBA")
    if scale == 1:
        return image.copy()
    new_size = (
        max(1, int(round(image.width * scale))),
        max(1, int(round(image.height * scale))),
    )
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _frame_duration_ms(frame: CursorFrame, fallback_delay_ms: int) -> int:
    if fallback_delay_ms <= 0:
        raise ValueError("delay_ms must be greater than zero")
    if frame.delay > 0:
        return max(1, int(round(frame.delay * 1000)))
    return fallback_delay_ms


def _parse_background(background: str) -> tuple[int, int, int, int]:
    if background.lower() == "transparent":
        return (0, 0, 0, 0)
    return ImageColor.getcolor(background, "RGBA")
