#!/bin/sh
# Linux "Exclusive audio" in a test VM: through PipeWire, direct to a device, and direct while the device is
# busy (falls back to PipeWire). Run ALMP from source: sh exclusive_check.sh <direct device, e.g. alsa/front:CARD=Generic,DEV=0>
# Reads only: pw-dump (PipeWire streams; nothing else may play meanwhile), fuser on /dev/snd (who holds the card), ALMP's log.
DEV=${1:-alsa/front:CARD=Generic,DEV=0}
X="$HOME/xw.sh"
MUSIC="$HOME/testmedia/music/Tone 24-96.flac"
pass() { echo "PASS | $1 | $2"; }
fail() { echo "FAIL | $1 | $2"; }
pw_node() { $X pw-dump 2>/dev/null | python3 -c "
import json, sys
for o in json.load(sys.stdin):
    p = (o.get('info') or {}).get('props') or {}
    name = str(p.get('application.name', '')) + str(p.get('node.name', ''))
    if p.get('media.class') == 'Stream/Output/Audio' and ('mpv' in name.lower() or 'almp' in name.lower()):
        print('exclusive=%s rate=%s' % (p.get('node.exclusive'), p.get('node.rate'))); break
else:
    print('none')"; }
holds_card() { for f in /dev/snd/pcmC*p; do fuser "$f" 2>/dev/null; done | tr -s ' ' '\n' | grep -qx "$1" && echo yes || echo no; }

run() {   # $1 label, $2 settings json
  D=$(mktemp -d); printf '%s' "$2" > "$D/settings.json"
  cd "$HOME/ALMP-Linux" && (ALMP_DATA_DIR=$D $X "$HOME/venv/bin/python" main.py "$MUSIC" >/tmp/excl.out 2>&1 &)
  sleep 5
  PID=$(pgrep -f "^$HOME/venv/bin/python main.py" | head -1)
  NODE=$(pw_node "$PID"); CARD=$(holds_card "$PID")
  echo "INFO [$1] pid=$PID pipewire-stream: $NODE  holds-card: $CARD"
  grep -h -i "exclusive" "$D"/*.log 2>/dev/null | tail -2 | sed 's/^/INFO   log: /'
  $X wmctrl -c "Light Media"; sleep 2
}

run "PipeWire exclusive" '{"audio_exclusive": true, "audio_exclusive_device": ""}'
case "$NODE" in exclusive=True*) pass "Through PipeWire: ALMP's stream is exclusive" "$NODE";;
  *) fail "Through PipeWire: ALMP's stream is exclusive" "$NODE";; esac

run "direct" "{\"audio_exclusive\": true, \"audio_exclusive_device\": \"$DEV\"}"
[ "$CARD" = yes ] && [ "$NODE" = none ] && pass "Direct: ALMP holds the card itself, no PipeWire stream" "$DEV" \
  || fail "Direct: ALMP holds the card itself, no PipeWire stream" "card=$CARD stream=$NODE"

# make the card busy with another program, then ask for it directly
HW=$(echo "$DEV" | sed -n 's/.*CARD=\([^,]*\),DEV=\([0-9]*\).*/hw:CARD=\1,DEV=\2/p')
(aplay -q -D "$HW" -f S16_LE -r 48000 -c 2 /dev/zero >/dev/null 2>&1 &); sleep 1
run "direct, busy" "{\"audio_exclusive\": true, \"audio_exclusive_device\": \"$DEV\"}"
pkill -x aplay
case "$NODE" in exclusive=True*) pass "Busy device: falls back to PipeWire (exclusive)" "$NODE";;
  *) fail "Busy device: falls back to PipeWire (exclusive)" "stream=$NODE card=$CARD";; esac

run "off" '{"audio_exclusive": false}'
case "$NODE" in exclusive=True*) fail "Off: normal PipeWire stream" "$NODE";;
  none) fail "Off: normal PipeWire stream" "no stream";; *) pass "Off: normal PipeWire stream" "$NODE";; esac
