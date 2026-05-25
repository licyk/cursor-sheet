"""Command line interface for converting GIF files to cursor files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from PIL import Image, ImageSequence

from cursor_sheet.frame_images import align_frame_images, pixelate_frame_images
from cursor_sheet.writer import write_ani, write_cur

DEFAULT_OUTPUT = Path("output/gif_cursors")
GIF_SUFFIXES = {".gif"}


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input", type=Path, help="a GIF file or a directory containing GIF files")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="output .ani/.cur file for single-file input, or output directory",
    )
    parser.add_argument("--pattern", default="*.gif", help="glob used when input is a directory")
    parser.add_argument("--hotspot", default="0,0", help="cursor hotspot as X,Y")
    parser.add_argument("--format", choices=("auto", "ani", "cur"), default="auto", help="output format")
    parser.add_argument("--delay-ms", type=int, default=100, help="fallback delay for GIF frames without timing")
    parser.add_argument("--scale", type=float, default=1.0, help="scale factor applied to every frame before writing")
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
            if args.scale <= 0:
                raise argparse.ArgumentTypeError("--scale must be greater than zero")
            pixelate_size = None
            if args.pixelate or args.pixelate_size is not None:
                pixelate_size = _parse_pixelate_size(args.pixelate_size or "64")
            gif_paths = _find_gif_paths(args.input, args.pattern)
        except (ValueError, argparse.ArgumentTypeError) as exc:
            parser.error(str(exc))

        if not gif_paths:
            parser.error(f"no GIF files found in {args.input}")
        if args.input.is_dir() and args.output.suffix.lower() in {".ani", ".cur"}:
            parser.error("--output must be a directory when input is a directory")

        failures = 0
        for gif_path in gif_paths:
            try:
                output_file, output_format, frame_count = _convert_gif_file(
                    gif_path,
                    args.input,
                    args.output,
                    args.format,
                    hotspot,
                    args.delay_ms,
                    args.scale,
                    args.align_frames,
                    args.align_anchor,
                    pixelate_size,
                )
            except Exception as exc:  # pragma: no cover - exercised through CLI behavior
                failures += 1
                print(f"error: {gif_path}: {exc}", file=sys.stderr)
                continue
            print(f"saved {output_file} ({frame_count} frames, {output_format})")

        return 1 if failures else 0
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


def load_gif_frames(path: str | Path, *, default_delay_ms: int = 100) -> tuple[list[Image.Image], list[int]]:
    """Load GIF frames as RGBA images with per-frame durations in milliseconds."""

    if default_delay_ms <= 0:
        raise ValueError("default_delay_ms must be greater than zero")

    frames: list[Image.Image] = []
    durations: list[int] = []
    with Image.open(path) as image:
        if image.format != "GIF":
            raise ValueError("input file is not a GIF")
        for frame in ImageSequence.Iterator(image):
            duration = int(frame.info.get("duration") or default_delay_ms)
            if duration <= 0:
                duration = default_delay_ms
            frames.append(frame.convert("RGBA").copy())
            durations.append(duration)

    if not frames:
        raise ValueError("GIF file does not contain frames")
    return frames, durations


def _convert_gif_file(
    gif_path: Path,
    input_path: Path,
    output: Path,
    requested_format: str,
    hotspot: tuple[int, int],
    default_delay_ms: int,
    scale: float,
    align_frames: bool,
    align_anchor: str,
    pixelate_size: tuple[int, int] | None,
) -> tuple[Path, str, int]:
    images, durations = load_gif_frames(gif_path, default_delay_ms=default_delay_ms)
    if scale != 1:
        images = _scale_frame_images(images, scale)
    if align_frames:
        images = align_frame_images(images, anchor=align_anchor)
    if pixelate_size is not None:
        images = pixelate_frame_images(images, target_size=pixelate_size)

    output_file, output_format = _resolve_output(gif_path, input_path, output, requested_format)
    if output_format == "cur":
        if len(images) != 1:
            raise ValueError("writing .cur requires exactly one GIF frame")
        saved = write_cur(images[0], output_file, hotspot=hotspot)
    else:
        saved = write_ani(
            images,
            output_file,
            hotspot=hotspot,
            delay_ms=default_delay_ms,
            frame_delays_ms=durations,
        )
    return saved, output_format, len(images)


def _find_gif_paths(input_path: Path, pattern: str) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() not in GIF_SUFFIXES:
            raise ValueError(f"unsupported input file type: {input_path.suffix}")
        return [input_path]
    if input_path.is_dir():
        return sorted((path for path in input_path.glob(pattern) if path.is_file()), key=_natural_key)
    raise ValueError(f"input path does not exist: {input_path}")


def _resolve_output(input_file: Path, input_path: Path, output: Path, requested_format: str) -> tuple[Path, str]:
    if requested_format == "auto":
        output_format = "cur" if output.suffix.lower() == ".cur" else "ani"
    else:
        output_format = requested_format

    desired_suffix = f".{output_format}"
    if input_path.is_file() and output.suffix.lower() in {".ani", ".cur"}:
        return output.with_suffix(desired_suffix), output_format
    return output / f"{input_file.stem}{desired_suffix}", output_format


def _scale_frame_images(images: list[Image.Image], scale: float) -> list[Image.Image]:
    return [
        image.convert("RGBA").resize(
            (
                max(1, int(round(image.width * scale))),
                max(1, int(round(image.height * scale))),
            ),
            Image.Resampling.LANCZOS,
        )
        for image in images
    ]


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
    normalized = value.casefold().replace(",", "x").replace("*", "x").replace("\u00d7", "x")
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


def _natural_key(path: Path) -> tuple[object, ...]:
    parts = re.split(r"(\d+)", path.name)
    return tuple(int(part) if part.isdigit() else part.casefold() for part in parts)
