# ALMP Roadmap

ALMP is free software for people who just want to press play. This roadmap shows where the project is heading.
Plans can change - open an issue or a discussion if something matters to you.

## Done (v7.2.0)
- [x] Modern dark interface, floating fullscreen controls, playlist search
- [x] Large playlists load in batches (window stays responsive)
- [x] Set-as-default script, single-window mode, remembered settings
- [x] GPL-3.0 licence, third-party notices, honest documentation

## Next: v7.2.x - polish
- [ ] Delete to the Recycle Bin (instead of permanent delete)
- [ ] Shuffle without repeats; "Previous" goes back to the last track played
- [ ] Remember the last playlist and the position in each file
- [ ] First-run welcome screen (Open files / Open folder / Make default)

## Then: v7.3 - proven at scale
- [ ] Virtual playlist (handles 100,000+ items without slowing down)
- [ ] Public benchmark results (use `tools/make_test_library.py`)
- [ ] Automatic builds on GitHub Actions
- [ ] Code-signed Windows releases (free signing for open-source projects)
- [ ] Subtitle and audio-track menu
- [ ] Save / load / re-order playlists

## Later
- [ ] Easier installation: winget, Microsoft Store, optional installer
- [ ] Accessibility: high-contrast theme, large-text mode, screen-reader labels
- [ ] Translations by the community
- [ ] Switch to PySide6 (LGPL) so the project can be offered under more permissive terms

## Principles
Free forever. No ads, no tracking, no accounts. Works offline. Simple first.
