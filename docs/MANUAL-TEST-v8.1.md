# ALMP v8.1 - manual test checklist (Windows)

The automatic tests run on Linux and Windows with real Qt but **without a screen, without sound and
without the real mpv** (it is replaced by a stand-in). Everything that needs a real Windows desktop,
real media files or `mpv-2.dll` must be checked by hand on the built `ALMP.exe`. Tick each line on the
PC you test; note the Windows version, screen size and the zip's SHA-256 at the top of your notes.

Use your own test files (not private family media) or a library made with
`python tools/make_test_library.py D:\ALMP-test 100000 --source "D:\some-short-song.mp3"`
(hard links, so every file really plays and takes almost no disk space).

Legend: **[ ]** to do. "Expected" says what must happen. If something else happens, copy
`%LOCALAPPDATA%\ALMP\almp.log` (Settings > About ALMP > Open log folder) into the bug report.

## 0. Build and start
- [ ] `Build-ALMP.bat` then `Package-ALMP.bat` finish without errors (check `build.log`). The zip contains
      `ALMP.exe`, `LICENSE`, `THIRD-PARTY-NOTICES.txt`, `LICENSES\`, both `.bat` files and `README.txt`.
- [ ] Or: run the **Build ALMP** workflow on `v8.1-dev` and use its artifact (preferred for releases).
- [ ] Extract to `Documents\ALMP-test`, double-click `ALMP.exe`. Expected: the welcome screen, window title
      "Alexbed Light Media Player 8.1.0", "Version 8.1.0" under the buttons.
- [ ] First start on a PC that had v8.0.1: volume, shuffle, "Remove played", high contrast and interface size are
      kept. On a PC that never had ALMP: "Remove played" is **off**.
- [ ] Rename `runtime\mpv-2.dll` for a moment: ALMP shows the "playback engine could not be loaded" message. Put it back.

## 1. Big playlists (the main v8.1 change)
- [ ] Drag a folder with 100,000 files onto the window. Expected: the first track starts within about
      a second; the status line shows "Adding files... N in the list so far" and the count pill grows;
      the window can be moved, scrolled and clicked the whole time; "Stop adding" is shown.
- [ ] Press **Stop adding** halfway. Expected: adding stops, what was found stays in the list.
- [ ] Scroll the list fast with the mouse wheel and the scroll bar (no stutter). Press End / Home in the list.
- [ ] Type in the search box (for example `love`, then `love n`). Expected: the list filters within a
      moment after you stop typing, the pill shows "N of 100,000", Enter plays the first match,
      Down moves into the list, Esc clears the search.
- [ ] Right-click > Sort the playlist > By name. Expected: "Sorting the playlist..." then "Playlist
      sorted by name." with the window responsive meanwhile; "Track 2" is before "Track 10".
- [ ] Same folder from a USB stick and (if you have one) a network share: first track still starts quickly.
- [ ] Close ALMP while a huge folder is still being added. Expected: it closes without a crash message.
- [ ] Note the memory use in Task Manager with 100,000 files (for the release notes).

## 2. Playlist right-click menu and keys
- [ ] Right-click a track: Play, Play next, Move up / Move down, Remove from list, Show in folder,
      Copy file path, Delete file..., Sort, Add files, Add folder, Clear.
- [ ] **Play next** on two tracks: they show `[next]` / `[next 2]` and play in that order after the current
      track ends (also with Shuffle on), then normal order/shuffle continues.
- [ ] **Show in folder** opens Explorer with the file selected. **Copy file path** puts the path in the clipboard.
- [ ] **Move up / Move down** and drag-and-drop inside the list move the item; the playing track keeps playing.
      While a search is active, moving is greyed out.
- [ ] Select a track and press **Delete**: removed from the list (file kept). **Shift+Delete**: the delete question.
- [ ] Menu key (or Shift+F10) on a selected track opens the same menu.
- [ ] Right-click on the **video** (or album art): Play/Pause, Next, Previous, audio/subtitles, video size,
      fullscreen, Settings, Help. [L: mpv draws into its own child window; confirm right-click reaches ALMP.]
- [ ] Explorer files dropped on the playlist area are added (not ignored).

## 3. Safe delete (must still work exactly as in 8.0.1)
- [ ] File on the C: drive: "Send this file to the Recycle Bin?"; Yes -> the file is in the Recycle Bin.
- [ ] File on a USB stick: "This drive has no Recycle Bin... deleted PERMANENTLY"; No keeps it; Yes deletes it.
- [ ] Delete the file that is playing: playback moves on to the track that took its place; no "file in use" error.
- [ ] In fullscreen: the delete question is on top and the mouse pointer is visible.

## 4. Settings (gear button, or Ctrl+,)
- [ ] High contrast: everything turns black/white/yellow at once, including the status line, time, volume %,
      the count pill, the playlist title, the Remove button and the **welcome screen** (black, yellow bars).
- [ ] Interface size 150%, **Apply now**: ALMP closes and reopens at 150% (playlist not kept, as the note says).
      Repeat with 200% and back to 100%.
- [ ] Video size Fit / Fill / Stretch changes the picture and is remembered next start (A still cycles it).
- [ ] Remove played: same state as the box under the playlist; greyed out while Loop All is on.
- [ ] Keep the playback speed: set 1.25x, next track is still 1.25x; untick it, next track is 1.0x.
      After restarting ALMP the speed is 1.0x.
- [ ] Even out loud and quiet parts: on a file with quiet and loud parts the difference is smaller.
      [L: needs the real mpv/FFmpeg `dynaudnorm` filter.] The status line must not say it failed.
- [ ] Allow volume up to 150%: the slider goes to 150 and it is louder above 100. Untick: back to max 100.
- [ ] Subtitle size Large/Huge and "Dark box behind subtitles" change the subtitles of a film with an .srt.
- [ ] Continue long files: tick it, play a 30-minute file to minute 10, close ALMP, open the file again:
      "continuing at 10:..". A 5-minute song always starts at 0. Untick: the file
      `%APPDATA%\ALMP\positions.json` is deleted. **Never** is the playlist restored.
- [ ] Run at Startup: tick, sign out and in: ALMP starts. Untick: it does not.

## 5. Make ALMP the default player / folder menu (current user only)
- [ ] Settings > **Make ALMP my default player...**: the message explains the last step, then Windows'
      Default apps page opens on ALMP. After "Set default", double-clicking an .mp3 opens ALMP.
- [ ] Select 20 files in Explorer, press Enter: all 20 are added to one ALMP window.
- [ ] Tick **"Play with ALMP"** for folders. Right-click a music folder in Explorer: "Play with ALMP"
      (Windows 11: under "Show more options"). It opens ALMP and starts the first track of that folder,
      also when ALMP is already open with another playlist.
- [ ] Untick it: the menu entry is gone. **Remove ALMP from Default apps**: ALMP disappears from Default apps.
- [ ] `Remove-ALMP-Defaults.bat` still removes everything, including the folder entry.

## 6. Media keys and Windows media controls (SMTC)
- [ ] Play a song, then click on the desktop or another program (ALMP in the background). Press the keyboard's
      **Play/Pause**, **Next**, **Previous** keys. Expected: ALMP reacts (once per press, not twice).
- [ ] Press a volume key: the Windows volume pop-up shows the track name and Play/Pause/Next/Previous
      buttons; they work. Windows 11: also in Quick Settings. The lock screen (Win+L) shows the track.
- [ ] With ALMP in front, Play/Pause toggles once (not twice).
- [ ] Play a video in a browser after ALMP: Windows gives the keys to the browser (normal Windows behaviour).
- [ ] Settings > untick "Media keys work while ALMP is in the background": the pop-up controls disappear;
      the keys still work while ALMP is the active window.
- [ ] If ALMP ever crashes right at start after this feature: start it again. Expected: it starts, the
      feature is switched off, and almp.log says why.

## 7. Accessibility and the control bar
- [ ] 1366x768 laptop (or set Windows display to 1366x768) at ALMP 150% and 200%: every control is visible
      (the bar switches to icons and two rows when narrow); nothing is cut off. Window fits the screen.
- [ ] Windows display scaling 125%/150% + ALMP 100%: same check.
- [ ] Tab through the whole window: every button, box and slider gets the yellow (HC: cyan) frame.
      **Space on a focused button presses that button** (it does not toggle playback).
- [ ] With the playlist focused: Up/Down/Page Up/Page Down move in the list; Enter plays; Space pauses;
      Left/Right seek.
- [ ] With the volume slider focused: arrows change the volume. With the speed box focused: arrows change speed.
- [ ] With the video focused (click it once): Space, arrows, Page Up/Down, M, A, S, L, F, P work as in F1.
- [ ] Narrator (Win+Ctrl+Enter): buttons are read with names ("Previous track", "Sleep timer, off",
      "High contrast theme, on"...), the playlist rows are read, "Playing: ..." is announced
      [L: announcements need Qt 6.8 or newer].
- [ ] F1 opens Help ("How do I..." and "Keyboard"). Help > About shows version 8.1.0, the licence, the third-party
      notices, **Open log folder** opens `%LOCALAPPDATA%\ALMP`.

## 8. Sleep timer
- [ ] 5 minutes: the clock turns blue; during the last minute the sound fades out; then playback pauses and
      the volume is back to normal for the next Play.
- [ ] "+15 minutes" appears in the menu while a timer runs and adds 15 minutes.
- [ ] "At the end of this track": playback stops when the track ends; Play starts the next track.
- [ ] "When time is up: Close ALMP" closes ALMP.

## 9. Regressions from 8.0.1 to re-check
- [ ] Loop Off / One / All behave as in 8.0.1, and Loop is Off after a restart.
- [ ] Fullscreen: controls float and hide after 3 s, P opens the drawer, typing in the drawer's search keeps it
      open, Esc leaves fullscreen, the pointer is visible over dialogs.
- [ ] Album art shows for MP3/FLAC/M4A. Snapshots (S) go to Pictures.
- [ ] Save playlist as M3U and open it again with Add Media > Open a playlist file.
- [ ] Opening a file from Explorer while ALMP is still starting: the file arrives and plays.
- [ ] ALMP never connects to the internet (for example with the network cable unplugged, or watch it in a firewall).
