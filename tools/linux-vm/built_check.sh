#!/bin/sh
# Checks of the BUILT program on a VM desktop (Xorg or Wayland). Run in the VM:
#   sh built_check.sh <unpacked ALMP folder> <testmedia folder> <shots folder>
# Start time, music + MPRIS (playerctl and real key presses through uinput), video inside the window,
# app-menu entry / default player / open from the entry / remove, close. Prints PASS/FAIL lines.
D=${1%/}; M=$2; S=${3:-$HOME/shots}; mkdir -p "$S"
X="$HOME/xw.sh"; P="playerctl -p almp"
KEY="sudo $(command -v python3) $HOME/ALMP-Linux/tools/linux-vm/presskey.py"
python3 -c "import evdev" 2>/dev/null || KEY="sudo $HOME/venv/bin/python $HOME/ALMP-Linux/tools/linux-vm/presskey.py"
pass() { echo "PASS | $1 | $2"; }
fail() { echo "FAIL | $1 | $2"; }
check() { if [ "$2" = "$3" ]; then pass "$1" "$2"; else fail "$1" "got '$2', want '$3'"; fi; }
win() { $X wmctrl -l 2>/dev/null | grep "Light Media" | cut -d" " -f1 | head -1; }
close_almp() { $X wmctrl -c "Light Media"; for i in $(seq 1 30); do pgrep -x ALMP >/dev/null || return 0; sleep 0.1; done; return 1; }

# 1. start + music + MPRIS
t0=$(date +%s.%N)
$X "$D/ALMP" "$M/music" >/tmp/built.out 2>&1 &
for i in $(seq 1 100); do [ -n "$(win)" ] && break; sleep 0.1; done
t1=$(date +%s.%N)
[ -n "$(win)" ] && pass "Start (window listed)" "$(echo "$t1 - $t0" | bc) s" || fail "Start" "no window; $(tail -2 /tmp/built.out)"
for i in $(seq 1 40); do [ "$($X $P status 2>/dev/null)" = "Playing" ] && break; sleep 0.25; done
check "Music plays (MPRIS status)" "$($X $P status)" "Playing"
p1=$($X $P position | cut -d. -f1); sleep 2; p2=$($X $P position | cut -d. -f1)
[ "$p2" -gt "$p1" ] && pass "Clock moves" "$p1 -> $p2 s" || fail "Clock moves" "$p1 -> $p2"
$X $P pause; sleep 1; check "playerctl pause" "$($X $P status)" "Paused"
$X $P play; sleep 1; check "playerctl play" "$($X $P status)" "Playing"
t=$($X $P metadata xesam:title)
$X $P next; sleep 2; n=$($X $P metadata xesam:title)
[ "$n" != "$t" ] && pass "playerctl next" "$t -> $n" || fail "playerctl next" "$n"
$X $P previous; sleep 2; check "playerctl previous" "$($X $P metadata xesam:title)" "$t"
$KEY KEY_PLAYPAUSE; sleep 1.5; check "Real Play/Pause key" "$($X $P status)" "Paused"
$KEY KEY_PLAYPAUSE; sleep 1.5; check "Real Play/Pause key again" "$($X $P status)" "Playing"
$KEY KEY_NEXTSONG; sleep 2; n=$($X $P metadata xesam:title)
[ "$n" != "$t" ] && pass "Real Next key" "$t -> $n" || fail "Real Next key" "$n"
$KEY KEY_PREVIOUSSONG; sleep 2; check "Real Previous key" "$($X $P metadata xesam:title)" "$t"
$X import -window "$(win)" "$S/built-music.png" 2>/dev/null
close_almp && pass "Close" "" || fail "Close" "still running"

# 2. video inside the window (one window only; mpv must not open its own)
$X "$D/ALMP" "$M/video/big-buck-bunny-480p-30sec.mp4" >/tmp/built.out 2>&1 &
for i in $(seq 1 100); do [ -n "$(win)" ] && break; sleep 0.1; done
sleep 5
ctx=$(grep -h -i "gpu-context\|wayland" "$D"/Data/*.log 2>/dev/null | tail -1)
n=$($X wmctrl -l | grep -c -v "^$")
if [ "$($X sh -c 'echo $XDG_SESSION_TYPE')" = "x11" ]; then
  # On Xorg a window grab leaves out mpv's GL picture; take the screen and cut out ALMP's window.
  geo=$($X wmctrl -lG | grep "Light Media" | head -1 | awk '{print $5"x"$6"+"$3"+"$4}')
  $X import -window root -crop "$geo" "$S/built-video.png" 2>/dev/null
else
  $X import -window "$(win)" "$S/built-video.png" 2>/dev/null       # XWayland: the window grab works
fi
colours=$(python3 -c "
from PIL import Image; im=Image.open('$S/built-video.png').convert('RGB'); w,h=im.size
print(len(set(im.crop((w//4,h//6,3*w//4,h//2)).resize((40,20)).getdata())))" 2>/dev/null || echo "?")
[ "$colours" != "?" ] && [ "$colours" -gt 20 ] && pass "Video drawn inside ALMP" "$colours colours in the video area; X windows: $n" \
  || fail "Video drawn inside ALMP" "colours=$colours; $ctx"
close_almp && pass "Close after video" "" || fail "Close after video" "still running"

# 3. app-menu entry, default player, open from the entry, remove
cd "$HOME/ALMP-Linux" || exit 1
PYTHONPATH=. $X python3 -c "
import sys; from almp import platform_linux as pl
print(pl.install_desktop_entry(sys.argv[1] + '/ALMP', sys.argv[1] + '/icon.png', make_default=True))" "$D" >/tmp/de.out 2>&1
check "Menu entry + default player" "$(tail -1 /tmp/de.out)" "(True, '')"
check "xdg-mime default (mp3)" "$($X xdg-mime query default audio/mpeg)" "alexbed-almp.desktop"
command -v desktop-file-validate >/dev/null && { desktop-file-validate ~/.local/share/applications/alexbed-almp.desktop \
  && pass "desktop-file-validate" "" || fail "desktop-file-validate" ""; }
$X gio launch ~/.local/share/applications/alexbed-almp.desktop "$M/music/Tone 24-96.flac" >/dev/null 2>&1 &
for i in $(seq 1 100); do [ -n "$(win)" ] && break; sleep 0.1; done
sleep 3
check "Opened from the menu entry" "$($X $P metadata xesam:title)" "Tone 24-96"
close_almp
PYTHONPATH=. $X python3 -c "from almp import platform_linux as pl; print(pl.remove_desktop_entry())" >/tmp/de.out 2>&1
check "Remove menu entry" "$(tail -1 /tmp/de.out)" "(True, '')"
