# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Version text checks (shared with tools/get_version.py)."""
import re

VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+", re.ASCII)


def is_valid_version(text):
    """True only for a plain X.Y.Z version (digits and two dots, nothing else)."""
    return isinstance(text, str) and VERSION_RE.fullmatch(text) is not None
