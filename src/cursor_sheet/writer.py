"""Windows CUR/ANI writing helpers."""

from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path
from typing import Sequence

from PIL import Image

CURSOR_TYPE = 2
ANI_ICON_FLAG = 0x1
JIF_RATE = 60

ICON_DIR = struct.Struct("<HHH")
ICON_DIR_ENTRY = struct.Struct("<BBBBHHII")
ANI_HEADER = struct.Struct("<IIIIIIIII")
UINT32 = struct.Struct("<I")


def write_cur(image: Image.Image, output_file: str | Path, *, hotspot: tuple[int, int] = (0, 0)) -> Path:
    """Write one image as a static Windows .cur file."""

    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_cur_bytes(image, hotspot=hotspot))
    return path


def write_ani(
    images: Sequence[Image.Image],
    output_file: str | Path,
    *,
    hotspot: tuple[int, int] = (0, 0),
    delay_ms: int = 100,
    frame_delays_ms: Sequence[int] | None = None,
) -> Path:
    """Write a sequence of images as a Windows .ani file."""

    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        build_ani_bytes(
            images,
            hotspot=hotspot,
            delay_ms=delay_ms,
            frame_delays_ms=frame_delays_ms,
        )
    )
    return path


def build_cur_bytes(image: Image.Image, *, hotspot: tuple[int, int] = (0, 0)) -> bytes:
    """Build a single-image CUR file using a PNG payload."""

    rgba = image.convert("RGBA")
    _validate_cursor_image(rgba, hotspot)
    payload = _image_to_png_bytes(rgba)
    image_offset = ICON_DIR.size + ICON_DIR_ENTRY.size
    width_byte = 0 if rgba.width == 256 else rgba.width
    height_byte = 0 if rgba.height == 256 else rgba.height
    directory = ICON_DIR.pack(0, CURSOR_TYPE, 1)
    entry = ICON_DIR_ENTRY.pack(
        width_byte,
        height_byte,
        0,
        0,
        hotspot[0],
        hotspot[1],
        len(payload),
        image_offset,
    )
    return directory + entry + payload


def build_ani_bytes(
    images: Sequence[Image.Image],
    *,
    hotspot: tuple[int, int] = (0, 0),
    delay_ms: int = 100,
    frame_delays_ms: Sequence[int] | None = None,
) -> bytes:
    """Build an ANI file from image frames in playback order."""

    if not images:
        raise ValueError("at least one frame image is required")
    delay_values_ms = _resolve_frame_delays(len(images), delay_ms, frame_delays_ms)

    rgba_images = tuple(image.convert("RGBA") for image in images)
    for image in rgba_images:
        _validate_cursor_image(image, hotspot)

    delay_jiffies = tuple(_milliseconds_to_jiffies(delay) for delay in delay_values_ms)
    max_width = max(image.width for image in rgba_images)
    max_height = max(image.height for image in rgba_images)
    frame_count = len(rgba_images)
    anih_payload = ANI_HEADER.pack(
        ANI_HEADER.size,
        frame_count,
        frame_count,
        max_width,
        max_height,
        32,
        1,
        delay_jiffies[0],
        ANI_ICON_FLAG,
    )
    rate_payload = b"".join(UINT32.pack(delay) for delay in delay_jiffies)
    frame_chunks = b"".join(
        _riff_chunk(b"icon", build_cur_bytes(image, hotspot=hotspot))
        for image in rgba_images
    )
    chunks = b"".join(
        [
            _riff_chunk(b"anih", anih_payload),
            _riff_chunk(b"rate", rate_payload),
            _riff_chunk(b"LIST", b"fram" + frame_chunks),
        ]
    )
    riff_size = 4 + len(chunks)
    return b"RIFF" + UINT32.pack(riff_size) + b"ACON" + chunks


def _resolve_frame_delays(frame_count: int, delay_ms: int, frame_delays_ms: Sequence[int] | None) -> tuple[int, ...]:
    if frame_delays_ms is None:
        if delay_ms <= 0:
            raise ValueError("delay_ms must be greater than zero")
        return tuple(delay_ms for _ in range(frame_count))
    if len(frame_delays_ms) != frame_count:
        raise ValueError("frame_delays_ms length must match image frame count")
    if any(delay <= 0 for delay in frame_delays_ms):
        raise ValueError("frame delays must be greater than zero")
    return tuple(frame_delays_ms)


def _milliseconds_to_jiffies(delay_ms: int) -> int:
    return max(1, int(round(delay_ms * JIF_RATE / 1000)))


def _validate_cursor_image(image: Image.Image, hotspot: tuple[int, int]) -> None:
    if not 1 <= image.width <= 256 or not 1 <= image.height <= 256:
        raise ValueError(f"cursor frames must be between 1 and 256 pixels, got {image.width}x{image.height}")
    x, y = hotspot
    if x < 0 or y < 0 or x >= image.width or y >= image.height:
        raise ValueError(f"hotspot {hotspot} is outside image size {image.width}x{image.height}")


def _image_to_png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _riff_chunk(chunk_id: bytes, payload: bytes) -> bytes:
    if len(chunk_id) != 4:
        raise ValueError("RIFF chunk ids must be four bytes")
    padding = b"\x00" if len(payload) % 2 else b""
    return chunk_id + UINT32.pack(len(payload)) + payload + padding
