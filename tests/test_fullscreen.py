"""Fullscreen: no freeze on the first fullscreen; the "Always play videos in fullscreen" setting.

The window tests for both are in test_qt_window.py.

The freeze: Qt's Windows plugin draws a hidden title bar in "Segoe UI" / "Segoe Fluent Icons" at
Thin weight on every maximize / fullscreen. Without a Thin style, Qt searched all installed fonts
(6.5 s with 9,223 fonts). almp/titlefonts.py gives Qt a Thin copy of the PC's own font."""
import struct

import pytest

from almp import settings, titlefonts


def fake_font(family="Segoe UI", weight=400):
    """A tiny sfnt file with only an OS/2 table and a name table (enough for thin_copy)."""
    os2 = struct.pack(">HhH", 4, 500, weight) + b"\0" * 90
    raw = family.encode("utf-16-be")
    name = struct.pack(">HHH", 0, 1, 18) + struct.pack(">HHHHHH", 3, 1, 0x409, 1, len(raw), 0) + raw
    tables = [(b"OS/2", os2), (b"name", name)]
    head = struct.pack(">IHHHH", 0x00010000, len(tables), 32, 1, 0)
    offset = 12 + 16 * len(tables)
    directory, body = b"", b""
    for tag, data in tables:
        directory += struct.pack(">4sIII", tag, 0, offset + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    return head + directory + body


def read_table(data, want):
    for i in range(struct.unpack_from(">H", data, 4)[0]):
        tag, _c, off, ln = struct.unpack_from(">4sIII", data, 12 + 16 * i)
        if tag == want:
            return data[off:off + ln]
    raise KeyError(want)


def names(data):
    tbl = read_table(data, b"name")
    count, store = struct.unpack_from(">HH", tbl, 2)
    out = {}
    for i in range(count):
        _p, _e, _l, nid, ln, off = struct.unpack_from(">HHHHHH", tbl, 6 + 12 * i)
        out[nid] = tbl[store + off:store + off + ln].decode("utf-16-be")
    return out


def test_thin_copy_sets_weight_and_names():
    out = titlefonts.thin_copy(fake_font("Segoe UI", 400), "Segoe UI")
    assert struct.unpack_from(">H", read_table(out, b"OS/2"), 4)[0] == 100
    n = names(out)
    assert n[1] == "Segoe UI" and n[2] == "Thin" and "ALMP" in n[3]
    assert len(out) % 4 == 0


def test_thin_copy_keeps_the_original_untouched():
    src = fake_font()
    titlefonts.thin_copy(src, "Segoe UI")
    assert struct.unpack_from(">H", read_table(src, b"OS/2"), 4)[0] == 400


def test_thin_copy_rejects_non_fonts():
    with pytest.raises(ValueError):
        titlefonts.thin_copy(b"not a font", "Segoe UI")


def test_title_bar_fonts_cover_windows_10_and_11():
    families = {f for _file, f in titlefonts.TITLE_BAR_FONTS}
    assert {"Segoe UI", "Segoe Fluent Icons", "Segoe MDL2 Assets"} <= families


def test_register_is_harmless_off_windows(monkeypatch):
    monkeypatch.setattr(titlefonts.sys, "platform", "linux")
    assert titlefonts.register_thin_title_fonts() == []


def test_play_fullscreen_setting_default_and_validation():
    assert settings.effective_settings({})["play_fullscreen"] is False
    assert settings.effective_settings({"play_fullscreen": True})["play_fullscreen"] is True
    assert settings.effective_settings({"play_fullscreen": "yes please"})["play_fullscreen"] is False
