from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from cursor_sheet.hotspot_viewer_gui import (
    canvas_to_image_pixel,
    choose_display_scale,
    load_hotspot_preview_frames,
    make_checkerboard_preview,
    main,
)
from cursor_sheet.writer import write_ani, write_cur


def test_canvas_to_image_pixel_maps_scaled_preview_coordinates() -> None:
    assert canvas_to_image_pixel(10, 20, (4, 4), (40, 40), (10, 20)) == (0, 0)
    assert canvas_to_image_pixel(49, 59, (4, 4), (40, 40), (10, 20)) == (3, 3)
    assert canvas_to_image_pixel(30, 40, (4, 4), (40, 40), (10, 20)) == (2, 2)
    assert canvas_to_image_pixel(9, 20, (4, 4), (40, 40), (10, 20)) is None
    assert canvas_to_image_pixel(50, 20, (4, 4), (40, 40), (10, 20)) is None


def test_choose_display_scale_upscales_small_images_and_fits_large_images() -> None:
    assert choose_display_scale((32, 32), (320, 160)) == 5.0
    assert choose_display_scale((1000, 500), (500, 500)) == 0.5


def test_load_hotspot_preview_frames_reads_cur_file(tmp_path: Path) -> None:
    image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
    cursor_file = tmp_path / "cursor.cur"
    write_cur(image, cursor_file, hotspot=(2, 3))

    frames = load_hotspot_preview_frames(cursor_file)

    assert len(frames) == 1
    assert frames[0].image.size == (8, 8)
    assert frames[0].hotspot == (2, 3)
    assert frames[0].label == "Frame 1/1"


def test_load_hotspot_preview_frames_reads_ani_playback_frames(tmp_path: Path) -> None:
    output_file = tmp_path / "cursor.ani"
    write_ani(
        [Image.new("RGBA", (4, 4), (255, 0, 0, 255)), Image.new("RGBA", (6, 6), (0, 0, 255, 255))],
        output_file,
        hotspot=(1, 1),
        delay_ms=100,
    )

    frames = load_hotspot_preview_frames(output_file)

    assert len(frames) == 2
    assert [frame.image.size for frame in frames] == [(4, 4), (6, 6)]
    assert [frame.hotspot for frame in frames] == [(1, 1), (1, 1)]
    assert frames[0].label.startswith("Frame 1/2")


def test_load_hotspot_preview_frames_reads_image_file(tmp_path: Path) -> None:
    image_file = tmp_path / "frame.png"
    Image.new("RGBA", (5, 7), (0, 255, 0, 128)).save(image_file)

    frames = load_hotspot_preview_frames(image_file)

    assert len(frames) == 1
    assert frames[0].image.size == (5, 7)
    assert frames[0].hotspot is None
    assert frames[0].label == "frame.png"


def test_make_checkerboard_preview_preserves_opaque_pixels() -> None:
    image = Image.new("RGBA", (1, 1), (255, 0, 0, 255))

    preview = make_checkerboard_preview(image, (4, 4))

    assert preview.size == (4, 4)
    assert preview.getpixel((0, 0)) == (255, 0, 0, 255)


def test_hotspot_viewer_help_does_not_launch_gui(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "Open a GUI" in capsys.readouterr().out
