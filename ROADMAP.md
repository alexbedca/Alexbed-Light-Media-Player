# ALMP Roadmap

ALMP is free software for people who just want to press play. This roadmap shows where the project is heading.
Plans can change - open an issue or a discussion if something matters to you.

## Done (v8.0.1) - safety and reliability
- [x] Delete warns clearly on drives without a Recycle Bin (USB sticks, memory cards, network drives)
- [x] Removed the "Remember Playlist" checkbox that did not work; ALMP always starts clean and removes old v7 history files
- [x] Errors are written to a local log file (`%LOCALAPPDATA%\ALMP\almp.log`) instead of closing ALMP
- [x] Several files opened from Explorer at once all reach the same window; opening a file adds it instead of wiping the playlist
- [x] Click-to-seek, Enter plays the selected item, visible keyboard focus, fullscreen pointer stays visible over dialogs
- [x] Old "ANSI" `.m3u` playlists load correctly; licence texts included in the zip
- [x] Build version comes from `main.py`; workflow inputs pinned
- [x] High contrast on/off button on the control bar; three-way loop (Off / One / All, key `L`), not remembered between runs

## Done (v8.0.0)
- [x] Starts clean: no remembered position or playlist, lower memory use
- [x] Save playlist as M3U, sleep timer (pause or close), high-contrast theme
- [x] Delete to the Recycle Bin (on drives without one, a warning was added in v8.0.1); delete works in fullscreen without leaving it
- [x] Previous goes back; first-run welcome screen
- [x] Tested with a 10,000-file library and a 3,500-song real library
- [x] Build and package scripts; GitHub Actions workflow (run by hand) with a pinned libmpv

## Done (v7.2.0)
- [x] Modern dark interface, floating fullscreen controls, playlist search
- [x] Large playlists load in batches (window stays responsive)
- [x] Set-as-default script, single-window mode, remembered settings
- [x] GPL-3.0 licence, third-party notices, honest documentation

## Next: v8.1 - trust and polish
- [ ] Code signing: the free SignPath Foundation application was declined for now (not enough public visibility yet).
      Grow the project's visibility and reapply later, or choose another route (see SIGNING.md)
- [ ] First successful GitHub Actions build, then build releases only from Actions
- [ ] Host a copy of the exact libmpv/FFmpeg source next to each release (today: a written offer, see THIRD-PARTY-NOTICES.txt)
- [ ] Tidy `main.py` (split into a few files; turn the remaining silent error handlers into log entries)
- [ ] High-contrast theme for every label and the welcome screen; interface sizes that always fit small laptop screens
- [ ] Public benchmark results (use `tools/make_test_library.py`), including a 100,000-file playlist
- [ ] A screenshot of a playing video and short how-to for the README

## Then: v8.2+
- [ ] Virtual playlist (100,000+ items without slowing down)
- [ ] Subtitle and audio-track improvements
- [ ] Re-order playlists: drag-and-drop is already switched on in the playlist; test it with shuffle, search and
      "Remove played" before it is announced as a feature

## Later
- [ ] Easier installation: winget, Microsoft Store, optional installer
- [ ] Accessibility: large-text mode, screen-reader labels
- [ ] Translations by the community
- [ ] Switch to PySide6 (LGPL) so the project can be offered under more permissive terms

## Principles
Free forever. No ads, no tracking, no accounts. Works offline. Simple first.
