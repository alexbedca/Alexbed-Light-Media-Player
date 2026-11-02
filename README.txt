====================================================================
                  ALEXBED LIGHT MEDIA PLAYER (ALMP)
====================================================================
Version:       v8.0.0
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
2. Open the "Alexbed Light Media Player (ALMP)" folder.
3. Double-click "ALMP.exe".
4. Drag and drop a folder (or files) into the window. If the playlist
   is empty, the first file starts playing automatically.

If Windows shows "Windows protected your PC" (SmartScreen), click
"More info" and then "Run anyway". ALMP is not code-signed, which is
why Windows asks.

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
To undo this, run "Remove-ALMP-Defaults.bat".

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
- Single window: opening another file while ALMP is running adds it
  to the same window.
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
- High Contrast Theme: Add Media menu (black, white and yellow).
- Shuffle, Loop 1, and "Remove played". Shuffle picks a random track
  each time; with "Remove played" off, a track can repeat.
- Album art from embedded tags (MP3, FLAC, M4A).
- Hardware video decoding when your graphics card supports it.
- Windows media keys (play/pause, next, previous) work.
- Interface size: choose 100% - 200% in the playlist panel
  (takes effect the next time you open ALMP).
- Your volume, shuffle, loop, remove-played and interface size are
  remembered between runs (saved in %APPDATA%\ALMP\settings.json).

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
P ................. Show / hide the playlist drawer (fullscreen)
Ctrl+F ............ Search the playlist
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
  "Remove" only takes it off the playlist.
- Run at Startup: tick this box to start ALMP when Windows starts.
  If you move the folder, open ALMP once and it fixes the entry.
- ALMP does not connect to the internet.

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
"THIRD-PARTY-NOTICES.txt".

Copyright (c) 2026 Alexander Bediako
====================================================================
