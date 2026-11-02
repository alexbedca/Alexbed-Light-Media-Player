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
"""ALMP package.

Layout (pure logic first, so it can be tested without a screen):
  logic.py           loop / shuffle / queue / sleep-timer / resume decisions (no Qt)
  media.py           file types, M3U/PLS reading and writing (no Qt)
  naturalsort.py     "Track 2" before "Track 10" (no Qt)
  settings.py        settings.json: defaults, migration, saving (no Qt)
  store.py           the playlist data and its search index (no Qt)
  scanner.py         folder walk that streams results in batches (Qt only for the thread)
  playlist_model.py  virtual list model over the store (Qt)
  player.py          mpv options and helpers (no window code)
  platform_win.py    Windows-only calls, every one guarded (Recycle Bin, registry, startup)
  smtc.py            Windows media controls (media keys in the background), guarded
  theme.py, widgets.py, dialogs.py, ui.py, app.py   the window
"""

__version__ = "8.1.0"

APP_TITLE = "Alexbed Light Media Player"
APP_SHORT = "ALMP"
