"""Command line interface for converting image sequences to cursor files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from PIL import ImageColor

from cursor_sheet.frame_images import align_frame_images, load_frame_images, pixelate_frame_images
from cursor_sheet.writer import write_ani, write_cur

DEFAULT_OUTPUT = Path("output/generated_cursor.ani")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return run_from_args(args, parser)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create Windows cursor files from ordered frame images.")
    add_arguments(parser)
    return parser


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", type=Path, help="a frame image or a directory containing frame images")
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT, help="output .ani or .cur file")
    parser.add_argument("--pattern", default="*.png", help="glob used when input is a directory")
    parser.add_argument("--delay-ms", type=int, default=100, help="animation delay per frame in milliseconds")
    parser.add_argument("--hotspot", default="0,0", help="cursor hotspot as X,Y")
    parser.add_argument("--format", choices=("auto", "ani", "cur"), default="auto", help="output format")
    parser.add_argument("--sheet-mode", choices=("auto", "split", "single"), default="auto", help="how to handle a single image input")
    parser.add_argument("--remove-background", choices=("auto", "none"), default="auto", help="remove detected solid frame backgrounds")
    parser.add_argument("--background-color", default="auto", help="auto or a color to remove, such as #00ff00")
    parser.add_argument("--background-tolerance", type=int, default=0, help="RGB tolerance for solid background removal")
    parser.add_argument("--separator-color", default="#000000", help="contact-sheet separator color")
    parser.add_argument("--separator-tolerance", type=int, default=20, help="RGB tolerance for separator color detection")
    parser.add_argument("--align-frames", action="store_true", help="align visible frame content to reduce animation jitter")
    parser.add_argument(
        "--align-anchor",
        choices=("bottom-center", "center"),
        default="bottom-center",
        help="anchor used by --align-frames",
    )
    parser.add_argument("--pixelate", action="store_true", help="pixelate frames before writing; defaults to 64x64")
    parser.add_argument(
        "--pixelate-size",
        help="enable pixelation and resize frames to N or WIDTHxHEIGHT pixels, such as 64 or 64x64",
    )


def run_from_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        try:
            hotspot = _parse_hotspot(args.hotspot)
            if args.delay_ms <= 0:
                raise argparse.ArgumentTypeError("--delay-ms must be greater than zero")
            if args.background_tolerance < 0:
                raise argparse.ArgumentTypeError("--background-tolerance must not be negative")
            if args.separator_tolerance < 0:
                raise argparse.ArgumentTypeError("--separator-tolerance must not be negative")
            if args.background_color.lower() != "auto":
                _validate_color(args.background_color, "--background-color")
            _validate_color(args.separator_color, "--separator-color")
            pixelate_size = None
            if args.pixelate or args.pixelate_size is not None:
                pixelate_size = _parse_pixelate_size(args.pixelate_size or "64")
            frame_paths = _find_frame_paths(args.input, args.pattern)
        except (ValueError, argparse.ArgumentTypeError) as exc:
            parser.error(str(exc))

        if not frame_paths:
            parser.error(f"no frame images found in {args.input}")
        images = load_frame_images(
            frame_paths,
            sheet_mode=args.sheet_mode,
            remove_background=args.remove_background == "auto",
            background_color=None if args.background_color.lower() == "auto" else args.background_color,
            background_tolerance=args.background_tolerance,
            separator_color=args.separator_color,
            separator_tolerance=args.separator_tolerance,
        )
        if args.align_frames:
            images = align_frame_images(images, anchor=args.align_anchor)
        if pixelate_size is not None:
            images = pixelate_frame_images(images, target_size=pixelate_size)
        output_file, output_format = _resolve_output(args.output, args.format)
        if output_format == "cur":
            if len(images) != 1:
                parser.error("writing .cur requires exactly one frame image")
            saved = write_cur(images[0], output_file, hotspot=hotspot)
        else:
            saved = write_ani(images, output_file, hotspot=hotspot, delay_ms=args.delay_ms)
        print(f"saved {saved} ({len(images)} frames, {output_format})")
        return 0
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _find_frame_paths(input_path: Path, pattern: str) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return sorted((path for path in input_path.glob(pattern) if path.is_file()), key=_natural_key)
    raise ValueError(f"input path does not exist: {input_path}")


def _resolve_output(output: Path, requested_format: str) -> tuple[Path, str]:
    if requested_format == "auto":
        output_format = "cur" if output.suffix.lower() == ".cur" else "ani"
    else:
        output_format = requested_format

    desired_suffix = f".{output_format}"
    if output.suffix.lower() != desired_suffix:
        output = output.with_suffix(desired_suffix)
    return output, output_format


def _parse_hotspot(value: str) -> tuple[int, int]:
    parts = value.replace(",", " ").split()
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("--hotspot must be formatted as X,Y")
    try:
        x, y = (int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--hotspot must contain integer coordinates") from exc
    if x < 0 or y < 0:
        raise argparse.ArgumentTypeError("--hotspot coordinates must not be negative")
    return x, y


def _parse_pixelate_size(value: str) -> tuple[int, int]:
    normalized = value.casefold().replace(",", "x").replace("*", "x").replace("×", "x")
    parts = [part.strip() for part in normalized.split("x") if part.strip()]
    if len(parts) == 1:
        parts = [parts[0], parts[0]]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("--pixelate-size must be formatted as N or WIDTHxHEIGHT")
    try:
        width, height = (int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--pixelate-size must contain integer dimensions") from exc
    if not 1 <= width <= 256 or not 1 <= height <= 256:
        raise argparse.ArgumentTypeError("--pixelate-size dimensions must be between 1 and 256 pixels")
    return width, height


def _validate_color(value: str, option_name: str) -> None:
    try:
        ImageColor.getrgb(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{option_name} is not a valid color: {value}") from exc


def _natural_key(path: Path) -> tuple[object, ...]:
    parts = re.split(r"(\d+)", path.name)
    return tuple(int(part) if part.isdigit() else part.casefold() for part in parts)


if __name__ == "__main__":
    raise SystemExit(main())
