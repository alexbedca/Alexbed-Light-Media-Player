# ALMP v8.0.0

A clean, lighter and more useful release.

## New
- **Starts clean.** ALMP no longer remembers the last playlist or position. It opens fast and uses less memory.
- **Save Playlist as M3U** (Add Media menu), plus loading `.m3u`/`.m3u8` files back in.
- **Sleep timer** with its own clock button on the control bar (5 min to 2 h). Choose what happens when time is up: pause playback, or close ALMP.
- **High-contrast theme** (black, white, yellow).
- **Delete goes to the Recycle Bin.**
- Open-file dialog lists playlists too; folders and files passed on the command line are sent to the running window.

## Improved
- Lower memory use (about 270 MB while playing in our test, down from about 400 MB).
- A 10,000-file library loads and searches without freezing the window.
- In fullscreen the controls and cursor now stay visible while the audio/subtitle menu is open.
- Fixed black bands around the welcome screen.

## Notes
- ALMP is not code-signed yet, so Windows SmartScreen may ask for confirmation (More info > Run anyway).
- Built with Nuitka on Python 3.15.2 for this build; future official builds will use Python 3.13/3.14 on GitHub Actions.
- **SHA-256 of ALMP-v8.0.0-Portable.zip:** `CF2E413DF31EB25103570BD87470D729D2540C639270B28CB460EC767DF3CC0B`
