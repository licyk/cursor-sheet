"""Root command line interface for cursor-sheet tools."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import ImageColor

from cursor_sheet.cursor_demo_gui import add_arguments as add_demo_arguments
from cursor_sheet.cursor_demo_gui import run_from_args as run_demo_from_args
from cursor_sheet.frames_cli import add_arguments as add_cursor_arguments
from cursor_sheet.frames_cli import run_from_args as run_cursor_from_args
from cursor_sheet.gif import write_gif
from cursor_sheet.hotspot_viewer_gui import add_arguments as add_hotspot_arguments
from cursor_sheet.hotspot_viewer_gui import run_from_args as run_hotspot_from_args
from cursor_sheet.parser import CursorDocument, parse_cursor_file
from cursor_sheet.sheet import make_contact_sheet

SUPPORTED_SUFFIXES = {".ani", ".cur"}
DEFAULT_INPUT_CANDIDATES = (Path("Merry-Windows"), Path("cursors/Merry-Windows"))
DEFAULT_GIF_OUTPUT = Path("output/cursor_gifs")


def main(argv: list[str] | None = None) -> int:
    parser = _build_root_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


def _build_root_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cursor-sheet",
        description="Work with Windows cursor files, frame images, and cursor helper GUIs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    sheet_parser = subparsers.add_parser(
        "sheet",
        help="create PNG contact sheets from .ani/.cur files",
        description="Create PNG contact sheets from Windows cursor frames.",
    )
    add_sheet_arguments(sheet_parser)
    sheet_parser.set_defaults(func=lambda args: run_sheet_from_args(args, sheet_parser))

    cursor_parser = subparsers.add_parser(
        "cursor",
        help="create .ani/.cur files from frame images",
        description="Create Windows cursor files from ordered frame images.",
    )
    add_cursor_arguments(cursor_parser)
    cursor_parser.set_defaults(func=lambda args: run_cursor_from_args(args, cursor_parser))

    gif_parser = subparsers.add_parser(
        "gif",
        help="create GIF files from .ani/.cur files",
        description="Create animated GIF files from Windows cursor frames.",
    )
    add_gif_arguments(gif_parser)
    gif_parser.set_defaults(func=lambda args: run_gif_from_args(args, gif_parser))

    demo_parser = subparsers.add_parser(
        "demo",
        help="open the Windows system cursor preview GUI",
        description="Show a GUI grid for Windows system cursor roles.",
    )
    add_demo_arguments(demo_parser)
    demo_parser.set_defaults(func=lambda args: run_demo_from_args(args, demo_parser))

    hotspot_parser = subparsers.add_parser(
        "hotspot",
        help="open the cursor hotspot coordinate viewer",
        description="Open a GUI for inspecting cursor hotspot coordinates.",
    )
    add_hotspot_arguments(hotspot_parser)
    hotspot_parser.set_defaults(func=lambda args: run_hotspot_from_args(args, hotspot_parser))

    return parser


def add_sheet_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", nargs="?", type=Path, default=_default_input_path(), help="a .ani/.cur file or a directory containing cursor files")
    parser.add_argument("-o", "--output", type=Path, default=Path("output/cursor_sheets"), help="directory for generated PNG files")
    parser.add_argument("--columns", default="auto", help="auto or a positive integer column count")
    parser.add_argument("--scale", type=float, default=1.0, help="scale factor applied to every frame")
    parser.add_argument("--line-width", type=int, default=1, help="separator line width in pixels")
    parser.add_argument(
        "--separator-color",
        "--line-color",
        dest="separator_color",
        default="#000000",
        help="separator line color, such as #000000",
    )
    parser.add_argument(
        "--background-color",
        "--background",
        dest="background",
        default="transparent",
        help="transparent or a Pillow-compatible background color such as #ffffff",
    )
    parser.add_argument("--mode", choices=("playback", "unique"), default="playback", help="frame set to render")


def add_gif_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", type=Path, help="a .ani/.cur file or a directory containing cursor files")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_GIF_OUTPUT,
        help="output .gif file for single-file input, or output directory",
    )
    parser.add_argument("--scale", type=float, default=1.0, help="scale factor applied to every frame")
    parser.add_argument("--delay-ms", type=int, default=100, help="fallback delay for frames without cursor timing")
    parser.add_argument("--loop", type=int, default=0, help="GIF loop count; 0 loops forever")
    parser.add_argument(
        "--background-color",
        "--background",
        dest="background",
        default="transparent",
        help="transparent or a Pillow-compatible background color such as #ffffff",
    )
    parser.add_argument("--mode", choices=("playback", "unique"), default="playback", help="frame set to render")


def run_sheet_from_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        columns = _parse_columns(args.columns)
        _validate_color(args.separator_color, "--separator-color")
        if args.background.lower() != "transparent":
            _validate_color(args.background, "--background-color")
        if args.scale <= 0:
            raise argparse.ArgumentTypeError("--scale must be greater than zero")
        if args.line_width < 0:
            raise argparse.ArgumentTypeError("--line-width must not be negative")
        cursor_files = _find_cursor_files(args.input)
    except (ValueError, argparse.ArgumentTypeError) as exc:
        parser.error(str(exc))

    if not cursor_files:
        parser.error(f"no .ani or .cur files found in {args.input}")

    args.output.mkdir(parents=True, exist_ok=True)
    failures = 0
    for cursor_file in cursor_files:
        try:
            output_file, frame_count = _render_file(
                cursor_file,
                args.output,
                args.mode,
                columns,
                args.scale,
                args.line_width,
                args.separator_color,
                args.background,
            )
        except Exception as exc:  # pragma: no cover - exercised through CLI behavior
            failures += 1
            print(f"error: {cursor_file}: {exc}", file=sys.stderr)
            continue
        print(f"saved {output_file} ({frame_count} frames)")

    return 1 if failures else 0


def run_gif_from_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        if args.scale <= 0:
            raise argparse.ArgumentTypeError("--scale must be greater than zero")
        if args.delay_ms <= 0:
            raise argparse.ArgumentTypeError("--delay-ms must be greater than zero")
        if args.loop < 0:
            raise argparse.ArgumentTypeError("--loop must not be negative")
        if args.background.lower() != "transparent":
            _validate_color(args.background, "--background-color")
        cursor_files = _find_cursor_files(args.input)
    except (ValueError, argparse.ArgumentTypeError) as exc:
        parser.error(str(exc))

    if not cursor_files:
        parser.error(f"no .ani or .cur files found in {args.input}")
    if args.input.is_dir() and args.output.suffix.lower() == ".gif":
        parser.error("--output must be a directory when input is a directory")

    failures = 0
    for cursor_file in cursor_files:
        try:
            output_file, frame_count = _render_gif_file(
                cursor_file,
                args.input,
                args.output,
                args.mode,
                args.scale,
                args.delay_ms,
                args.loop,
                args.background,
            )
        except Exception as exc:  # pragma: no cover - exercised through CLI behavior
            failures += 1
            print(f"error: {cursor_file}: {exc}", file=sys.stderr)
            continue
        print(f"saved {output_file} ({frame_count} frames, gif)")

    return 1 if failures else 0


def _default_input_path() -> Path:
    for candidate in DEFAULT_INPUT_CANDIDATES:
        if candidate.exists():
            return candidate
    return DEFAULT_INPUT_CANDIDATES[0]


def _render_file(
    cursor_file: Path,
    output_dir: Path,
    mode: str,
    columns: int | None,
    scale: float,
    line_width: int,
    line_color: str,
    background: str,
) -> tuple[Path, int]:
    document = parse_cursor_file(cursor_file)
    frames = _select_frames(document, mode)
    sheet = make_contact_sheet(
        frames,
        columns=columns,
        scale=scale,
        line_width=line_width,
        line_color=line_color,
        background=background,
    )
    output_file = output_dir / f"{cursor_file.stem}.png"
    sheet.save(output_file)
    return output_file, len(frames)


def _render_gif_file(
    cursor_file: Path,
    input_path: Path,
    output: Path,
    mode: str,
    scale: float,
    delay_ms: int,
    loop: int,
    background: str,
) -> tuple[Path, int]:
    document = parse_cursor_file(cursor_file)
    frames = _select_frames(document, mode)
    output_file = _resolve_gif_output(cursor_file, input_path, output)
    write_gif(frames, output_file, scale=scale, delay_ms=delay_ms, loop=loop, background=background)
    return output_file, len(frames)


def _resolve_gif_output(cursor_file: Path, input_path: Path, output: Path) -> Path:
    if input_path.is_file() and output.suffix.lower() == ".gif":
        return output
    return output / f"{cursor_file.stem}.gif"


def _select_frames(document: CursorDocument, mode: str):
    if mode == "playback":
        return document.playback_frames
    if mode == "unique":
        return document.unique_frames
    raise ValueError(f"unsupported mode {mode!r}")


def _find_cursor_files(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"unsupported input file type: {path.suffix}")
        return [path]
    if path.is_dir():
        return sorted(item for item in path.iterdir() if item.is_file() and item.suffix.lower() in SUPPORTED_SUFFIXES)
    raise ValueError(f"input path does not exist: {path}")


def _parse_columns(value: str) -> int | None:
    if value.lower() == "auto":
        return None
    try:
        columns = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--columns must be auto or a positive integer") from exc
    if columns <= 0:
        raise argparse.ArgumentTypeError("--columns must be auto or a positive integer")
    return columns


def _validate_color(value: str, option_name: str) -> None:
    try:
        ImageColor.getcolor(value, "RGBA")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{option_name} is not a valid color: {value}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
