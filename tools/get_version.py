# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""Print the ALMP version from `__version__` in main.py, so it is written in one place only.

Used by Build-ALMP.bat, Package-ALMP.bat and the GitHub Actions workflow.
The version must be plain X.Y.Z (ASCII digits and two dots). Anything else makes this
script fail, so a typo or stray characters can never reach a build command line.

Usage:  python tools/get_version.py [path/to/main.py]
"""
import ast
import re
import sys
from pathlib import Path

VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+", re.ASCII)


def read_version(main_py):
    tree = ast.parse(Path(main_py).read_text(encoding="utf-8"), filename=str(main_py))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
            raise ValueError("__version__ must be a plain string")
    raise ValueError("__version__ not found")


def main(argv):
    main_py = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent / "main.py"
    try:
        version = read_version(main_py)
    except Exception as exc:
        print(f"ERROR: could not read the version from {main_py}: {exc}", file=sys.stderr)
        return 1
    if VERSION_RE.fullmatch(version) is None:
        print(f"ERROR: __version__ {version!r} is not a plain X.Y.Z version", file=sys.stderr)
        return 1
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
