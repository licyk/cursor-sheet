from __future__ import annotations

from cursor_sheet.cursor_demo_gui import CURSOR_DEMO_ITEMS, ITEMS_BY_NAME, cursor_names, main


def test_cursor_demo_items_match_requested_order() -> None:
    assert cursor_names() == (
        "Arrow",
        "Help",
        "AppStarting",
        "Wait",
        "Crosshair",
        "IBeam",
        "NWPen",
        "No",
        "SizeNS",
        "SizeWE",
        "SizeNWSE",
        "SizeNESW",
        "SizeAll",
        "UpArrow",
        "Hand",
        "Pin",
        "Person",
    )


def test_cursor_demo_items_have_windows_resource_ids() -> None:
    assert ITEMS_BY_NAME["Arrow"].windows_cursor_id == 32512
    assert ITEMS_BY_NAME["Hand"].windows_cursor_id == 32649
    assert ITEMS_BY_NAME["Pin"].windows_cursor_id == 32671
    assert ITEMS_BY_NAME["Person"].windows_cursor_id == 32672
    assert all(item.fallback_cursor for item in CURSOR_DEMO_ITEMS)


def test_cursor_demo_rejects_invalid_column_count(capsys) -> None:
    try:
        main(["--columns", "0"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("main should reject non-positive columns")
    captured = capsys.readouterr()
    assert "--columns must be greater than zero" in captured.err
