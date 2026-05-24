from __future__ import annotations

from PIL import Image
import pytest

from cursor_sheet.models import CursorFrame, CursorImage
from cursor_sheet.sheet import make_contact_sheet


def frame(width: int, height: int, color: tuple[int, int, int, int]) -> CursorFrame:
    image = Image.new("RGBA", (width, height), color)
    return CursorFrame(images=(CursorImage(image=image, hotspot=(0, 0), nominal_size=max(width, height)),))


def test_auto_columns_and_separator_pixels() -> None:
    frames = [frame(4, 3, (255, 0, 0, 255)) for _ in range(6)]

    sheet = make_contact_sheet(frames, line_width=2, line_color="#000000")

    assert sheet.size == (16, 8)
    assert sheet.getpixel((4, 0)) == (0, 0, 0, 255)
    assert sheet.getpixel((5, 7)) == (0, 0, 0, 255)
    assert sheet.getpixel((0, 3)) == (0, 0, 0, 255)
    assert sheet.getpixel((15, 4)) == (0, 0, 0, 255)


def test_custom_separator_and_background_colors() -> None:
    frames = [frame(2, 2, (255, 0, 0, 128)), frame(2, 2, (0, 0, 255, 128))]

    sheet = make_contact_sheet(frames, columns=2, line_color="#00ff00", background="#ffffff")

    assert sheet.getpixel((2, 0)) == (0, 255, 0, 255)
    assert sheet.getpixel((0, 0)) == (255, 127, 127, 255)


def test_transparent_background_and_centering_mixed_sizes() -> None:
    frames = [
        frame(2, 2, (255, 0, 0, 255)),
        frame(4, 2, (0, 255, 0, 255)),
        frame(2, 4, (0, 0, 255, 255)),
        frame(4, 4, (255, 255, 0, 255)),
    ]

    sheet = make_contact_sheet(frames, columns=2, line_width=1, background="transparent")

    assert sheet.size == (9, 9)
    assert sheet.getpixel((0, 0)) == (0, 0, 0, 0)
    assert sheet.getpixel((1, 1)) == (255, 0, 0, 255)
    assert sheet.getpixel((4, 0)) == (0, 0, 0, 255)
    assert sheet.getpixel((0, 4)) == (0, 0, 0, 255)


def test_scale_affects_cell_size() -> None:
    sheet = make_contact_sheet([frame(4, 4, (255, 0, 0, 255))], scale=2)

    assert sheet.size == (8, 8)


@pytest.mark.parametrize(
    ("frame_count", "expected_size"),
    [
        (2, (9, 3)),
        (4, (9, 7)),
        (6, (14, 7)),
        (9, (14, 11)),
    ],
)
def test_auto_columns_for_common_frame_counts(frame_count: int, expected_size: tuple[int, int]) -> None:
    frames = [frame(4, 3, (255, 0, 0, 255)) for _ in range(frame_count)]

    sheet = make_contact_sheet(frames)

    assert sheet.size == expected_size
