from __future__ import annotations

from pathlib import Path

from PIL import Image

from cursor_sheet.cli import main as cursor_sheet_main
from cursor_sheet.writer import build_ani_bytes


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
    assert "demo" in captured.out
    assert "hotspot" in captured.out
