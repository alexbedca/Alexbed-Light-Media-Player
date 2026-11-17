# Alexbed Light Media Player (ALMP): project notes for Claude

## What this project is
A simple, free, offline media player for Windows built on mpv (libmpv): big clear buttons, dark theme,
high-contrast theme, huge playlists (100,000+ files with a streaming scan and virtual list), search, sleep timer,
media keys, accessibility, TV-size start screen in fullscreen. Portable zip, no installer, no telemetry.

- **Status:** v8.2.4 released 2026-11-17 (Latest; subtitles on/off setting, all files in a Data folder next to
  ALMP.exe + log auto-clean, All/Video/Audio filter, Ctrl+S saves what is shown, format text, gapless, exclusive
  audio, upscaling levels, Releases link in About, fullscreen music controls fix). v8.2.3 released 2026-11-14. Public repo https://github.com/alexbedca/Alexbed-Light-Media-Player
  (GPL-3.0-or-later). Release asset: `ALMP-vX.Y.Z-Portable.zip` + SHA-256. Not code-signed (SignPath declined
  for now; see `SIGNING.md`).
- **Next:** see `ROADMAP.md` (open items: bigger fullscreen drawer/text for TVs, winget/Scoop submission from
  `packaging/`).
- **Read first:** `README.md` (features, performance numbers, build), `ROADMAP.md`, `docs/release-notes/`,
  `docs/MANUAL-TEST-v8.1.md` (manual Windows test checklist).

## Stack and layout
Python 3.10+ (CI uses 3.13), PyQt6, python-mpv + `runtime\mpv-2.dll`, mutagen. Built with **Nuitka** (standalone).
```
main.py                   only starts the app
almp/__init__.py          __version__ (single source of the version; plain X.Y.Z)
almp/                     logic.py, store.py, naturalsort.py, settings.py, media.py, scanner.py (plain, tested logic);
                          playlist_model.py, player.py (mpv options), ui.py / widgets.py / dialogs.py (window),
                          platform_win.py + smtc.py (Windows-only calls, all guarded), ipc.py (single instance)
tests/                    pytest; Qt window tests run offscreen with mpv replaced by a stand-in
tools/                    bench_playlist.py (public benchmark), bench_startup.py (open-time benchmark),
                          make_test_library.py, get_version.py
packaging/                winget + Scoop drafts (not submitted)
runtime/mpv-2.dll         libmpv, NOT committed (git-ignored); needed to run and build
Build-ALMP.bat            Nuitka build -> main.dist\ (log: build.log)
Package-ALMP.bat          -> release\ALMP-vX.Y.Z-Portable.zip + .sha256.txt (with LICENSES\)
Set-/Remove-ALMP-Defaults.bat  shipped in the zip: default-player registration / uninstall (HKCU only)
.github/workflows/ci.yml   ruff + tests on Ubuntu and Windows + short benchmark, every push/PR
.github/workflows/build.yml  manual (workflow_dispatch) portable build with pinned, hash-checked libmpv
```

## Tools for this project
**Project commands**
- Run: `python main.py` (needs `runtime\mpv-2.dll`).
- Tests and lint: `python -m pytest tests` and `ruff check .` (config in `ruff.toml`).
- Benchmark: `python tools/bench_playlist.py --sizes 100000,250000 --disk-sizes 100000 --json my-pc.json`.
- Open time: `python tools/bench_startup.py <video> [--exe main.dist\ALMP.exe] [--runs 5]` (close ALMP first;
  reads the "Start-up: window shown / playing after" lines in `%LOCALAPPDATA%\ALMP\almp.log`).
- Build: `pip install nuitka`, then `Build-ALMP.bat`, then `Package-ALMP.bat`.

**Skills**
- Release: use the claude.ai library skill **`anthropic-skills:almp-release`** (version bump, notes, build, merge,
  GitHub release, cleanup). There is no separate project release skill, to avoid two versions of the same steps.
- Personal skill `alexbed-github-publish` for repo-wide conventions.

**Account tools this project uses** (full list in `~/.claude/CLAUDE.md`)
- `git push` via Git Credential Manager. The `gh` token has **no `workflow` scope**: any change under
  `.github/workflows/` must be pushed with plain `git push`, not through gh.
- `gh` for PRs, releases and CI (`gh run watch`). Work is done on a branch (`release/vX.Y.Z`, `v8.2-tv-mode`, …)
  and merged to `main` through a PR.
- Claude in Chrome for GitHub web-only settings (social preview).

## Decisions and gotchas
- **Fonts and start-up speed (v8.2.2):** Alexander's PC has 9,223 fonts. Qt searches *all* installed fonts for
  (1) its DirectWrite font list, (2) a weight the family lacks, (3) a character the font lacks; each cost
  5-70 s there. So: ALMP sets `QT_QPA_PLATFORM=windows:fontengine=gdi` (unless the user set it), semi-bold uses
  `SEMIBOLD` in `theme.py` ("Segoe UI Semibold" by name, never bare `font-weight: 600` on Windows), and window
  text must not use symbols Segoe UI lacks (no "✓"; use checkable actions). Re-measure with
  `tools/bench_startup.py` after UI/font changes; target: window ~1 s, video playing ~1.5-2 s.
- **Fullscreen freeze (v8.2.3):** Qt 6.12's Windows plugin redraws a hidden title bar
  (`updateCustomTitlebar`) on every maximize/fullscreen in Segoe UI + Segoe Fluent Icons at *Thin* weight;
  with GDI fonts that searched all fonts (6.4 s, once per run). `almp/titlefonts.py` registers in-memory Thin
  copies of the PC's own fonts right after `window.show()` (must be after Qt loaded the family). Dead ends,
  measured: font substitutions, stand-in fonts for missing fallbacks, Qt's emoji/fallback-family APIs,
  `darkmode=` (moves the cost to start-up), `fontengine=freetype` (25 s).
- **Still slow (known, not fixed):** names with emoji or Chinese/Japanese/Korean text freeze the controls
  7-9 s the first time one is drawn (Qt's `populateFamilyAliases` loads every family before fallbacks).
- Debugging Qt freezes: sample the GUI thread's native stack from a second process (dbghelp
  StackWalk64, GIL blocks an in-process sampler) and name Qt6Gui offsets from its export table.
- Known quirk (not fixed): right after ALMP is force-killed, a new start within ~1-2 s can find the stale
  single-instance lock and hand its file to nothing (normal close is fine).
- Performance claims must match `tools/bench_playlist.py` runs; the README states where targets were **not** met
  (window stall 61–148 ms during a 100,000-file scan). Keep that honesty when updating numbers.
- The playlist is a one-column table, not `QListView` (measured ~30× faster to append rows).
- ALMP never remembers the last playlist (fast start); Loop choice is not remembered; "Remove played" is off for
  new installs. These are deliberate.
- Delete on removable/network drives is permanent (no Recycle Bin) and must keep its clear warning.
- `release/`, `main.build/`, `main.dist/`, `*.log`, `*.zip` and `runtime/` are git-ignored.
- Old single-file versions (`main-V7.2*.py`, `main-V7.7.0-DeepSeek.py`, `main-usabke.py`) sit one folder up in
  the parent folder (`..\`) and early builds in `..\..\Media-Player` and `..\..\version Control`.
  They are history only; all work happens in this repo.
