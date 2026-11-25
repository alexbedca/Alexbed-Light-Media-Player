#!/bin/sh
# Test-only audio output (VM sound card stalls in these VMware VMs): add a PipeWire null sink, turn the
# HD Audio card off and make the null sink the default. Run again after every log-in. Uses ~/xw.sh.
X="$HOME/xw.sh"
$X pw-cli create-node adapter "{ factory.name=support.null-audio-sink node.name=almp-test-null node.description=\"ALMP test null output\" media.class=Audio/Sink object.linger=true audio.position=[FL FR] }" >/dev/null
sleep 1
card=$($X wpctl status | grep -E "HD Audio Controller +\[alsa\]" | grep -oE "[0-9]+\." | head -1 | tr -d .)
[ -n "$card" ] && $X wpctl set-profile "$card" 0
$X wpctl set-default "$($X wpctl status | grep "ALMP test null" | grep -oE "[0-9]+\." | head -1 | tr -d .)"
