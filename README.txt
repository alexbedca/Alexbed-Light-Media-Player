====================================================================
                  ALEXBED LIGHT MEDIA PLAYER (ALMP)
====================================================================
Version:       v8.2.0
Developer:     Alexander Bediako
Contact:       alexbedgh@gmail.com
Website:       https://github.com/alexbedca/Alexbed-Light-Media-Player
License:       GNU General Public License v3 or later (Free Software)

ALMP is free and will stay free. It is built to help people who need
an easy, no-cost media player.

--------------------------------------------------------------------
1. QUICK START (NO INSTALLATION REQUIRED)
--------------------------------------------------------------------
This is a portable application. It does not need Python, VLC or any
other software, and it does not need administrator rights.

1. Extract the ZIP file to a folder on your PC (for example in
   Documents). Do not run it from inside the ZIP.
2. Open the extracted "ALMP-v8.2.0-Portable" folder.
3. Double-click "ALMP.exe".
4. Drag and drop a folder (or files) into the window. If the playlist
   is empty, the first file starts playing automatically.

If Windows shows "Windows protected your PC" (SmartScreen), click
"More info" and then "Run anyway". ALMP is not code-signed, which is
why Windows asks. This warning appears for most new free programs that
are not signed; it does not mean a virus was found. Only download ALMP
from https://github.com/alexbedca/Alexbed-Light-Media-Player/releases

To check that your download is the real one, compare its SHA-256
checksum with the one on the release page. Open PowerShell in the
folder with the zip and type:
    Get-FileHash .\ALMP-v8.2.0-Portable.zip -Algorithm SHA256
The long code it prints must be exactly the same as on the release
page (capital or small letters do not matter). If it is different, do
not run the file.

--------------------------------------------------------------------
2. HOW TO SET AS YOUR DEFAULT MEDIA PLAYER
--------------------------------------------------------------------
Windows does not allow any program to change your default player
silently, so you must confirm the choice yourself.

1. Make sure the ALMP folder is on your computer (not on a USB stick).
2. In ALMP, click the gear button (Settings) and then
   "Make ALMP my default player...".
   (Or: double-click "Set-ALMP-Defaults.bat" and press "Y".)
3. The Windows "Default apps" page opens on ALMP.
   - Windows 11: click "Set default" at the top, or click each type
     (.mp3, .mp4 ...) and choose ALMP.
   - Windows 10: click "Set this program as default".

In the same Settings window you can add "Play with ALMP" to the menu
you get when you right-click a folder in Explorer.

If you move the ALMP folder later, do this again.

To undo this (or to uninstall ALMP), use "Remove ALMP from Default
apps" in Settings, or run "Remove-ALMP-Defaults.bat". The .bat file
removes ALMP from "Open with" and "Default apps", the folder menu
entry and "Run at Startup", and asks whether to delete ALMP's
settings and log files. Then delete the ALMP folder.

--------------------------------------------------------------------
3. DESKTOP SHORTCUT (AND FIXING A BLANK ICON)
--------------------------------------------------------------------
1. Right-click "ALMP.exe" > "Show more options" > "Create shortcut".
2. Move the shortcut to your Desktop.
3. If the icon is blank: right-click the shortcut > Properties >
   "Change Icon..." > Browse > pick "icon.ico" in the ALMP folder.

--------------------------------------------------------------------
4. FEATURES
--------------------------------------------------------------------
- Plays most audio and video files, and .m3u / .m3u8 / .pls playlists.
- Very large playlists: the first track starts at once while a big
  folder is still being added; the list, search and scrolling stay
  quick with 100,000+ files. "Stop adding" stops a long scan.
- Search box: type to filter the playlist by file or folder name
  (Ctrl+F). Enter plays the first match.
- Right-click a track: Play, Play next, Move up / down, Remove from
  list, Show in folder, Copy file path, Delete file, Sort.
- Sort the playlist by name ("Track 2" before "Track 10"), by folder,
  or reverse it.
- Single window: files you open from Explorer while ALMP is running
  are added to the playlist in the same window, and the first one
  starts playing. The playlist is not wiped.
- Drag and drop files or folders to add them to the playlist.
- Starts clean: ALMP does not remember the last playlist.
- Save Playlist as M3U and open a playlist file: "+ Add Media" menu.
- Sleep timer (clock button): 5 minutes to 2 hours, or "At the end of
  this track". The sound fades out during the last minute. "+15
  minutes" while it runs. When time is up: Pause, or Close ALMP.
- Settings (gear button, Ctrl+,): high contrast, interface size,
  video size, remove played, keep the playback speed, even out loud
  and quiet parts, volume up to 150%, subtitle size and dark box,
  media keys in the background, Run at Startup, default player.
- High Contrast Theme (black, white and yellow): the half-filled
  circle button, or Settings. Applies at once, everywhere.
- Shuffle, "Remove played" (off for new installs) and Loop:
    Loop: Off ... playback stops after the last track.
    Loop: One ... the track that is playing now repeats.
    Loop: All ... the whole playlist starts again after the last
                  track (with Shuffle: every track once per round).
  Loop All switches "Remove played" off (unticked and greyed out).
  Loop is always Off when ALMP starts.
- Playback speed 0.5x to 2x; it stays for the next tracks until you
  close ALMP.
- Media keys (play/pause, next, previous) also work while another
  program is in front, and the Windows volume pop-up shows the track
  (Windows media controls; can be switched off in Settings).
- Optional (off unless you switch it on): continue films and
  audiobooks of 20 minutes or more where you stopped.
- Album art from embedded tags (MP3, FLAC, M4A).
- Hardware video decoding when your graphics card supports it.
- Click anywhere on the progress bar to jump there.
- Help (F1) and About (version, licence, open the log folder).

--------------------------------------------------------------------
5. KEYBOARD SHORTCUTS
--------------------------------------------------------------------
Space ............. Play / Pause (a focused button is pressed instead)
F ................. Fullscreen on / off
Esc ............... Leave fullscreen
Left / Right ...... Seek 5 seconds back / forward
Up / Down ......... Volume up / down (in the playlist: move up/down)
Page Up / Down .... Previous / Next track
M ................. Mute
A ................. Video size: Fit, Fill (crop), Stretch
S ................. Save a picture of the video (to Pictures)
P ................. Show / hide the playlist drawer (fullscreen)
L ................. Loop: Off / One (this track) / All (playlist)
Ctrl+F ............ Search the playlist
Ctrl+O ............ Add files      Ctrl+Shift+O ... Add a folder
Ctrl+, ............ Settings
Enter ............. Play the selected playlist item
Delete ............ Remove the selected item from the list
Shift+Delete ...... Delete the selected file (asks first)
Menu key .......... Right-click menu for the selected item
Tab ............... Move between buttons (yellow outline)
F1 ................ Help
Double-click video  Fullscreen on / off

--------------------------------------------------------------------
6. IMPORTANT NOTES
--------------------------------------------------------------------
- Fullscreen: move the mouse to show the control bar. If the playlist
  drawer is open (button on the bar, or press P) it appears and hides
  together with the bar after 3 seconds without movement. Leave
  fullscreen with Esc, F, or the button at the right of the bar.
- "Delete file" (right-click menu, or Shift+Delete) moves the file to
  the Recycle Bin, so you can restore it. BUT: USB sticks, memory
  cards and network drives have no Recycle Bin. For files there, ALMP
  warns you that the file will be deleted PERMANENTLY and only does
  it if you click "Yes". "Remove" only takes the file off the
  playlist; the file is kept.
- Interface size: changes after ALMP restarts ("Apply now" in
  Settings restarts it; the playlist is not kept).
- Remembered between runs (in %APPDATA%\ALMP\settings.json): volume,
  shuffle, remove played and the choices in Settings. Not remembered:
  the playlist, the loop mode and the playback speed.
- ALMP does not connect to the internet.
- If something goes wrong, ALMP keeps running and writes a short error
  report to %LOCALAPPDATA%\ALMP\almp.log on your PC. It is never sent
  anywhere. It can contain file names. You can attach it to a bug
  report (Settings > About ALMP > Open log folder).

--------------------------------------------------------------------
7. LICENSE
--------------------------------------------------------------------
ALMP is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your
option) any later version.

ALMP is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License
for more details. The full text is in the file "LICENSE".

ALMP uses other free software (PyQt6, Qt, mpv, FFmpeg, mutagen and
more). Their licences and where to get their source code are listed in
"THIRD-PARTY-NOTICES.txt". The full licence texts are in the
"LICENSES" folder.

Copyright (c) 2026 Alexander Bediako
====================================================================
