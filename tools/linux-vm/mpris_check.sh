#!/bin/sh
# Linux VM check of ALMP's MPRIS (background media keys). Run on the VM: sh tools/linux-vm/mpris_check.sh [program]
# Starts ALMP on the desktop with the test music, then drives it with playerctl and real X media keys
# while another window is in front. Prints PASS/FAIL lines; screenshots go to ~/shots.
PROG=${1:-"$HOME/venv/bin/python main.py"}
X="$HOME/x.sh"
P="playerctl -p almp"
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1 ($2)"; }
check() { if [ "$2" = "$3" ]; then pass "$1"; else fail "$1" "got '$2', want '$3'"; fi; }

cd "$HOME/ALMP-Linux" || exit 1
$X $PROG "$HOME/testmedia/music" >/tmp/almp-mpris.out 2>&1 &
for i in $(seq 1 40); do $X $P status >/dev/null 2>&1 && break; sleep 0.5; done
sleep 3
check "registered on the session bus" "$($X playerctl -l 2>/dev/null | grep -c '^almp')" "1"
check "playing after start" "$($X $P status)" "Playing"
t1="$($X $P metadata xesam:title)"
[ -n "$t1" ] && pass "title shown: $t1" || fail "title shown" "empty"
$X $P pause; sleep 1
check "pause" "$($X $P status)" "Paused"
$X $P play; sleep 1
check "play" "$($X $P status)" "Playing"
$X $P next; sleep 2
t2="$($X $P metadata xesam:title)"
[ "$t2" != "$t1" ] && pass "next: $t2" || fail "next" "title stayed $t2"
$X $P previous; sleep 2
check "previous" "$($X $P metadata xesam:title)" "$t1"
p1="$($X $P position | cut -d. -f1)"; sleep 2; p2="$($X $P position | cut -d. -f1)"
[ "$p2" -gt "$p1" ] && pass "position moves ($p1 -> $p2 s)" || fail "position moves" "$p1 -> $p2"
$X $P volume 0.5; sleep 0.5
check "volume set from the desktop" "$($X $P volume)" "0.500000"
$X $P volume 1.0

# Real media keys while another window is in front (GNOME's media-keys service sends them over MPRIS).
$X xterm -geometry 80x20+50+50 -T keytest -e sleep 30 &
sleep 2
$X xdotool search --name keytest windowactivate --sync 2>/dev/null
sleep 0.5
active="$($X xdotool getactivewindow getwindowname 2>/dev/null)"
echo "INFO active window: $active"
$X xdotool key XF86AudioPlay; sleep 1.5
check "Play/Pause key in the background pauses" "$($X $P status)" "Paused"
$X xdotool key XF86AudioPlay; sleep 1.5
check "Play/Pause key in the background plays" "$($X $P status)" "Playing"
before="$($X $P metadata xesam:title)"
$X xdotool key XF86AudioNext; sleep 2
after="$($X $P metadata xesam:title)"
[ "$after" != "$before" ] && pass "Next key in the background" || fail "Next key in the background" "$after"
$X xdotool key XF86AudioPrev; sleep 2
check "Previous key in the background" "$($X $P metadata xesam:title)" "$before"
pkill -x xterm

# GNOME's media controls (in the date/notification menu).
$X xdotool key super+v; sleep 2
~/shot.sh mpris-gnome-menu >/dev/null
$X xdotool key Escape
$X $P stop; sleep 1
check "stop" "$($X $P status)" "Paused"
echo "INFO almp output:"; tail -5 /tmp/almp-mpris.out
