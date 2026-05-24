"""Lightweight Windows CUR/ANI parser for extracting cursor frame images."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable

from PIL import Image

from cursor_sheet.models import CursorFrame, CursorImage

CURSOR_TYPE = 2
ICON_TYPE = 1
CUR_MAGIC = b"\x00\x00\x02\x00"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
ANI_ICON_FLAG = 0x1
BI_RGB = 0

ICON_DIR = struct.Struct("<HHH")
ICON_DIR_ENTRY = struct.Struct("<BBBBHHII")
RIFF_HEADER = struct.Struct("<4sI4s")
CHUNK_HEADER = struct.Struct("<4sI")
ANI_HEADER = struct.Struct("<IIIIIIIII")
UINT32 = struct.Struct("<I")


@dataclass(frozen=True)
class CursorDocument:
    """A parsed cursor file with unique and playback-expanded frame lists."""

    unique_frames: tuple[CursorFrame, ...]
    playback_frames: tuple[CursorFrame, ...]


def parse_cursor_file(path: str | Path) -> CursorDocument:
    """Parse a Windows .cur or .ani file."""

    cursor_path = Path(path)
    return parse_cursor_blob(cursor_path.read_bytes())


def parse_cursor_blob(blob: bytes) -> CursorDocument:
    """Parse cursor bytes as CUR or ANI."""

    if blob.startswith(CUR_MAGIC):
        frame = _parse_cur_frame(blob, source_index=0)
        return CursorDocument(unique_frames=(frame,), playback_frames=(frame.clone(source_index=0),))
    if _is_ani(blob):
        return _parse_ani(blob)
    raise ValueError("unsupported cursor format")


def _parse_ani(blob: bytes) -> CursorDocument:
    if len(blob) < RIFF_HEADER.size:
        raise ValueError("ANI file is too small")

    signature, riff_size, subtype = RIFF_HEADER.unpack_from(blob, 0)
    if signature != b"RIFF" or subtype != b"ACON":
        raise ValueError("not an ANI file")

    end = min(len(blob), 8 + riff_size)
    unique_frames: list[CursorFrame] = []
    declared_frames = 0
    steps = 0
    default_rate = 1
    flags = 0
    order: list[int] | None = None
    rates: list[int] | None = None

    for chunk_id, size, payload_start, payload_end in _iter_chunks(blob, RIFF_HEADER.size, end):
        if chunk_id == b"anih":
            if size < ANI_HEADER.size:
                raise ValueError("ANI header is truncated")
            header_size, declared_frames, steps, _, _, _, _, default_rate, flags = ANI_HEADER.unpack_from(blob, payload_start)
            if header_size < ANI_HEADER.size:
                raise ValueError(f"unexpected ANI header size {header_size}")
            if not flags & ANI_ICON_FLAG:
                raise NotImplementedError("raw BMP ANI frames are not supported")
        elif chunk_id == b"LIST" and blob[payload_start : payload_start + 4] == b"fram":
            for child_id, child_size, child_start, child_end in _iter_chunks(blob, payload_start + 4, payload_end):
                if child_id == b"icon":
                    payload = blob[child_start : child_start + child_size]
                    unique_frames.append(_parse_cur_frame(payload, source_index=len(unique_frames)))
        elif chunk_id == b"seq ":
            order = _read_uint32_list(blob[payload_start:payload_end], "seq")
        elif chunk_id == b"rate":
            rates = _read_uint32_list(blob[payload_start:payload_end], "rate")

    if not unique_frames:
        raise ValueError("ANI file does not contain icon frames")

    declared_frames = declared_frames or len(unique_frames)
    steps = steps or declared_frames
    if order is None:
        order = list(range(steps))
    if rates is None:
        rates = [default_rate for _ in range(steps)]
    if len(order) != steps:
        raise ValueError(f"ANI sequence length {len(order)} does not match step count {steps}")
    if len(rates) != steps:
        raise ValueError(f"ANI rate length {len(rates)} does not match step count {steps}")

    playback: list[CursorFrame] = []
    for frame_index, rate in zip(order, rates):
        if frame_index >= len(unique_frames):
            raise ValueError(f"ANI sequence references missing frame {frame_index}")
        playback.append(unique_frames[frame_index].clone(delay=rate / 60.0, source_index=frame_index))

    return CursorDocument(unique_frames=tuple(unique_frames), playback_frames=tuple(playback))


def _parse_cur_frame(blob: bytes, *, source_index: int | None = None) -> CursorFrame:
    if len(blob) < ICON_DIR.size:
        raise ValueError("CUR file is too small")

    reserved, cursor_type, image_count = ICON_DIR.unpack_from(blob, 0)
    if reserved != 0 or cursor_type not in {CURSOR_TYPE, ICON_TYPE}:
        raise ValueError("not a CUR file")
    if image_count <= 0:
        raise ValueError("CUR file does not contain images")

    directory_end = ICON_DIR.size + image_count * ICON_DIR_ENTRY.size
    if len(blob) < directory_end:
        raise ValueError("CUR directory is truncated")

    images: list[CursorImage] = []
    offset = ICON_DIR.size
    for _ in range(image_count):
        width_byte, height_byte, _, _, hotspot_x, hotspot_y, payload_size, payload_offset = ICON_DIR_ENTRY.unpack_from(blob, offset)
        offset += ICON_DIR_ENTRY.size

        if payload_offset + payload_size > len(blob):
            raise ValueError("CUR image payload is truncated")

        width = 256 if width_byte == 0 else width_byte
        height = 256 if height_byte == 0 else height_byte
        payload = blob[payload_offset : payload_offset + payload_size]
        image = _decode_image_payload(payload, width, height)
        hotspot = (hotspot_x, hotspot_y) if cursor_type == CURSOR_TYPE else (0, 0)
        images.append(CursorImage(image=image, hotspot=hotspot, nominal_size=max(width, height)))

    return CursorFrame(images=tuple(images), source_index=source_index)


def _decode_image_payload(payload: bytes, entry_width: int, entry_height: int) -> Image.Image:
    if payload.startswith(PNG_MAGIC):
        with Image.open(BytesIO(payload)) as image:
            return image.convert("RGBA").copy()
    return _decode_dib_payload(payload, entry_width, entry_height)


def _decode_dib_payload(payload: bytes, entry_width: int, entry_height: int) -> Image.Image:
    if len(payload) < 40:
        raise ValueError("DIB payload is too small")

    header_size = struct.unpack_from("<I", payload, 0)[0]
    if header_size < 40 or len(payload) < header_size:
        raise ValueError(f"unsupported DIB header size {header_size}")

    width, raw_height, planes, bit_count, compression, image_size, _, _, colors_used, _ = struct.unpack_from(
        "<iiHHIIiiII", payload, 4
    )
    if planes != 1:
        raise ValueError(f"unsupported DIB plane count {planes}")
    if compression != BI_RGB:
        raise ValueError(f"unsupported compressed DIB payload {compression}")
    if bit_count not in {1, 4, 8, 24, 32}:
        raise ValueError(f"unsupported DIB bit depth {bit_count}")

    width = abs(width) or entry_width
    absolute_height = abs(raw_height)
    if width <= 0 or absolute_height <= 0:
        raise ValueError("invalid DIB dimensions")

    palette, palette_size = _read_palette(payload, header_size, bit_count, colors_used)
    pixel_offset = header_size + palette_size
    if pixel_offset > len(payload):
        raise ValueError("DIB pixel offset is outside payload")

    row_stride = ((width * bit_count + 31) // 32) * 4
    mask_stride = ((width + 31) // 32) * 4
    data_size = len(payload) - pixel_offset
    visible_height = _infer_visible_height(
        absolute_height=absolute_height,
        entry_height=entry_height,
        row_stride=row_stride,
        mask_stride=mask_stride,
        data_size=data_size,
        declared_image_size=image_size,
    )

    xor_size = row_stride * visible_height
    mask_offset = pixel_offset + xor_size
    if len(payload) < mask_offset:
        raise ValueError("DIB pixel data is truncated")
    has_mask = len(payload) >= mask_offset + mask_stride * visible_height
    bottom_up = raw_height > 0
    use_alpha = _has_meaningful_alpha(payload, pixel_offset, visible_height, row_stride, width, bit_count)

    rgba = bytearray(width * visible_height * 4)
    for y in range(visible_height):
        source_y = visible_height - 1 - y if bottom_up else y
        pixel_row = pixel_offset + source_y * row_stride
        mask_row = mask_offset + source_y * mask_stride
        for x in range(width):
            red, green, blue, alpha = _read_dib_pixel(payload, pixel_row, x, bit_count, palette, use_alpha)
            if has_mask and payload[mask_row + x // 8] & (0x80 >> (x % 8)):
                alpha = 0
            target = (y * width + x) * 4
            rgba[target : target + 4] = bytes((red, green, blue, alpha))

    return Image.frombytes("RGBA", (width, visible_height), bytes(rgba))


def _read_palette(payload: bytes, header_size: int, bit_count: int, colors_used: int) -> tuple[list[tuple[int, int, int]], int]:
    if bit_count > 8:
        return [], 0

    palette_count = colors_used or (1 << bit_count)
    palette_size = palette_count * 4
    palette_end = header_size + palette_size
    if palette_end > len(payload):
        raise ValueError("DIB color table is truncated")

    palette: list[tuple[int, int, int]] = []
    for offset in range(header_size, palette_end, 4):
        blue, green, red, _ = payload[offset : offset + 4]
        palette.append((red, green, blue))
    return palette, palette_size


def _infer_visible_height(
    *,
    absolute_height: int,
    entry_height: int,
    row_stride: int,
    mask_stride: int,
    data_size: int,
    declared_image_size: int,
) -> int:
    target_size = declared_image_size or data_size
    candidates = []
    if absolute_height % 2 == 0:
        candidates.append(absolute_height // 2)
    candidates.extend([entry_height, absolute_height])

    for height in _unique_positive(candidates):
        if row_stride * height + mask_stride * height == target_size or row_stride * height == target_size:
            return height

    for height in _unique_positive(candidates):
        if row_stride * height + mask_stride * height <= data_size or row_stride * height <= data_size:
            return height

    raise ValueError("DIB pixel data is truncated")


def _read_dib_pixel(
    payload: bytes,
    row_start: int,
    x: int,
    bit_count: int,
    palette: list[tuple[int, int, int]],
    use_alpha: bool,
) -> tuple[int, int, int, int]:
    if bit_count == 32:
        offset = row_start + x * 4
        blue, green, red, alpha = payload[offset : offset + 4]
        return red, green, blue, alpha if use_alpha else 255
    if bit_count == 24:
        offset = row_start + x * 3
        blue, green, red = payload[offset : offset + 3]
        return red, green, blue, 255

    palette_index = _read_palette_index(payload, row_start, x, bit_count)
    if palette_index >= len(palette):
        raise ValueError(f"DIB palette index {palette_index} is out of range")
    red, green, blue = palette[palette_index]
    return red, green, blue, 255


def _read_palette_index(payload: bytes, row_start: int, x: int, bit_count: int) -> int:
    if bit_count == 8:
        return payload[row_start + x]
    if bit_count == 4:
        value = payload[row_start + x // 2]
        return value >> 4 if x % 2 == 0 else value & 0x0F
    if bit_count == 1:
        return 1 if payload[row_start + x // 8] & (0x80 >> (x % 8)) else 0
    raise ValueError(f"unsupported indexed DIB bit depth {bit_count}")


def _has_meaningful_alpha(payload: bytes, pixel_offset: int, height: int, row_stride: int, width: int, bit_count: int) -> bool:
    if bit_count != 32:
        return False
    for y in range(height):
        row = pixel_offset + y * row_stride
        for x in range(width):
            if payload[row + x * 4 + 3] != 0:
                return True
    return False


def _read_uint32_list(payload: bytes, chunk_name: str) -> list[int]:
    if len(payload) % UINT32.size != 0:
        raise ValueError(f"ANI {chunk_name} chunk has invalid size")
    return [value for (value,) in UINT32.iter_unpack(payload)]


def _is_ani(blob: bytes) -> bool:
    if len(blob) < RIFF_HEADER.size:
        return False
    signature, _, subtype = RIFF_HEADER.unpack_from(blob, 0)
    return signature == b"RIFF" and subtype == b"ACON"


def _iter_chunks(blob: bytes, offset: int, end: int) -> Iterable[tuple[bytes, int, int, int]]:
    while offset + CHUNK_HEADER.size <= end:
        chunk_id, size = CHUNK_HEADER.unpack_from(blob, offset)
        payload_start = offset + CHUNK_HEADER.size
        payload_end = payload_start + size
        if payload_end > end:
            raise ValueError(f"chunk {chunk_id!r} is truncated")
        yield chunk_id, size, payload_start, payload_end
        offset = payload_end + (payload_end & 1)


def _unique_positive(values: Iterable[int]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value > 0 and value not in seen:
            result.append(value)
            seen.add(value)
    return result
