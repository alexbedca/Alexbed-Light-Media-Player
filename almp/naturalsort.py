# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Natural ("human") sort: "Track 2" comes before "Track 10", like Windows Explorer.

Explorer uses StrCmpLogicalW. This is a close, portable version of it: letters are compared
without case, runs of digits are compared as numbers (numbers come before letters). It is pure
Python so it can be tested anywhere and gives the same order on every PC.

The key is one plain string (digit runs left-padded with zeros), so sorting 100,000 names is a
fast C-level string sort; making the keys is the only Python work (about 3 microseconds a name).
"""
import ntpath
import re

_DIGITS = re.compile(r"\d+")
_SEPS = re.compile(r"[\\/]+")
_PAD = 20                     # digit runs up to 20 digits compare as numbers


def _pad(m):
    g = m.group()
    return g.rjust(_PAD, "0") if len(g) < _PAD else g


def natural_key(text):
    """Sort key for one name. 'Track 2' < 'Track 10' < 'track 11' < 'Track B'.
    The original text is appended so '01' / '1' and 'ABC' / 'abc' still have a fixed order."""
    return _DIGITS.sub(_pad, text.casefold()) + "\x00" + text


def natural_path_key(path):
    """Sort a whole path folder by folder (what Explorer shows when you sort by folder).
    A folder separator sorts before every other character, so 'A\\x' comes before 'A b\\x'."""
    folded = path.casefold()
    return _SEPS.sub("\x00", _DIGITS.sub(_pad, folded))


def natural_name_key(path):
    """Sort by file name only (natural), then by folder so equal names keep a fixed order."""
    return natural_key(ntpath.basename(path)) + "\x01" + natural_path_key(path)


def natural_sorted(items, key=None):
    if key is None:
        return sorted(items, key=natural_key)
    return sorted(items, key=lambda x: natural_key(key(x)))
