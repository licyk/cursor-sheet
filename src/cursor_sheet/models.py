"""Shared cursor data models."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class CursorImage:
    """One image candidate embedded in a cursor frame."""

    image: Image.Image
    hotspot: tuple[int, int]
    nominal_size: int

    def clone(self) -> "CursorImage":
        return CursorImage(
            image=self.image.copy(),
            hotspot=self.hotspot,
            nominal_size=self.nominal_size,
        )


@dataclass(frozen=True)
class CursorFrame:
    """One animation frame, possibly carrying multiple cursor sizes."""

    images: tuple[CursorImage, ...]
    delay: float = 0.0
    source_index: int | None = None

    def clone(self, *, delay: float | None = None, source_index: int | None = None) -> "CursorFrame":
        return CursorFrame(
            images=tuple(image.clone() for image in self.images),
            delay=self.delay if delay is None else delay,
            source_index=self.source_index if source_index is None else source_index,
        )
