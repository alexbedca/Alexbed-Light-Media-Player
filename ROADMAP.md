# ALMP Roadmap

ALMP is free software for people who just want to press play. This roadmap shows where the project is heading.
Plans can change - open an issue or a discussion if something matters to you.

## v8.1 (in development on `v8.1-dev`) - big playlists, settings, accessibility
- [x] Virtual playlist (one list model, no item per file) and a streaming folder scan: the first track plays at once
- [x] Search over a prepared index; natural sort ("2" before "10"); Play next; Move up/down; sort by name/folder
- [x] Settings window (gear): contrast, interface size with "Apply now", video size, remove played (Off for new
      installs), speed kept for the session, volume normaliser and 150% boost, subtitle size and box, media keys,
      Run at Startup, default player and "Play with ALMP" on folders
- [x] High contrast for every label and the welcome screen; control bar that fits 150-200% on small screens
      (icons, two rows); accessible names; Space/arrows go to the focused control first
- [x] Playlist and video right-click menus; Help and About (version, licence, log folder); version in the title
- [x] Windows media controls (media keys in the background, title in the volume pop-up), with a safe fallback
- [x] Sleep timer: end of track, fade-out, +15 min. Optional resume for files of 20+ minutes (off by default)
- [x] `main.py` split into the `almp/` package; ruff in CI; tests run with real Qt on Linux and Windows
- [x] Public benchmark (`tools/bench_playlist.py`) with measured numbers in the README
- [ ] Manual Windows test of the built exe (docs/MANUAL-TEST-v8.1.md), then release from Actions
- [ ] winget / Scoop submission (drafts in `packaging/`)

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

## Next: v8.2 - trust and reach
- [ ] Code signing: the free SignPath Foundation application was declined for now (not enough public visibility yet).
      Grow the project's visibility and reapply later, or choose another route (see SIGNING.md)
- [ ] Build releases only from Actions; attest builds (GitHub artifact attestations)
- [ ] Host a copy of the exact libmpv/FFmpeg source next to each release (today: a written offer, see THIRD-PARTY-NOTICES.txt)
- [ ] Microsoft Store (MSIX) listing; submit the winget and Scoop manifests
- [ ] Translations: route all texts through one function, then community languages
- [ ] Album art loaded off the window thread (slow USB/network drives)
- [ ] "Keep on top" and a simple layout preset

## Later
- [ ] Optional installer (after signing)
- [ ] Translations by the community
- [ ] Switch to PySide6 (LGPL) so the project can be offered under more permissive terms

## Principles
Free forever. No ads, no tracking, no accounts. Works offline. Simple first.
