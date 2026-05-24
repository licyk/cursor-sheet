from __future__ import annotations

import struct
from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest

from cursor_sheet.parser import parse_cursor_blob, parse_cursor_file

ROOT = Path(__file__).resolve().parents[1]


def cursor_dir() -> Path:
    for candidate in (ROOT / "Merry-Windows", ROOT / "cursors" / "Merry-Windows"):
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Merry-Windows test cursor directory was not found")


CURSOR_DIR = cursor_dir()


@pytest.mark.parametrize(
    ("filename", "playback_count"),
    [
        ("DJye1.ani", 2),
        ("DJye2.ani", 2),
        ("Mye.ani", 2),
        ("Pye.ani", 2),
        ("Sye.ani", 2),
        ("bashi.ani", 6),
        ("dianliu.ani", 9),
        ("doki.ani", 4),
        ("help.ani", 4),
        ("lightning.ani", 6),
        ("lingdang.ani", 5),
        ("merry.ani", 9),
        ("wink.ani", 4),
        ("woniu.ani", 2),
        ("yangtuo.ani", 8),
    ],
)
def test_merry_windows_animation_counts(filename: str, playback_count: int) -> None:
    document = parse_cursor_file(CURSOR_DIR / filename)

    assert len(document.playback_frames) == playback_count
    assert all(frame.images for frame in document.playback_frames)
    assert all(image.image.mode == "RGBA" for frame in document.playback_frames for image in frame.images)


@pytest.mark.parametrize(
    ("filename", "unique_count", "source_indexes"),
    [
        ("bashi.ani", 4, [0, 1, 2, 1, 0, 3]),
        ("help.ani", 3, [0, 1, 0, 2]),
        ("lightning.ani", 4, [0, 1, 2, 1, 3, 1]),
        ("wink.ani", 3, [0, 1, 2, 1]),
    ],
)
def test_seq_chunk_expands_playback_order(filename: str, unique_count: int, source_indexes: list[int]) -> None:
    document = parse_cursor_file(CURSOR_DIR / filename)

    assert len(document.unique_frames) == unique_count
    assert [frame.source_index for frame in document.playback_frames] == source_indexes


def test_rate_chunk_sets_delay_without_changing_order() -> None:
    document = parse_cursor_file(CURSOR_DIR / "wink.ani")

    assert [frame.source_index for frame in document.playback_frames] == [0, 1, 2, 1]
    assert [frame.delay for frame in document.playback_frames] == [1.5, 0.05, 0.5, 0.05]


def test_static_cur_png_payload() -> None:
    payload = BytesIO()
    Image.new("RGBA", (3, 2), (255, 0, 0, 255)).save(payload, format="PNG")
    png = payload.getvalue()
    blob = (
        struct.pack("<HHH", 0, 2, 1)
        + struct.pack("<BBBBHHII", 3, 2, 0, 0, 1, 1, len(png), 22)
        + png
    )

    document = parse_cursor_blob(blob)

    assert len(document.unique_frames) == 1
    image = document.playback_frames[0].images[0]
    assert image.image.size == (3, 2)
    assert image.hotspot == (1, 1)
