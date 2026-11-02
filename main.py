# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""Start ALMP:  python main.py [files or folders...]

The code lives in the `almp` package (see almp/__init__.py for the map). This file is the
program's entry point (Nuitka builds it into ALMP.exe) and also re-exports the plain-logic
functions under their old names, so `import main` keeps working for scripts and tests.
"""
import os  # noqa: F401  (kept for scripts that used main.os)
import sys

from almp import __version__  # noqa: F401  (the version is set in almp/__init__.py)
from almp.ipc import connect_with_retry, make_ipc_name  # noqa: F401
from almp.logic import *  # noqa: F401,F403
from almp.media import *  # noqa: F401,F403
from almp.media import _playlist_entry_to_path  # noqa: F401
from almp.platform_win import (  # noqa: F401
    DELETE_CANCELLED,
    DELETE_FAILED,
    DELETE_OK,
    DRIVE_CDROM,
    DRIVE_FIXED,
    DRIVE_NO_ROOT_DIR,
    DRIVE_RAMDISK,
    DRIVE_REMOTE,
    DRIVE_REMOVABLE,
    DRIVE_UNKNOWN,
    FOF_ALLOWUNDO,
    FOF_NOCONFIRMATION,
    FOF_SILENT,
    FOF_WANTNUKEWARNING,
    drive_root,
    get_drive_type,
    recycle_bin_available,
    recycle_flags,
    send_to_recycle_bin,
    windows_powershell_path,
)
from almp.settings import (  # noqa: F401
    LEGACY_HISTORY_FILES,
    LEGACY_SETTINGS_KEYS,
    SCALE_CHOICES,
    load_settings,
    remove_legacy_history_files,
    save_settings,
    settings_to_save,
)
from almp.versioning import VERSION_RE, is_valid_version  # noqa: F401

if __name__ == "__main__":
    from almp.app import main as _run
    sys.exit(_run(sys.argv))
