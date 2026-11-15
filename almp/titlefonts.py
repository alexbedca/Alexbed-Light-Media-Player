# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stop the 6-7 s freeze on the first fullscreen / maximize on PCs with thousands of fonts.

Each time a window is maximized, restored or made fullscreen, Qt 6's Windows plugin redraws a
hidden title-bar picture (QWindowsWindow::updateCustomTitlebar). It draws the window title in
"Segoe UI" and the caption buttons in "Segoe Fluent Icons" ("Segoe MDL2 Assets" on Windows 10),
both at THIN weight. Neither font has a Thin style, and with the GDI font list (which ALMP uses
for its fast start, see app.qt_platform_override) a missing weight makes Qt look through every
installed font: 6.5 s with 9,223 fonts. ALMP froze for that long on the first press of F, and the
control bar and the picture were left half laid out.

The fix: right after the window is shown, give Qt a real Thin style of those families. It is a
copy of the PC's own font file, read from C:\\Windows\\Fonts, marked Thin, and registered for
ALMP only, in memory (QFontDatabase.addApplicationFontFromData). Nothing is installed in Windows
and no font file ships with ALMP. Only the hidden title-bar picture asks for Thin, so nothing
ALMP shows looks different. Measured: about 15 ms; first fullscreen 6.4 s -> 0.03 s.

The families must already be loaded by Qt before the copies are registered; registering first
made the first normal use of "Segoe UI" take 6.6 s instead.
"""
import logging
import os
import struct
import sys

log = logging.getLogger("almp")

# (font file in C:\Windows\Fonts, family name Qt asks for)
TITLE_BAR_FONTS = (("segoeui.ttf", "Segoe UI"),
                   ("SegoeIcons.ttf", "Segoe Fluent Icons"),
                   ("segmdl2.ttf", "Segoe MDL2 Assets"))
THIN = 100


def thin_copy(data, family, weight=THIN, style="Thin"):
    """A copy of TrueType/OpenType font `data` named `family` / `style`, with OS/2 weight `weight`.

    The 'name' table is replaced by a small new one (added at the end of the file) and the OS/2
    weight is changed. Everything else (glyphs, metrics) stays as it is."""
    if len(data) < 12:
        raise ValueError("not a font file")
    num = struct.unpack_from(">H", data, 4)[0]
    tables = {}
    for i in range(num):
        tag, _chk, off, ln = struct.unpack_from(">4sIII", data, 12 + 16 * i)
        tables[tag] = (i, off, ln)
    if b"name" not in tables or b"OS/2" not in tables:
        raise ValueError("font has no name or OS/2 table")
    out = bytearray(data)
    struct.pack_into(">H", out, tables[b"OS/2"][1] + 4, weight)
    names = ((1, family), (2, style), (3, f"{family} {style} (ALMP)"), (4, f"{family} {style}"),
             (6, f"{family}-{style}".replace(" ", "")))
    records, strings = b"", b""
    for name_id, text in names:
        raw = text.encode("utf-16-be")
        records += struct.pack(">HHHHHH", 3, 1, 0x409, name_id, len(raw), len(strings))
        strings += raw
    table = struct.pack(">HHH", 0, len(names), 6 + 12 * len(names)) + records + strings
    out += b"\0" * (-len(out) % 4)
    offset = len(out)
    out += table + b"\0" * (-len(table) % 4)
    padded = table + b"\0" * (-len(table) % 4)
    checksum = sum(struct.unpack(f">{len(padded) // 4}I", padded)) & 0xFFFFFFFF
    struct.pack_into(">III", out, 12 + 16 * tables[b"name"][0] + 4, checksum, offset, len(table))
    return bytes(out)


def register_thin_title_fonts(fonts_dir=None):
    """Windows only: register Thin copies of the title-bar fonts. Returns the families registered.

    Call it after the main window is shown (the families are loaded by then). Never raises."""
    if sys.platform != "win32":
        return []
    try:
        from PyQt6.QtCore import QByteArray
        from PyQt6.QtGui import QFont, QFontDatabase, QFontInfo
    except ImportError:
        return []
    fonts_dir = fonts_dir or os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    done = []
    try:
        installed = set(QFontDatabase.families())
    except RuntimeError:
        return []
    for file_name, family in TITLE_BAR_FONTS:
        path = os.path.join(fonts_dir, file_name)
        if family not in installed or not os.path.isfile(path):
            continue
        try:
            QFontInfo(QFont(family, 9)).weight()      # make sure Qt has loaded the family's own styles
            if "Thin" in QFontDatabase.styles(family):
                continue                               # a real Thin style is installed: nothing to do
            with open(path, "rb") as f:
                data = thin_copy(f.read(), family)
            if QFontDatabase.addApplicationFontFromData(QByteArray(data)) >= 0:
                done.append(family)
        except (OSError, ValueError, struct.error, RuntimeError):
            log.debug("Could not add a Thin copy of %s", family, exc_info=True)
    return done
