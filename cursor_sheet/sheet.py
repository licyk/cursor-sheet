"""Contact sheet rendering for cursor frames."""

from __future__ import annotations

from math import ceil, sqrt
from typing import Sequence

from PIL import Image, ImageColor, ImageDraw

from cursor_sheet.models import CursorFrame, CursorImage


def make_contact_sheet(
    frames: Sequence[CursorFrame],
    *,
    columns: int | None = None,
    scale: float = 1.0,
    line_width: int = 1,
    line_color: str = "#000000",
    background: str = "transparent",
) -> Image.Image:
    """Render cursor frames into a left-to-right contact sheet."""

    if not frames:
        raise ValueError("at least one frame is required")
    if columns is not None and columns <= 0:
        raise ValueError("columns must be greater than zero")
    if scale <= 0:
        raise ValueError("scale must be greater than zero")
    if line_width < 0:
        raise ValueError("line width must not be negative")

    selected_images = [_prepare_image(_largest_image(frame), scale) for frame in frames]
    column_count = min(len(selected_images), ceil(sqrt(len(selected_images)))) if columns is None else columns
    row_count = ceil(len(selected_images) / column_count)
    cell_width = max(image.width for image in selected_images)
    cell_height = max(image.height for image in selected_images)

    sheet_width = column_count * cell_width + max(0, column_count - 1) * line_width
    sheet_height = row_count * cell_height + max(0, row_count - 1) * line_width
    sheet = Image.new("RGBA", (sheet_width, sheet_height), _parse_background(background))

    for index, image in enumerate(selected_images):
        row = index // column_count
        column = index % column_count
        cell_x = column * (cell_width + line_width)
        cell_y = row * (cell_height + line_width)
        paste_x = cell_x + (cell_width - image.width) // 2
        paste_y = cell_y + (cell_height - image.height) // 2
        sheet.alpha_composite(image, (paste_x, paste_y))

    _draw_separators(sheet, column_count, row_count, cell_width, cell_height, line_width, line_color)
    return sheet


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


def _parse_background(background: str) -> tuple[int, int, int, int]:
    if background.lower() == "transparent":
        return (0, 0, 0, 0)
    return ImageColor.getcolor(background, "RGBA")


def _draw_separators(
    image: Image.Image,
    columns: int,
    rows: int,
    cell_width: int,
    cell_height: int,
    line_width: int,
    line_color: str,
) -> None:
    if line_width == 0:
        return

    color = ImageColor.getcolor(line_color, "RGBA")
    draw = ImageDraw.Draw(image)
    for column in range(1, columns):
        x = column * cell_width + (column - 1) * line_width
        draw.rectangle((x, 0, x + line_width - 1, image.height - 1), fill=color)
    for row in range(1, rows):
        y = row * cell_height + (row - 1) * line_width
        draw.rectangle((0, y, image.width - 1, y + line_width - 1), fill=color)
