"""Tk GUI for previewing Windows system cursor roles."""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import platform
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class CursorDemoItem:
    name: str
    description: str
    windows_cursor_id: int
    fallback_cursor: str


CURSOR_DEMO_ITEMS: tuple[CursorDemoItem, ...] = (
    CursorDemoItem("Arrow", "正常选择", 32512, "arrow"),
    CursorDemoItem("Help", "帮助选择", 32651, "question_arrow"),
    CursorDemoItem("AppStarting", "后台运行", 32650, "watch"),
    CursorDemoItem("Wait", "忙", 32514, "watch"),
    CursorDemoItem("Crosshair", "精确选择", 32515, "crosshair"),
    CursorDemoItem("IBeam", "文本选择", 32513, "xterm"),
    CursorDemoItem("NWPen", "手写", 32631, "pencil"),
    CursorDemoItem("No", "不可用", 32648, "no"),
    CursorDemoItem("SizeNS", "垂直调整大小", 32645, "sb_v_double_arrow"),
    CursorDemoItem("SizeWE", "水平调整大小", 32644, "sb_h_double_arrow"),
    CursorDemoItem("SizeNWSE", "沿对角线调整大小 1", 32642, "size_nw_se"),
    CursorDemoItem("SizeNESW", "沿对角线调整大小 2", 32643, "size_ne_sw"),
    CursorDemoItem("SizeAll", "移动", 32646, "fleur"),
    CursorDemoItem("UpArrow", "候选", 32516, "based_arrow_up"),
    CursorDemoItem("Hand", "链接选择", 32649, "hand2"),
    CursorDemoItem("Pin", "位置选择", 32671, "target"),
    CursorDemoItem("Person", "个人选择", 32672, "person"),
)

ITEMS_BY_NAME = {item.name: item for item in CURSOR_DEMO_ITEMS}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show a GUI grid for Windows system cursor roles.")
    add_arguments(parser)
    args = parser.parse_args(argv)
    return run_from_args(args, parser)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--columns", type=int, default=4, help="number of cursor regions per row")
    parser.add_argument("--title", default="Windows Cursor Preview", help="window title")


def run_from_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.columns <= 0:
        parser.error("--columns must be greater than zero")

    launch_cursor_demo(columns=args.columns, title=args.title)
    return 0


def launch_cursor_demo(*, columns: int = 4, title: str = "Windows Cursor Preview") -> None:
    import tkinter as tk

    root = tk.Tk()
    root.title(title)
    root.minsize(860, 560)
    root.configure(bg="#f4f6f8")

    controller = CursorController()
    status = tk.StringVar(value="移动到任一区域以切换鼠标指针")

    header = tk.Frame(root, bg="#172033")
    header.pack(fill="x")
    tk.Label(
        header,
        text="Windows 鼠标指针类型预览",
        bg="#172033",
        fg="#ffffff",
        font=("Segoe UI", 18, "bold"),
        padx=20,
        pady=14,
        anchor="w",
    ).pack(fill="x")

    content = tk.Frame(root, bg="#f4f6f8", padx=16, pady=16)
    content.pack(fill="both", expand=True)
    for column in range(columns):
        content.grid_columnconfigure(column, weight=1, uniform="cursor-card")

    for index, item in enumerate(CURSOR_DEMO_ITEMS):
        row, column = divmod(index, columns)
        card = _build_cursor_card(content, item)
        card.grid(row=row, column=column, sticky="nsew", padx=8, pady=8)
        content.grid_rowconfigure(row, weight=1)
        _bind_cursor_region(card, item, controller, status.set)

    footer = tk.Label(
        root,
        textvariable=status,
        bg="#ffffff",
        fg="#172033",
        font=("Segoe UI", 10),
        anchor="w",
        padx=16,
        pady=8,
    )
    footer.pack(fill="x")
    _bind_cursor_region(footer, ITEMS_BY_NAME["Arrow"], controller, status.set)

    root.mainloop()


class CursorController:
    def __init__(self) -> None:
        self._handles: dict[str, int] = {}
        self._user32 = None
        if platform.system() == "Windows":
            self._user32 = ctypes.windll.user32
            self._user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
            self._user32.LoadCursorW.restype = wintypes.HANDLE
            self._user32.SetCursor.argtypes = [wintypes.HANDLE]
            self._user32.SetCursor.restype = wintypes.HANDLE
            for item in CURSOR_DEMO_ITEMS:
                handle = self._user32.LoadCursorW(None, ctypes.c_wchar_p(item.windows_cursor_id))
                if handle:
                    self._handles[item.name] = handle

    def apply(self, widget, item: CursorDemoItem) -> None:
        _safe_configure_cursor(widget, item.fallback_cursor)
        if self._user32 is not None and item.name in self._handles:
            self._user32.SetCursor(self._handles[item.name])


def _build_cursor_card(parent, item: CursorDemoItem):
    import tkinter as tk

    card = tk.Frame(parent, bg="#ffffff", bd=0, highlightthickness=1, highlightbackground="#cad2df")
    name = tk.Label(
        card,
        text=item.name,
        bg="#ffffff",
        fg="#111827",
        font=("Segoe UI", 13, "bold"),
        anchor="w",
    )
    desc = tk.Label(
        card,
        text=item.description,
        bg="#ffffff",
        fg="#4b5563",
        font=("Microsoft YaHei UI", 10),
        anchor="w",
    )
    system_id = tk.Label(
        card,
        text=f"IDC {item.windows_cursor_id}",
        bg="#ffffff",
        fg="#6b7280",
        font=("Segoe UI", 9),
        anchor="w",
    )
    name.pack(fill="x", padx=14, pady=(14, 2))
    desc.pack(fill="x", padx=14, pady=(0, 10))
    system_id.pack(fill="x", padx=14, pady=(0, 14))
    return card


def _bind_cursor_region(
    widget,
    item: CursorDemoItem,
    controller: CursorController,
    set_status: Callable[[str], None],
) -> None:
    def activate(_event=None) -> None:
        controller.apply(widget, item)
        set_status(f"{item.name} - {item.description}")

    widget.bind("<Enter>", activate)
    widget.bind("<Motion>", activate)
    for child in widget.winfo_children():
        _bind_cursor_region(child, item, controller, set_status)


def _safe_configure_cursor(widget, cursor: str) -> None:
    try:
        widget.configure(cursor=cursor)
    except Exception:
        widget.configure(cursor="arrow")


def cursor_names() -> tuple[str, ...]:
    return tuple(item.name for item in CURSOR_DEMO_ITEMS)


if __name__ == "__main__":
    raise SystemExit(main())
