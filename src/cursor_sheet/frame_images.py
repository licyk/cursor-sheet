"""Load and prepare frame images from files or contact sheets."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np
from PIL import Image, ImageColor

RgbColor = tuple[int, int, int]
COLOR_BUCKET_SIZE = 16
ALIGN_ANCHORS = {"center", "bottom-center"}


@dataclass(frozen=True)
class BackgroundCandidate:
    color: RgbColor
    tolerance: int = 0


def load_frame_images(
    paths: Sequence[Path],
    *,
    sheet_mode: str = "auto",
    remove_background: bool = True,
    background_color: str | RgbColor | None = None,
    background_tolerance: int = 0,
    separator_color: str | RgbColor = "#000000",
    separator_tolerance: int = 20,
) -> list[Image.Image]:
    """Load ordered frame images, optionally splitting a single contact sheet."""

    if sheet_mode not in {"auto", "split", "single"}:
        raise ValueError(f"unsupported sheet mode {sheet_mode!r}")
    if background_tolerance < 0:
        raise ValueError("background tolerance must not be negative")
    if separator_tolerance < 0:
        raise ValueError("separator tolerance must not be negative")

    background_rgb = _parse_optional_rgb(background_color)
    separator_rgb = _parse_rgb(separator_color)

    if len(paths) == 1:
        with Image.open(paths[0]) as image:
            rgba = image.convert("RGBA").copy()
        images = _images_from_single_input(
            rgba,
            sheet_mode=sheet_mode,
            separator_color=separator_rgb,
            separator_tolerance=separator_tolerance,
            background_color=background_rgb,
            background_tolerance=background_tolerance,
        )
    else:
        images = []
        for path in paths:
            with Image.open(path) as image:
                images.append(image.convert("RGBA").copy())

    if remove_background:
        return [remove_solid_background(image, background_color=background_rgb, tolerance=background_tolerance) for image in images]
    return images


def split_contact_sheet(
    image: Image.Image,
    *,
    separator_color: str | RgbColor = "#000000",
    separator_tolerance: int = 20,
    min_coverage: float = 0.98,
    background_color: str | RgbColor | None = None,
    background_tolerance: int = 0,
) -> list[Image.Image]:
    """Split a separator-line contact sheet into row-major frame images."""

    rgba = image.convert("RGBA")
    separator_rgb = _parse_rgb(separator_color)
    background_rgb = _parse_optional_rgb(background_color)
    column_runs = _separator_runs(
        rgba,
        axis="x",
        separator_color=separator_rgb,
        separator_tolerance=separator_tolerance,
        min_coverage=min_coverage,
    )
    row_runs = _separator_runs(
        rgba,
        axis="y",
        separator_color=separator_rgb,
        separator_tolerance=separator_tolerance,
        min_coverage=min_coverage,
    )
    if not column_runs and not row_runs:
        return [rgba.copy()]

    x_sections = _filter_tiny_sections(_sections_from_runs(rgba.width, column_runs))
    y_sections = _filter_tiny_sections(_sections_from_runs(rgba.height, row_runs))
    frames: list[Image.Image] = []
    for top, bottom in y_sections:
        for left, right in x_sections:
            crop = rgba.crop((left, top, right, bottom))
            if not _is_blank_cell(crop, background_color=background_rgb, background_tolerance=background_tolerance):
                frames.append(crop)
    return frames or [rgba.copy()]


def align_frame_images(images: Sequence[Image.Image], *, anchor: str = "bottom-center") -> list[Image.Image]:
    """Pad and reposition frames so their visible content shares a stable anchor."""

    if anchor not in ALIGN_ANCHORS:
        raise ValueError(f"unsupported alignment anchor {anchor!r}")
    rgba_images = [image.convert("RGBA") for image in images]
    if not rgba_images:
        return []

    canvas_width = max(image.width for image in rgba_images)
    canvas_height = max(image.height for image in rgba_images)
    target_x, target_y = _anchor_point((0, 0, canvas_width, canvas_height), anchor)

    aligned: list[Image.Image] = []
    for image in rgba_images:
        foreground, bbox = _extract_alignment_foreground(image)
        canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        if bbox is None:
            aligned.append(canvas)
            continue

        crop = foreground.crop(bbox)
        source_x, source_y = _anchor_point((0, 0, crop.width, crop.height), anchor)
        left = round(target_x - source_x)
        top = round(target_y - source_y)
        left = min(max(left, 0), canvas_width - crop.width)
        top = min(max(top, 0), canvas_height - crop.height)
        canvas.alpha_composite(crop, (left, top))
        aligned.append(canvas)
    return aligned


def pixelate_frame_images(images: Sequence[Image.Image], *, target_size: int | tuple[int, int]) -> list[Image.Image]:
    """Resize frames to a low-resolution pixel-art size using nearest-neighbor sampling."""

    width, height = _normalize_pixelate_size(target_size)
    return [image.convert("RGBA").resize((width, height), Image.Resampling.NEAREST) for image in images]


def remove_solid_background(
    image: Image.Image,
    *,
    background_color: str | RgbColor | None = None,
    tolerance: int = 0,
) -> Image.Image:
    """Make a detected solid border background transparent."""

    rgba = image.convert("RGBA")
    explicit_background = background_color is not None
    candidate = BackgroundCandidate(_parse_rgb(background_color), tolerance) if explicit_background else _detect_background(rgba)
    if candidate is None:
        return rgba.copy()
    background = candidate.color
    effective_tolerance = tolerance if explicit_background or tolerance > 0 else candidate.tolerance

    pixels = list(rgba.getdata())
    opaque_count = sum(1 for _, _, _, alpha in pixels if alpha > 0)
    match_count = sum(
        1
        for red, green, blue, alpha in pixels
        if alpha > 0 and _matches_background_rgb((red, green, blue), background, effective_tolerance)
    )
    if opaque_count == 0 or (match_count == opaque_count and not explicit_background):
        return rgba.copy()

    background_like_mask = _background_like_mask(rgba, candidate).reshape(-1).tolist()
    edge_background_mask = _edge_connected_background_mask(rgba, candidate)
    combined_background_mask = [
        background_like or edge_background
        for background_like, edge_background in zip(background_like_mask, edge_background_mask)
    ]
    if any(combined_background_mask):
        output = Image.new("RGBA", rgba.size)
        output.putdata(
            [
                (0, 0, 0, 0) if combined_background_mask[index] else (red, green, blue, alpha)
                for index, (red, green, blue, alpha) in enumerate(pixels)
            ]
        )
        return output

    output = Image.new("RGBA", rgba.size)
    output.putdata(
        [
            (0, 0, 0, 0)
            if alpha > 0 and _matches_background_rgb((red, green, blue), background, effective_tolerance)
            else (red, green, blue, alpha)
            for red, green, blue, alpha in pixels
        ]
    )
    return output


def _extract_alignment_foreground(image: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int] | None]:
    alpha_bbox = image.getchannel("A").getbbox()
    if alpha_bbox is None:
        return image.copy(), None

    candidate = _detect_alignment_background(image)
    if candidate is None:
        return image.copy(), alpha_bbox

    width, height = image.size
    pixels = list(image.getdata())
    background_mask = _edge_connected_background_mask(image, candidate)
    bounds = _foreground_bounds(pixels, width, background_mask)
    if bounds is None:
        return image.copy(), alpha_bbox

    cleaned_pixels = [
        (0, 0, 0, 0) if background_mask[index] else (red, green, blue, alpha)
        for index, (red, green, blue, alpha) in enumerate(pixels)
    ]
    cleaned = Image.new("RGBA", image.size)
    cleaned.putdata(cleaned_pixels)
    return cleaned, bounds


def _detect_alignment_background(image: Image.Image) -> BackgroundCandidate | None:
    transparent_colors = [(red, green, blue) for red, green, blue, alpha in image.getdata() if alpha == 0]
    if transparent_colors:
        clustered = _detect_clustered_background(transparent_colors, transparent_colors)
        if clustered is not None:
            return clustered
        color, _ = Counter(transparent_colors).most_common(1)[0]
        if max(color) > 16:
            return BackgroundCandidate(color, _auto_background_tolerance(color))
        return None
    return _detect_background(image)


def _edge_connected_background_mask(
    image: Image.Image,
    candidate: BackgroundCandidate,
) -> list[bool]:
    background_like = _background_like_mask(image, candidate)

    labels_count, labels = cv2.connectedComponents(background_like.astype(np.uint8), connectivity=8)
    if labels_count <= 1:
        return [False] * (image.width * image.height)

    border_labels = set(np.unique(labels[0, :]))
    border_labels.update(np.unique(labels[-1, :]))
    border_labels.update(np.unique(labels[:, 0]))
    border_labels.update(np.unique(labels[:, -1]))
    border_labels.discard(0)
    if not border_labels:
        return [False] * (image.width * image.height)

    mask = np.isin(labels, list(border_labels))
    return mask.reshape(-1).tolist()


def _background_like_mask(image: Image.Image, candidate: BackgroundCandidate):
    rgba = np.asarray(image, dtype=np.uint8)
    alpha = rgba[:, :, 3]
    background_like = alpha == 0
    background_like |= _alignment_background_mask_cv2(rgba[:, :, :3], candidate)
    return background_like


def _foreground_bounds(
    pixels: list[tuple[int, int, int, int]],
    width: int,
    background_mask: list[bool],
) -> tuple[int, int, int, int] | None:
    height = len(pixels) // width
    alpha = np.array([alpha for *_, alpha in pixels], dtype=np.uint8).reshape((height, width))
    background = np.array(background_mask, dtype=bool).reshape((height, width))
    foreground = (alpha > 0) & ~background
    foreground_count = int(foreground.sum())
    if foreground_count == 0:
        return None

    labels_count, labels, stats, _ = cv2.connectedComponentsWithStats(foreground.astype(np.uint8), connectivity=8)
    if labels_count <= 1:
        return None

    min_area = max(4, foreground_count // 500)
    significant_labels = [label for label in range(1, labels_count) if stats[label, cv2.CC_STAT_AREA] >= min_area]
    if not significant_labels:
        significant_labels = list(range(1, labels_count))

    left = min(int(stats[label, cv2.CC_STAT_LEFT]) for label in significant_labels)
    top = min(int(stats[label, cv2.CC_STAT_TOP]) for label in significant_labels)
    right = max(int(stats[label, cv2.CC_STAT_LEFT] + stats[label, cv2.CC_STAT_WIDTH]) for label in significant_labels)
    bottom = max(int(stats[label, cv2.CC_STAT_TOP] + stats[label, cv2.CC_STAT_HEIGHT]) for label in significant_labels)
    return left, top, right, bottom


def _anchor_point(bbox: tuple[int, int, int, int], anchor: str) -> tuple[float, float]:
    left, top, right, bottom = bbox
    if anchor == "bottom-center":
        return (left + right) / 2, float(bottom)
    return (left + right) / 2, (top + bottom) / 2


def _normalize_pixelate_size(target_size: int | tuple[int, int]) -> tuple[int, int]:
    if isinstance(target_size, int):
        width = height = target_size
    else:
        if len(target_size) != 2:
            raise ValueError("pixelate target size must contain width and height")
        width, height = target_size
    if width <= 0 or height <= 0:
        raise ValueError("pixelate target size must be greater than zero")
    return width, height


def _images_from_single_input(
    image: Image.Image,
    *,
    sheet_mode: str,
    separator_color: RgbColor,
    separator_tolerance: int,
    background_color: RgbColor | None,
    background_tolerance: int,
) -> list[Image.Image]:
    if sheet_mode == "single":
        return [image]
    frames = split_contact_sheet(
        image,
        separator_color=separator_color,
        separator_tolerance=separator_tolerance,
        background_color=background_color,
        background_tolerance=background_tolerance,
    )
    if sheet_mode == "split" and len(frames) == 1 and frames[0].size == image.size:
        return frames
    return frames


def _separator_runs(
    image: Image.Image,
    *,
    axis: str,
    separator_color: RgbColor,
    separator_tolerance: int,
    min_coverage: float,
) -> list[tuple[int, int]]:
    length = image.width if axis == "x" else image.height
    cross_length = image.height if axis == "x" else image.width
    separators: list[int] = []
    for index in range(length):
        match_count = 0
        for cross in range(cross_length):
            pixel = image.getpixel((index, cross) if axis == "x" else (cross, index))
            if _matches_pixel_rgb(pixel, separator_color, separator_tolerance):
                match_count += 1
        if match_count / cross_length >= min_coverage:
            separators.append(index)
    return _group_contiguous(separators)


def _sections_from_runs(size: int, runs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    starts = [0] + [end for _, end in runs]
    ends = [start for start, _ in runs] + [size]
    return [(start, end) for start, end in zip(starts, ends) if end > start]


def _filter_tiny_sections(sections: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if len(sections) <= 1:
        return sections

    sizes = [end - start for start, end in sections]
    largest = max(sizes)
    if largest < 16:
        return sections

    minimum_size = max(2, largest // 4)
    filtered = [(start, end) for start, end in sections if end - start >= minimum_size]
    return filtered or sections


def _group_contiguous(values: list[int]) -> list[tuple[int, int]]:
    if not values:
        return []
    runs: list[tuple[int, int]] = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        runs.append((start, previous + 1))
        start = previous = value
    runs.append((start, previous + 1))
    return runs


def _is_blank_cell(
    image: Image.Image,
    *,
    background_color: RgbColor | None = None,
    background_tolerance: int = 0,
) -> bool:
    if image.getbbox() is None:
        return True
    candidate = BackgroundCandidate(background_color, background_tolerance) if background_color is not None else _detect_background(image)
    background = None if candidate is None else candidate.color
    if background is None:
        return False
    effective_tolerance = background_tolerance if background_color is not None or background_tolerance > 0 else candidate.tolerance
    for red, green, blue, alpha in image.getdata():
        if alpha > 0 and not _matches_background_rgb((red, green, blue), background, effective_tolerance):
            return False
    return True


def _detect_background(image: Image.Image) -> BackgroundCandidate | None:
    rgba = image.convert("RGBA")
    opaque_pixels = [_rgb_if_opaque(pixel) for pixel in rgba.getdata()]
    opaque_colors = [color for color in opaque_pixels if color is not None]
    if not opaque_colors:
        return None

    border_colors = [_rgb_if_opaque(pixel) for pixel in _border_pixels(rgba)]
    opaque_border = [color for color in border_colors if color is not None]
    color_counts = Counter(opaque_colors)
    border_counts = Counter(opaque_border)

    dominant_color, dominant_count = color_counts.most_common(1)[0]
    dominant_ratio = dominant_count / len(opaque_colors)
    border_ratio = border_counts[dominant_color] / len(opaque_border) if opaque_border else 0
    if dominant_ratio >= 0.15 and border_ratio >= 0.03:
        return BackgroundCandidate(dominant_color, _auto_background_tolerance(dominant_color))
    if opaque_border and dominant_ratio >= 0.35:
        return BackgroundCandidate(dominant_color, _auto_background_tolerance(dominant_color))

    clustered_candidate = _detect_clustered_background(opaque_colors, opaque_border)
    if clustered_candidate is not None:
        return clustered_candidate

    corner_colors = [_rgb_if_opaque(rgba.getpixel(point)) for point in _corner_points(rgba)]
    corner_counts = Counter(color for color in corner_colors if color is not None)
    if corner_counts:
        color, count = corner_counts.most_common(1)[0]
        if count >= 3:
            return BackgroundCandidate(color, _auto_background_tolerance(color))

    if not opaque_border:
        return None
    color, count = Counter(opaque_border).most_common(1)[0]
    if count / len(opaque_border) >= 0.8:
        return BackgroundCandidate(color, _auto_background_tolerance(color))
    return None


def _detect_clustered_background(opaque_colors: list[RgbColor], opaque_border: list[RgbColor]) -> BackgroundCandidate | None:
    bucket_counts: Counter[tuple[int, int, int]] = Counter()
    bucket_sums: dict[tuple[int, int, int], list[int]] = {}
    for color in opaque_colors:
        key = _color_bucket(color)
        bucket_counts[key] += 1
        sums = bucket_sums.setdefault(key, [0, 0, 0])
        sums[0] += color[0]
        sums[1] += color[1]
        sums[2] += color[2]

    if not bucket_counts:
        return None

    border_buckets = Counter(_color_bucket(color) for color in opaque_border)
    bucket, count = bucket_counts.most_common(1)[0]
    cluster_ratio = count / len(opaque_colors)
    border_ratio = border_buckets[bucket] / len(opaque_border) if opaque_border else 0
    if cluster_ratio < 0.15:
        return None
    if border_ratio < 0.03 and cluster_ratio < 0.35:
        return None

    red_sum, green_sum, blue_sum = bucket_sums[bucket]
    color = (
        int(round(red_sum / count)),
        int(round(green_sum / count)),
        int(round(blue_sum / count)),
    )
    return BackgroundCandidate(color, max(_auto_background_tolerance(color), COLOR_BUCKET_SIZE))


def _color_bucket(color: RgbColor) -> tuple[int, int, int]:
    return tuple(channel // COLOR_BUCKET_SIZE for channel in color)


def _auto_background_tolerance(color: RgbColor) -> int:
    red, green, blue = color
    channels = sorted(color)
    if channels[-1] >= 180 and channels[-1] - channels[0] >= 120:
        return 24
    if red >= 235 and green >= 235 and blue >= 235:
        return 8
    return 4


def _corner_points(image: Image.Image) -> tuple[tuple[int, int], ...]:
    return (
        (0, 0),
        (image.width - 1, 0),
        (0, image.height - 1),
        (image.width - 1, image.height - 1),
    )


def _border_pixels(image: Image.Image):
    width, height = image.size
    for x in range(width):
        yield image.getpixel((x, 0))
        yield image.getpixel((x, height - 1))
    for y in range(1, height - 1):
        yield image.getpixel((0, y))
        yield image.getpixel((width - 1, y))


def _rgb_if_opaque(pixel: tuple[int, int, int, int]) -> tuple[int, int, int] | None:
    red, green, blue, alpha = pixel
    if alpha == 0:
        return None
    return red, green, blue


def _matches_pixel_rgb(pixel: tuple[int, int, int, int], color: RgbColor, tolerance: int) -> bool:
    red, green, blue, alpha = pixel
    return alpha > 0 and _close_rgb((red, green, blue), color, tolerance)


def _matches_background_rgb(color: RgbColor, background: RgbColor, tolerance: int) -> bool:
    if _close_rgb(color, background, tolerance):
        return True
    return _matches_chroma_key(color, background)


def _alignment_background_mask_cv2(rgb, candidate: BackgroundCandidate):
    color = np.array(candidate.color, dtype=np.int16)
    rgb16 = rgb.astype(np.int16)
    close = np.all(np.abs(rgb16 - color) <= candidate.tolerance, axis=2)

    key_channel = int(np.argmax(color))
    sorted_background = np.sort(color)
    if sorted_background[-1] < 180 or sorted_background[-1] - sorted_background[1] < 100:
        return close

    key_value = rgb16[:, :, key_channel]
    other_channels = [index for index in range(3) if index != key_channel]
    strongest_other = np.max(rgb16[:, :, other_channels], axis=2)
    weakest_other = np.min(rgb16[:, :, other_channels], axis=2)
    chroma = (key_value >= 80) & (key_value - strongest_other >= 40)
    dark_chroma = (np.max(rgb16, axis=2) <= 80) & (key_value >= 4) & (key_value >= strongest_other + 2)
    muted_chroma = (key_value >= 80) & (key_value >= strongest_other + 18) & (key_value >= weakest_other + 30)
    relaxed_chroma = (key_value >= 16) & (key_value >= strongest_other + 8) & (key_value >= strongest_other * 1.3)
    return close | chroma | dark_chroma | muted_chroma | relaxed_chroma


def _matches_chroma_key(color: RgbColor, background: RgbColor) -> bool:
    key_channel = max(range(3), key=lambda index: background[index])
    sorted_background = sorted(background)
    if sorted_background[-1] < 180 or sorted_background[-1] - sorted_background[1] < 100:
        return False

    key_value = color[key_channel]
    other_values = [value for index, value in enumerate(color) if index != key_channel]
    return key_value >= 80 and key_value - max(other_values) >= 40


def _parse_optional_rgb(color: str | RgbColor | None) -> RgbColor | None:
    if color is None:
        return None
    return _parse_rgb(color)


def _parse_rgb(color: str | RgbColor) -> RgbColor:
    if isinstance(color, tuple):
        if len(color) != 3:
            raise ValueError("RGB colors must contain exactly three channels")
        red, green, blue = color
        if any(channel < 0 or channel > 255 for channel in color):
            raise ValueError("RGB color channels must be between 0 and 255")
        return red, green, blue

    red, green, blue = ImageColor.getrgb(color)[:3]
    return red, green, blue


def _close_rgb(a: tuple[int, int, int], b: tuple[int, int, int], tolerance: int) -> bool:
    return all(abs(left - right) <= tolerance for left, right in zip(a, b))
