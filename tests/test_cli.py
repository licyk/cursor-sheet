from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageSequence

from cursor_sheet.cli import main as cursor_sheet_main
from cursor_sheet.parser import parse_cursor_file
from cursor_sheet.writer import build_ani_bytes, build_cur_bytes


def test_cursor_sheet_cli_accepts_separator_and_background_color(tmp_path: Path) -> None:
    frame_1 = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
    frame_2 = Image.new("RGBA", (2, 2), (0, 0, 255, 255))
    cursor_file = tmp_path / "cursor.ani"
    cursor_file.write_bytes(build_ani_bytes([frame_1, frame_2]))
    output_dir = tmp_path / "sheets"

    exit_code = cursor_sheet_main(
        [
            "sheet",
            str(cursor_file),
            "-o",
            str(output_dir),
            "--columns",
            "2",
            "--separator-color",
            "#00ff00",
            "--background-color",
            "#ffffff",
        ]
    )

    assert exit_code == 0
    with Image.open(output_dir / "cursor.png") as sheet:
        image = sheet.convert("RGBA")
    assert image.getpixel((2, 0)) == (0, 255, 0, 255)


def test_cursor_sheet_cli_keeps_legacy_color_option_names(tmp_path: Path) -> None:
    frame_1 = Image.new("RGBA", (1, 1), (255, 0, 0, 255))
    frame_2 = Image.new("RGBA", (1, 1), (0, 0, 255, 255))
    cursor_file = tmp_path / "cursor.ani"
    cursor_file.write_bytes(build_ani_bytes([frame_1, frame_2]))
    output_dir = tmp_path / "sheets"

    exit_code = cursor_sheet_main(
        [
            "sheet",
            str(cursor_file),
            "-o",
            str(output_dir),
            "--columns",
            "2",
            "--line-color",
            "#ff00ff",
            "--background",
            "transparent",
        ]
    )

    assert exit_code == 0
    with Image.open(output_dir / "cursor.png") as sheet:
        image = sheet.convert("RGBA")
    assert image.getpixel((1, 0)) == (255, 0, 255, 255)


def test_root_cli_lists_subcommands(capsys) -> None:
    try:
        cursor_sheet_main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("argparse should exit after printing help")

    captured = capsys.readouterr()
    assert "sheet" in captured.out
    assert "cursor" in captured.out
    assert "gif" in captured.out
    assert "gif-cursor" in captured.out
    assert "demo" in captured.out
    assert "hotspot" in captured.out


def test_cursor_to_gif_cli_writes_single_output_file_with_cursor_delays(tmp_path: Path) -> None:
    frame_1 = Image.new("RGBA", (3, 2), (255, 0, 0, 255))
    frame_2 = Image.new("RGBA", (3, 2), (0, 0, 255, 255))
    cursor_file = tmp_path / "cursor.ani"
    gif_file = tmp_path / "cursor.gif"
    cursor_file.write_bytes(build_ani_bytes([frame_1, frame_2], delay_ms=250))

    exit_code = cursor_sheet_main(["gif", str(cursor_file), "-o", str(gif_file)])

    assert exit_code == 0
    with Image.open(gif_file) as gif:
        frames = []
        durations = []
        for frame in ImageSequence.Iterator(gif):
            durations.append(frame.info["duration"])
            frames.append(frame.convert("RGBA"))
    assert len(frames) == 2
    assert durations == [250, 250]
    assert frames[0].getpixel((0, 0)) == (255, 0, 0, 255)
    assert frames[1].getpixel((0, 0)) == (0, 0, 255, 255)


def test_cursor_to_gif_cli_writes_directory_output(tmp_path: Path) -> None:
    input_dir = tmp_path / "cursors"
    output_dir = tmp_path / "gifs"
    input_dir.mkdir()
    (input_dir / "static.cur").write_bytes(build_cur_bytes(Image.new("RGBA", (4, 4), (0, 255, 0, 255))))

    exit_code = cursor_sheet_main(["gif", str(input_dir), "-o", str(output_dir), "--delay-ms", "80"])

    assert exit_code == 0
    with Image.open(output_dir / "static.gif") as gif:
        assert gif.n_frames == 1
        assert gif.size == (4, 4)


def test_cursor_to_gif_cli_keeps_transparent_background(tmp_path: Path) -> None:
    image = Image.new("RGBA", (3, 3), (0, 0, 0, 0))
    image.putpixel((1, 1), (255, 0, 0, 255))
    cursor_file = tmp_path / "cursor.cur"
    gif_file = tmp_path / "cursor.gif"
    cursor_file.write_bytes(build_cur_bytes(image))

    exit_code = cursor_sheet_main(["gif", str(cursor_file), "-o", str(gif_file)])

    assert exit_code == 0
    with Image.open(gif_file) as gif:
        frame = next(ImageSequence.Iterator(gif)).convert("RGBA")
    assert frame.getpixel((0, 0)) == (0, 0, 0, 0)
    assert frame.getpixel((1, 1)) == (255, 0, 0, 255)


def test_gif_to_cursor_cli_writes_ani_with_gif_delays(tmp_path: Path) -> None:
    frame_1 = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    frame_2 = Image.new("RGBA", (4, 4), (0, 0, 255, 255))
    gif_file = tmp_path / "input.gif"
    output_file = tmp_path / "cursor.ani"
    frame_1.save(gif_file, save_all=True, append_images=[frame_2], duration=[100, 250], loop=0)

    exit_code = cursor_sheet_main(["gif-cursor", str(gif_file), "-o", str(output_file), "--hotspot", "1,1"])

    assert exit_code == 0
    document = parse_cursor_file(output_file)
    assert [frame.delay for frame in document.playback_frames] == [0.1, 0.25]
    assert [frame.images[0].image.getpixel((0, 0)) for frame in document.playback_frames] == [
        (255, 0, 0, 255),
        (0, 0, 255, 255),
    ]
    assert [frame.images[0].hotspot for frame in document.playback_frames] == [(1, 1), (1, 1)]


def test_gif_to_cursor_cli_writes_static_cur(tmp_path: Path) -> None:
    gif_file = tmp_path / "input.gif"
    output_file = tmp_path / "cursor.cur"
    Image.new("RGBA", (4, 4), (0, 255, 0, 255)).save(gif_file)

    exit_code = cursor_sheet_main(["gif-cursor", str(gif_file), "-o", str(output_file), "--format", "cur"])

    assert exit_code == 0
    document = parse_cursor_file(output_file)
    assert len(document.playback_frames) == 1
    assert document.playback_frames[0].images[0].image.getpixel((0, 0)) == (0, 255, 0, 255)
