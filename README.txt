====================================================================
                  ALEXBED LIGHT MEDIA PLAYER (ALMP)
====================================================================
Version:       v7.1.0 (The "Studio" Edition)
Release Date:  31 October 2026
Developer:     Alexander Bediako
Contact:       alexbedgh@gmail.com
License:       MIT License (Free and Open Source)

--------------------------------------------------------------------
1. QUICK START (NO INSTALLATION REQUIRED)
--------------------------------------------------------------------
This is a 100% portable application. It does not require Python, 
VLC, or any other software to be installed on your computer.

1. Extract the ZIP file to a folder on your PC.
2. Open the "Alexbed Light Media Player (ALMP)" folder.
3. Double-click "ALMP.exe" to launch the player.
4. Drag and drop a folder (or individual files) directly into the 
   window. The player will automatically start playing the first 
   file if the playlist is empty.

--------------------------------------------------------------------
2. HOW TO SET AS YOUR DEFAULT MEDIA PLAYER
--------------------------------------------------------------------
Microsoft has made it intentionally difficult for any app to 
automatically become the "default" player for security reasons. 
This is why you must confirm the choice yourself.

We have provided a script to make this easy:

1. Open the "Alexbed Light Media Player (ALMP)" folder.
2. Double-click "Set-ALMP-Defaults.bat".
3. Press "Y" to continue when prompted.
4. The Windows "Default apps" settings page will open, showing ALMP.
5. Click the big "Set default" button at the top of the page (or 
   click each extension like .mp3 and .mp4 and select ALMP).

Note: If you move the ALMP folder to a different location later, 
you must run the .bat file again so Windows knows the new path. 
To undo this later, run "Remove-ALMP-Defaults.bat".

--------------------------------------------------------------------
3. HOW TO CREATE A DESKTOP SHORTCUT (AND FIX THE ICON)
--------------------------------------------------------------------
Because this is a portable app, Windows sometimes shows a blank 
icon if you just drag the EXE to your desktop. Here is how to fix it:

1. Right-click "ALMP.exe" and select "Show more options" > 
   "Create shortcut".
2. Move the new shortcut to your Desktop.
3. Right-click the shortcut and select "Properties".
4. Click "Change Icon..." at the bottom.
5. Click "Browse", select the "icon.ico" file inside the ALMP folder, 
   and click OK.
6. Rename the shortcut to "ALMP Media Player".

--------------------------------------------------------------------
4. KEY FEATURES
--------------------------------------------------------------------
- Double-Click Playback: Once set as default, double-clicking a media
  file will open it instantly in ALMP.
- Single-Instance Mode: If ALMP is already open, double-clicking a new 
  file will append it to the current playlist without opening a new window.
- Smart Playlists: Drop new files into the window to APPEND them.
- Remove from List: Don't want a file in your playlist? Click 
  "Remove from List" to remove it without deleting the physical file.
- True Random Shuffle: Picks a completely random track every time.
- Album Art: Displays embedded cover art for MP3 and FLAC files.
- High Performance: Handles playlists with 2000+ files without lag.
- Hardware Decoding: Uses your GPU to play 4K videos smoothly.
- IR Remote Support: Fully compatible with standard Windows Media Keys.

--------------------------------------------------------------------
5. KEYBOARD & REMOTE SHORTCUTS
--------------------------------------------------------------------
Spacebar .......... Play / Pause
F ................. Toggle Fullscreen Mode
Esc ............... Exit Fullscreen Mode
Right Arrow ....... Seek forward 5 seconds
Left Arrow ........ Seek backward 5 seconds
Up / Down Arrows .. Increase / Decrease Volume
PageUp / PageDown . Previous / Next Track
M ................. Toggle Mute

--------------------------------------------------------------------
6. IMPORTANT NOTES
--------------------------------------------------------------------
- Fullscreen Mode: Double-click the video to go fullscreen. The 
  mouse cursor and control panels will auto-hide after 5 seconds. 
  Move the mouse to reveal them. Click the "X" button in the top 
  right to exit fullscreen.
- Delete File vs Remove from List: "Delete File" PERMANENTLY deletes 
  the file from your hard drive. "Remove from List" only removes it 
  from the current playlist.
- Run at Startup: Check this box in the app to automatically launch 
  the player when Windows boots.

--------------------------------------------------------------------
7. LICENSE (MIT)
--------------------------------------------------------------------
Copyright (c) 2026 Alexander Bediako

Permission is hereby granted, free of charge, to any person obtaining 
a copy of this software and associated documentation files (the 
"Software"), to deal in the Software without restriction, including 
without limitation the rights to use, copy, modify, merge, publish, 
distribute, sublicense, and/or sell copies of the Software, and to 
permit persons to whom the Software is furnished to do so, subject 
to the following conditions:

The above copyright notice and this permission notice shall be 
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, 
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF 
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. 
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY 
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, 
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE 
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
====================================================================