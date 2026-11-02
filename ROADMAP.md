# ALMP Roadmap

ALMP is free software for people who just want to press play. This roadmap shows where the project is heading.
Plans can change - open an issue or a discussion if something matters to you.

## Done (v8.0.0)
- [x] Starts clean: no remembered position or playlist, lower memory use
- [x] Save playlist as M3U, sleep timer (pause or close), high-contrast theme
- [x] Delete to the Recycle Bin; delete works in fullscreen without leaving it
- [x] Previous goes back; first-run welcome screen
- [x] Tested with a 10,000-file library and a 3,500-song real library
- [x] Build and package scripts; GitHub Actions workflow (run by hand) with a pinned libmpv

## Done (v7.2.0)
- [x] Modern dark interface, floating fullscreen controls, playlist search
- [x] Large playlists load in batches (window stays responsive)
- [x] Set-as-default script, single-window mode, remembered settings
- [x] GPL-3.0 licence, third-party notices, honest documentation

## Next: v8.1 - trust and polish
- [ ] Code-signed Windows releases (free signing for open-source projects, see SIGNING.md)
- [ ] First successful GitHub Actions build, then build releases only from Actions
- [ ] Decide on the "Remember Playlist" option (make it work as a real choice, or remove it)
- [ ] Tidy `main.py` (split into a few files, log errors to a file instead of hiding them)
- [ ] Public benchmark results (use `tools/make_test_library.py`), including a 100,000-file playlist
- [ ] A screenshot of a playing video and short how-to for the README

## Then: v8.2+
- [ ] Virtual playlist (100,000+ items without slowing down)
- [ ] Subtitle and audio-track improvements
- [ ] Re-order playlists

## Later
- [ ] Easier installation: winget, Microsoft Store, optional installer
- [ ] Accessibility: large-text mode, screen-reader labels
- [ ] Translations by the community
- [ ] Switch to PySide6 (LGPL) so the project can be offered under more permissive terms

## Principles
Free forever. No ads, no tracking, no accounts. Works offline. Simple first.
