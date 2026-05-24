from __future__ import annotations

from pathlib import Path

from PIL import Image

from cursor_sheet.frame_images import (
    align_frame_images,
    load_frame_images,
    pixelate_frame_images,
    remove_solid_background,
    split_contact_sheet,
)


def test_split_contact_sheet_uses_row_major_order_and_removes_blank_tail() -> None:
    sheet = Image.new("RGBA", (14, 9), (255, 255, 255, 255))
    for x in (4, 9):
        for y in range(sheet.height):
            sheet.putpixel((x, y), (0, 0, 0, 255))
    for y in (4,):
        for x in range(sheet.width):
            sheet.putpixel((x, y), (0, 0, 0, 255))
    colors = [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
        (255, 255, 0, 255),
    ]
    positions = [(1, 1), (6, 1), (11, 1), (1, 6)]
    for position, color in zip(positions, colors):
        sheet.putpixel(position, color)

    frames = split_contact_sheet(sheet)

    assert len(frames) == 4
    assert [frame.getpixel((1, 1)) for frame in frames] == colors


def test_split_contact_sheet_matches_custom_separator_color_with_tolerance() -> None:
    sheet = Image.new("RGBA", (9, 4), (255, 255, 255, 255))
    for y in range(sheet.height):
        sheet.putpixel((4, y), (3, 1, 252, 255))
    sheet.putpixel((1, 1), (255, 0, 0, 255))
    sheet.putpixel((6, 1), (0, 255, 0, 255))

    frames = split_contact_sheet(sheet, separator_color="#0000ff", separator_tolerance=5)

    assert len(frames) == 2
    assert frames[0].getpixel((1, 1)) == (255, 0, 0, 255)
    assert frames[1].getpixel((1, 1)) == (0, 255, 0, 255)


def test_split_contact_sheet_default_tolerance_matches_near_black_separator() -> None:
    sheet = Image.new("RGBA", (9, 4), (255, 255, 255, 255))
    for y in range(sheet.height):
        sheet.putpixel((4, y), (0, 18, 0, 255))
    sheet.putpixel((1, 1), (255, 0, 0, 255))
    sheet.putpixel((6, 1), (0, 255, 0, 255))

    frames = split_contact_sheet(sheet)

    assert len(frames) == 2
    assert frames[0].getpixel((1, 1)) == (255, 0, 0, 255)
    assert frames[1].getpixel((1, 1)) == (0, 255, 0, 255)


def test_split_contact_sheet_ignores_tiny_sections_between_separator_runs() -> None:
    sheet = Image.new("RGBA", (10, 3), (255, 255, 255, 255))
    for x in (0, 4, 6):
        for y in range(sheet.height):
            sheet.putpixel((x, y), (0, 0, 0, 255))
    for y in range(sheet.height):
        sheet.putpixel((5, y), (255, 0, 0, 255))
    sheet.putpixel((2, 1), (0, 255, 0, 255))
    sheet.putpixel((8, 1), (0, 0, 255, 255))

    frames = split_contact_sheet(sheet)

    assert [frame.size for frame in frames] == [(3, 3), (3, 3)]
    assert frames[0].getpixel((1, 1)) == (0, 255, 0, 255)
    assert frames[1].getpixel((1, 1)) == (0, 0, 255, 255)


def test_remove_solid_background_keeps_subject_and_transparents_border() -> None:
    image = Image.new("RGBA", (4, 4), (255, 255, 255, 255))
    image.putpixel((1, 1), (255, 0, 0, 255))

    result = remove_solid_background(image)

    assert result.getpixel((0, 0)) == (0, 0, 0, 0)
    assert result.getpixel((1, 1)) == (255, 0, 0, 255)


def test_remove_solid_background_keeps_all_solid_images() -> None:
    image = Image.new("RGBA", (4, 4), (255, 0, 0, 255))

    result = remove_solid_background(image)

    assert result.getpixel((0, 0)) == (255, 0, 0, 255)


def test_remove_solid_background_does_not_remove_subject_with_transparent_border() -> None:
    image = Image.new("RGBA", (5, 5), (0, 0, 0, 0))
    image.putpixel((2, 2), (255, 0, 0, 255))

    result = remove_solid_background(image)

    assert result.getpixel((2, 2)) == (255, 0, 0, 255)


def test_remove_solid_background_uses_dominant_edge_color_when_corners_are_noisy() -> None:
    image = Image.new("RGBA", (10, 10), (0, 255, 0, 255))
    for point in [(0, 0), (9, 0), (0, 9), (9, 9)]:
        image.putpixel(point, (0, 20, 0, 255))
    for x in range(3, 7):
        for y in range(3, 7):
            image.putpixel((x, y), (255, 0, 0, 255))

    result = remove_solid_background(image)

    assert result.getpixel((1, 0)) == (0, 0, 0, 0)
    assert result.getpixel((0, 0)) == (0, 0, 0, 0)
    assert result.getpixel((4, 4)) == (255, 0, 0, 255)


def test_remove_solid_background_uses_high_share_dominant_color_without_clean_edges() -> None:
    image = Image.new("RGBA", (10, 10), (0, 255, 0, 255))
    for x in range(10):
        image.putpixel((x, 0), (0, 20, 0, 255))
        image.putpixel((x, 9), (0, 20, 0, 255))
    for y in range(10):
        image.putpixel((0, y), (0, 20, 0, 255))
        image.putpixel((9, y), (0, 20, 0, 255))
    for x in range(3, 7):
        for y in range(3, 7):
            image.putpixel((x, y), (255, 0, 0, 255))

    result = remove_solid_background(image)

    assert result.getpixel((2, 2)) == (0, 0, 0, 0)
    assert result.getpixel((0, 0)) == (0, 0, 0, 0)
    assert result.getpixel((4, 4)) == (255, 0, 0, 255)


def test_remove_solid_background_cleans_dark_green_fringe_but_keeps_black_subject() -> None:
    image = Image.new("RGBA", (8, 8), (0, 255, 0, 255))
    for x in range(8):
        image.putpixel((x, 1), (0, 24, 0, 255))
    for y in range(3, 6):
        image.putpixel((3, y), (0, 0, 0, 255))
        image.putpixel((4, y), (255, 255, 255, 255))

    result = remove_solid_background(image)

    assert result.getpixel((1, 1)) == (0, 0, 0, 0)
    assert result.getpixel((3, 4)) == (0, 0, 0, 255)
    assert result.getpixel((4, 4)) == (255, 255, 255, 255)


def test_remove_solid_background_cleans_muted_green_matte() -> None:
    image = Image.new("RGBA", (5, 5), (0, 255, 0, 255))
    image.putpixel((2, 2), (126, 147, 98, 255))
    image.putpixel((3, 2), (255, 255, 255, 255))

    result = remove_solid_background(image)

    assert result.getpixel((2, 2)) == (0, 0, 0, 0)
    assert result.getpixel((3, 2)) == (255, 255, 255, 255)


def test_remove_solid_background_detects_clustered_generated_green() -> None:
    image = Image.new("RGBA", (10, 10), (3, 247, 5, 255))
    variants = [(2, 247, 4, 255), (3, 248, 4, 255), (4, 246, 6, 255), (6, 236, 9, 255)]
    for y in range(10):
        for x in range(10):
            image.putpixel((x, y), variants[(x + y) % len(variants)])
    image.putpixel((0, 0), (3, 186, 6, 255))
    for x in range(3, 7):
        for y in range(3, 7):
            image.putpixel((x, y), (255, 0, 0, 255))

    result = remove_solid_background(image)

    assert result.getpixel((0, 0))[3] == 0
    assert result.getpixel((2, 2))[3] == 0
    assert result.getpixel((4, 4)) == (255, 0, 0, 255)


def test_remove_solid_background_matches_explicit_color_with_tolerance() -> None:
    image = Image.new("RGBA", (4, 4), (0, 251, 3, 255))
    image.putpixel((1, 1), (255, 0, 0, 255))

    result = remove_solid_background(image, background_color="#00ff00", tolerance=6)

    assert result.getpixel((0, 0)) == (0, 0, 0, 0)
    assert result.getpixel((1, 1)) == (255, 0, 0, 255)


def test_align_frame_images_matches_transparent_frame_anchor_points() -> None:
    first = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    second = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    for x in range(1, 3):
        for y in range(1, 3):
            first.putpixel((x, y), (255, 0, 0, 255))
    for x in range(4, 6):
        for y in range(3, 5):
            second.putpixel((x, y), (255, 0, 0, 255))

    aligned = align_frame_images([first, second], anchor="center")

    centers = [_bbox_center(frame.getchannel("A").getbbox()) for frame in aligned]
    assert [frame.size for frame in aligned] == [(8, 8), (8, 8)]
    assert centers == [(4.0, 4.0), (4.0, 4.0)]


def test_align_frame_images_ignores_green_edge_background_when_aligning() -> None:
    first = _green_frame_with_subject((1, 2))
    second = _green_frame_with_subject((4, 4))

    aligned = align_frame_images([first, second])

    bboxes = [frame.getchannel("A").getbbox() for frame in aligned]
    assert [_bbox_bottom_center(bbox) for bbox in bboxes] == [(4.0, 8), (4.0, 8)]
    assert aligned[0].getpixel((0, 0))[3] == 0
    assert aligned[1].getpixel((0, 0))[3] == 0


def test_pixelate_frame_images_resizes_with_nearest_neighbor_and_preserves_alpha() -> None:
    image = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    colors = {
        (0, 0): (255, 0, 0, 255),
        (2, 0): (0, 255, 0, 255),
        (0, 2): (0, 0, 255, 255),
        (2, 2): (255, 255, 0, 128),
    }
    for left, top in colors:
        for x in range(left, left + 2):
            for y in range(top, top + 2):
                image.putpixel((x, y), colors[(left, top)])

    result = pixelate_frame_images([image], target_size=2)[0]

    assert result.size == (2, 2)
    assert result.getpixel((0, 0)) == (255, 0, 0, 255)
    assert result.getpixel((1, 0)) == (0, 255, 0, 255)
    assert result.getpixel((0, 1)) == (0, 0, 255, 255)
    assert result.getpixel((1, 1)) == (255, 255, 0, 128)


def test_pixelate_frame_images_accepts_rectangular_target_size() -> None:
    image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))

    result = pixelate_frame_images([image], target_size=(4, 2))[0]

    assert result.size == (4, 2)


def test_load_single_sheet_image_splits_and_removes_background(tmp_path: Path) -> None:
    sheet = Image.new("RGBA", (9, 4), (255, 255, 255, 255))
    for y in range(sheet.height):
        sheet.putpixel((4, y), (0, 0, 0, 255))
    sheet.putpixel((1, 1), (255, 0, 0, 255))
    sheet.putpixel((6, 1), (0, 255, 0, 255))
    path = tmp_path / "sheet.png"
    sheet.save(path)

    frames = load_frame_images([path])

    assert len(frames) == 2
    assert frames[0].getpixel((0, 0)) == (0, 0, 0, 0)
    assert frames[0].getpixel((1, 1)) == (255, 0, 0, 255)
    assert frames[1].getpixel((1, 1)) == (0, 255, 0, 255)


def test_load_single_sheet_image_uses_custom_background_and_separator_colors(tmp_path: Path) -> None:
    sheet = Image.new("RGBA", (9, 4), (0, 252, 0, 255))
    for y in range(sheet.height):
        sheet.putpixel((4, y), (5, 0, 250, 255))
    sheet.putpixel((1, 1), (255, 0, 0, 255))
    sheet.putpixel((6, 1), (0, 0, 0, 255))
    path = tmp_path / "sheet.png"
    sheet.save(path)

    frames = load_frame_images(
        [path],
        background_color="#00ff00",
        background_tolerance=4,
        separator_color="#0000ff",
        separator_tolerance=8,
    )

    assert len(frames) == 2
    assert frames[0].getpixel((0, 0)) == (0, 0, 0, 0)
    assert frames[0].getpixel((1, 1)) == (255, 0, 0, 255)
    assert frames[1].getpixel((1, 1)) == (0, 0, 0, 255)


def _green_frame_with_subject(top_left: tuple[int, int]) -> Image.Image:
    image = Image.new("RGBA", (8, 8), (3, 245, 9, 0))
    for y in range(image.height):
        image.putpixel((0, y), (0, 20, 0, 255))
    left, top = top_left
    for x in range(left, left + 2):
        for y in range(top, top + 2):
            image.putpixel((x, y), (255, 0, 0, 255))
    return image


def _bbox_center(bbox: tuple[int, int, int, int] | None) -> tuple[float, float] | None:
    if bbox is None:
        return None
    left, top, right, bottom = bbox
    return (left + right) / 2, (top + bottom) / 2


def _bbox_bottom_center(bbox: tuple[int, int, int, int] | None) -> tuple[float, int] | None:
    if bbox is None:
        return None
    left, _, right, bottom = bbox
    return (left + right) / 2, bottom
