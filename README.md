# Alexbed Light Media Player (ALMP)

A simple, free media player for Windows, built on the [mpv](https://mpv.io) playback engine.
ALMP is made for people who just want to press play: big clear buttons, a dark modern look,
and no accounts, ads or tracking.

![ALMP Preview](images/screenshot-v8-welcome.png)

**Version:** 8.0.0 &nbsp;|&nbsp; **Author:** Alexander Bediako &nbsp;|&nbsp; **Licence:** [GPL-3.0-or-later](LICENSE)

ALMP is free and will stay free. It is built to help people who need an easy, no-cost player,
and it is not a commercial product.

---

## Features

- **Plays almost anything.** Audio, video and playlists (`.m3u`, `.m3u8`, `.pls`), powered by mpv and FFmpeg.
- **Starts clean.** ALMP does not remember the last playlist or position, so it opens fast and stays light.
- **Large playlists.** Folders load in batches so the window stays responsive. A search box filters the list as you type (tested with a 10,000-file library).
- **Save your playlist** as an `.m3u8` file (*Add Media > Save Playlist as M3U*) and load it again later.
- **Sleep timer.** Click the clock button on the control bar, choose 5 minutes to 2 hours, then pick what happens: pause playback, or close ALMP. The clock turns blue while a timer is running.
- **High-contrast theme** (black, white and yellow) for easier reading. *Add Media > High Contrast Theme*.
- **Drag and drop.** Drop files or folders on the window to add them to the playlist.
- **Delete goes to the Recycle Bin**, so a mistake can be undone.
- **Double-click to play.** Run `Set-ALMP-Defaults.bat` once to register ALMP with Windows, then choose it in *Default apps*.
- **Single window.** Opening another file while ALMP is running sends it to the same window.
- **Shuffle, loop and "remove played".**
- **Album art** from embedded tags (MP3, FLAC, M4A).
- **Hardware decoding** when your graphics card supports it (mpv `hwdec=auto`).
- **Fullscreen controls that float over the video**, hiding after 3 seconds (they stay up while a menu is open).
- **Audio tracks and subtitles.** The button next to the speed box lists audio tracks, subtitles, loads a subtitle file and takes snapshots (`S`).
- **Video size modes.** Press `A` to cycle Fit, Fill (crop) and Stretch.
- **Interface size.** Choose 100% to 200% in the playlist panel (applies the next time you open ALMP).
- **Remembers your settings** (volume, shuffle, loop, remove played, interface size, high contrast).
- **Windows media keys** (play/pause, next, previous) work.
- **Portable and offline.** No installer, no admin rights. ALMP does not connect to the internet.

## Download and run (Windows)

1. Open the [Releases](../../releases) page and download the latest `.zip`.
2. Extract the whole folder (do not run ALMP from inside the zip).
3. Double-click `ALMP.exe`.

> **Windows SmartScreen:** ALMP is not code-signed yet (see [SIGNING.md](SIGNING.md)), so Windows may show "Windows protected your PC".
> Click **More info** then **Run anyway**. To check your download, compare its SHA-256 with the value on the release page:
> `certutil -hashfile ALMP-v8.0.0-Portable.zip SHA256`

### Make ALMP your default player

1. Copy the ALMP folder to your computer (for example, `Documents`), not a USB stick.
2. Double-click `Set-ALMP-Defaults.bat` inside the ALMP folder and press **Y**.
3. On the Windows page that opens, press **Set default** (or pick ALMP for `.mp3`, `.mp4`, and so on).

Windows does not allow any program to change your defaults silently, so this last click must be yours.
To undo it, run `Remove-ALMP-Defaults.bat`.

## Keyboard shortcuts

| Key | Action |
|---|---|
| Space | Play / pause |
| F, Esc | Fullscreen / leave fullscreen |
| Left / Right | Seek 5 seconds |
| Up / Down | Volume |
| Page Up / Page Down | Previous / next track |
| M | Mute |
| A | Video size: Fit, Fill, Stretch |
| P | Show / hide the playlist drawer (fullscreen) |
| Ctrl+F | Search the playlist |
| F1 | Show the shortcut help |
| Double-click video | Fullscreen |

## Run from source

You need Python 3.10 or newer (official builds use Python 3.13 or 3.14) and the mpv library (`libmpv`).

```bash
git clone https://github.com/alexbedca/Alexbed-Light-Media-Player.git
cd Alexbed-Light-Media-Player
python -m venv venv
venv\Scripts\activate          # Linux: source venv/bin/activate
pip install -r requirements.txt
python main.py
```

- **Windows:** put `mpv-2.dll` (a libmpv build) in a folder named `runtime` next to `main.py`.
- **Linux (experimental, tested on Ubuntu under WSL only):** `sudo apt install libmpv2 libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-xkb1`. ALMP uses X11 on Linux because mpv embeds into the window that way.

### Build the portable app

`Build-ALMP.bat` runs the same command as below and writes `build.log`; `Package-ALMP.bat` then makes the zip and its SHA-256 file.

```bat
pip install nuitka
python -m nuitka --standalone --enable-plugin=pyqt6 --windows-console-mode=disable --lto=yes ^
  --windows-icon-from-ico=icon.ico --include-data-file=icon.ico=icon.ico ^
  --include-data-file=icon.png=icon.png --include-data-file=runtime/mpv-2.dll=runtime/mpv-2.dll ^
  --output-filename=ALMP.exe main.py
```

## Contributing

Bug reports, ideas and pull requests are welcome. Please open an issue first for larger changes.
By contributing you agree that your work is released under the same licence as the project.

## Licence

ALMP is free software, released under the **GNU General Public License v3.0 or later**.
You may use, study, share and change it. See [LICENSE](LICENSE).

ALMP is built on other free software (PyQt6, Qt, mpv, FFmpeg, mutagen and others).
Their licences are listed in [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt).

## Code signing policy

ALMP releases are not code-signed yet. We plan to apply to the [SignPath Foundation](https://signpath.org)
free programme for open-source projects once builds run on GitHub Actions. Until then, verify each download with
its published SHA-256. ALMP works fully offline and sends no data anywhere. Details: [SIGNING.md](SIGNING.md).

## Community & Roadmap
- See [ROADMAP.md](ROADMAP.md) for what is coming next.
- See [CONTRIBUTING.md](CONTRIBUTING.md) if you want to help.
- See [SECURITY.md](SECURITY.md) to report a security issue.
