from __future__ import annotations

from pathlib import Path

from PIL import Image

from cursor_sheet.cli import main as cursor_sheet_main
from cursor_sheet.parser import parse_cursor_blob, parse_cursor_file
from cursor_sheet.writer import build_ani_bytes, build_cur_bytes


def image(color: tuple[int, int, int, int]) -> Image.Image:
    return Image.new("RGBA", (4, 4), color)


def test_build_cur_round_trips_through_parser() -> None:
    blob = build_cur_bytes(image((255, 0, 0, 255)), hotspot=(1, 2))

    document = parse_cursor_blob(blob)

    cursor_image = document.playback_frames[0].images[0]
    assert len(document.playback_frames) == 1
    assert cursor_image.image.size == (4, 4)
    assert cursor_image.hotspot == (1, 2)
    assert cursor_image.image.getpixel((0, 0)) == (255, 0, 0, 255)


def test_build_ani_round_trips_through_parser() -> None:
    blob = build_ani_bytes(
        [
            image((255, 0, 0, 255)),
            image((0, 255, 0, 255)),
            image((0, 0, 255, 255)),
        ],
        hotspot=(1, 1),
        delay_ms=100,
    )

    document = parse_cursor_blob(blob)

    assert len(document.unique_frames) == 3
    assert len(document.playback_frames) == 3
    assert [frame.delay for frame in document.playback_frames] == [0.1, 0.1, 0.1]
    assert [frame.images[0].hotspot for frame in document.playback_frames] == [(1, 1), (1, 1), (1, 1)]


def test_build_ani_accepts_per_frame_delays() -> None:
    blob = build_ani_bytes(
        [
            image((255, 0, 0, 255)),
            image((0, 255, 0, 255)),
        ],
        hotspot=(1, 1),
        frame_delays_ms=[100, 250],
    )

    document = parse_cursor_blob(blob)

    assert [frame.delay for frame in document.playback_frames] == [0.1, 0.25]


def test_frames_to_cursor_cli_uses_natural_sort(tmp_path: Path) -> None:
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    Image.new("RGBA", (4, 4), (0, 255, 0, 255)).save(frames_dir / "frame_2.png")
    Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(frames_dir / "frame_1.png")
    Image.new("RGBA", (4, 4), (0, 0, 255, 255)).save(frames_dir / "frame_10.png")
    output_file = tmp_path / "cursor.ani"

    exit_code = cursor_sheet_main(["cursor", str(frames_dir), "-o", str(output_file), "--hotspot", "1,1"])

    assert exit_code == 0
    document = parse_cursor_file(output_file)
    colors = [frame.images[0].image.getpixel((0, 0)) for frame in document.playback_frames]
    assert colors == [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
    ]


def test_frames_to_cursor_cli_splits_sheet_and_removes_background(tmp_path: Path) -> None:
    sheet = Image.new("RGBA", (9, 4), (255, 255, 255, 255))
    for y in range(sheet.height):
        sheet.putpixel((4, y), (0, 0, 0, 255))
    sheet.putpixel((1, 1), (255, 0, 0, 255))
    sheet.putpixel((6, 1), (0, 255, 0, 255))
    sheet_file = tmp_path / "sheet.png"
    output_file = tmp_path / "cursor.ani"
    sheet.save(sheet_file)

    exit_code = cursor_sheet_main(["cursor", str(sheet_file), "-o", str(output_file), "--hotspot", "1,1"])

    assert exit_code == 0
    document = parse_cursor_file(output_file)
    assert len(document.playback_frames) == 2
    assert document.playback_frames[0].images[0].image.getpixel((0, 0)) == (0, 0, 0, 0)
    assert document.playback_frames[0].images[0].image.getpixel((1, 1)) == (255, 0, 0, 255)
    assert document.playback_frames[1].images[0].image.getpixel((1, 1)) == (0, 255, 0, 255)


def test_frames_to_cursor_cli_can_align_frames(tmp_path: Path) -> None:
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    first = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    second = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    for x in range(1, 3):
        for y in range(1, 3):
            first.putpixel((x, y), (255, 0, 0, 255))
    for x in range(4, 6):
        for y in range(3, 5):
            second.putpixel((x, y), (255, 0, 0, 255))
    first.save(frames_dir / "frame_1.png")
    second.save(frames_dir / "frame_2.png")
    output_file = tmp_path / "cursor.ani"

    exit_code = cursor_sheet_main(
        [
            "cursor",
            str(frames_dir),
            "-o",
            str(output_file),
            "--hotspot",
            "1,1",
            "--align-frames",
            "--align-anchor",
            "center",
        ]
    )

    assert exit_code == 0
    document = parse_cursor_file(output_file)
    bboxes = [frame.images[0].image.getchannel("A").getbbox() for frame in document.playback_frames]
    assert [_bbox_center(bbox) for bbox in bboxes] == [(4.0, 4.0), (4.0, 4.0)]


def test_frames_to_cursor_cli_can_pixelate_frames(tmp_path: Path) -> None:
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(frames_dir / "frame_1.png")
    Image.new("RGBA", (8, 8), (0, 0, 255, 255)).save(frames_dir / "frame_2.png")
    output_file = tmp_path / "cursor.ani"

    exit_code = cursor_sheet_main(
        ["cursor", str(frames_dir), "-o", str(output_file), "--hotspot", "1,1", "--pixelate-size", "4x2"]
    )

    assert exit_code == 0
    document = parse_cursor_file(output_file)
    assert [frame.images[0].image.size for frame in document.playback_frames] == [(4, 2), (4, 2)]
    assert document.playback_frames[0].images[0].image.getpixel((0, 0)) == (255, 0, 0, 255)
    assert document.playback_frames[1].images[0].image.getpixel((0, 0)) == (0, 0, 255, 255)


def _bbox_center(bbox: tuple[int, int, int, int] | None) -> tuple[float, float] | None:
    if bbox is None:
        return None
    left, top, right, bottom = bbox
    return (left + right) / 2, (top + bottom) / 2
