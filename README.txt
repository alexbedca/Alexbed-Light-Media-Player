====================================================================
                  ALEXBED LIGHT MEDIA PLAYER (ALMP)
====================================================================
Version:       v8.0.1
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
2. Open the extracted "ALMP-v8.0.1-Portable" folder.
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
    Get-FileHash .\ALMP-v8.0.1-Portable.zip -Algorithm SHA256
The long code it prints must be exactly the same as on the release
page (capital or small letters do not matter). If it is different, do
not run the file.

--------------------------------------------------------------------
2. HOW TO SET AS YOUR DEFAULT MEDIA PLAYER
--------------------------------------------------------------------
Windows does not allow any program to change your default player
silently, so you must confirm the choice yourself. This script makes
it easy:

1. Make sure the ALMP folder is on your computer (not on a USB stick).
2. Double-click "Set-ALMP-Defaults.bat" and press "Y".
3. The Windows "Default apps" page opens on ALMP.
   - Windows 11: click "Set default" at the top, or click each type
     (.mp3, .mp4 ...) and choose ALMP.
   - Windows 10: click "Set this program as default".

If you move the ALMP folder later, run the .bat file again.

To undo this (or to uninstall ALMP), run "Remove-ALMP-Defaults.bat".
It removes ALMP from "Open with" and "Default apps", turns off "Run at
Startup", and asks whether to delete ALMP's settings and log files.
Then delete the ALMP folder.

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
- Double-click playback once ALMP is your default player.
- Single window: files you open from Explorer while ALMP is running
  are added to the playlist in the same window, and the first one
  starts playing. The playlist is not wiped.
- Drag and drop files or folders to add them to the playlist.
- Large playlists load in batches so the window stays responsive.
- Search box: type to filter the playlist (Ctrl+F).
- Starts clean: ALMP does not remember the last playlist or position.
- Save Playlist as M3U: Add Media menu > "Save Playlist as M3U...".
- Sleep timer: click the clock button on the control bar (or Add Media
  menu > Sleep Timer). Pick the time, then choose "When time is up":
  Pause playback, or Close ALMP. The clock turns blue while it runs.
- Audio tracks and subtitles: the button next to the speed box. In
  fullscreen the bar stays up while this menu is open.
- High Contrast Theme (black, white and yellow): click the half-filled
  circle button next to the clock on the control bar to turn it on or
  off (it turns blue while on). Also in the Add Media menu.
- Shuffle and "Remove played". Shuffle picks a random track that has
  not been played yet in this round.
- Loop button (or press L) cycles through:
    Loop: Off ... playback stops after the last track.
    Loop: One ... the track that is playing now repeats. Next / Prev
                  or double-clicking another track still move on.
    Loop: All ... the whole playlist starts again after the last
                  track (with Shuffle: every track once per round).
  Loop All switches "Remove played" off (unticked and greyed out),
  so the list never empties. When you leave Loop All, it goes back
  to how you had it. Loop is always Off when ALMP starts.
- Album art from embedded tags (MP3, FLAC, M4A).
- Hardware video decoding when your graphics card supports it.
- Windows media keys (play/pause, next, previous) work.
- Interface size: choose 100% - 200% in the playlist panel
  (takes effect the next time you open ALMP).
- Click anywhere on the progress bar to jump there.
- Your volume, shuffle, remove-played, interface size and high
  contrast choice are remembered between runs (saved in
  %APPDATA%\ALMP\settings.json). Loop is not remembered.

--------------------------------------------------------------------
5. KEYBOARD SHORTCUTS
--------------------------------------------------------------------
Space ............. Play / Pause
F ................. Fullscreen on / off
Esc ............... Leave fullscreen
Left / Right ...... Seek 5 seconds back / forward
Up / Down ......... Volume up / down
Page Up / Down .... Previous / Next track
M ................. Mute
A ................. Video size: Fit, Fill (crop), Stretch
S ................. Save a picture of the video (to Pictures)
P ................. Show / hide the playlist drawer (fullscreen)
L ................. Loop: Off / One (this track) / All (playlist)
Ctrl+F ............ Search the playlist
Enter ............. Play the selected playlist item
Tab ............... Move between buttons (yellow outline)
F1 ................ Shortcut help
Double-click video  Fullscreen on / off

--------------------------------------------------------------------
6. IMPORTANT NOTES
--------------------------------------------------------------------
- Fullscreen: move the mouse to show the control bar. If the playlist
  drawer is open (button on the bar, or press P) it appears and hides
  together with the bar after 3 seconds without movement. Leave
  fullscreen with Esc, F, or the button at the right of the bar.
- "Delete" moves the file to the Recycle Bin, so you can restore it.
  BUT: USB sticks, memory cards and network drives have no Recycle
  Bin. For files there, ALMP warns you that the file will be deleted
  PERMANENTLY and only does it if you click "Yes".
  "Remove" only takes the file off the playlist; the file is kept.
- Run at Startup: tick this box to start ALMP when Windows starts.
  If you move the folder, open ALMP once and it fixes the entry.
- ALMP does not connect to the internet.
- If something goes wrong, ALMP keeps running and writes a short error
  report to %LOCALAPPDATA%\ALMP\almp.log on your PC. It is never sent
  anywhere. You can attach it to a bug report.

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
