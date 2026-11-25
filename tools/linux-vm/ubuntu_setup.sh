#!/bin/sh
# Set-up of the Ubuntu 26.04 test VM, in two steps (run there as almp; ~/ALMP-Linux, ~/testmedia and
# the release tar.gz copied in first). Downloads only inside the VM.
#   sh ubuntu_setup.sh user    what an ALMP user installs (libmpv2, libxkbcommon-x11-0) + test tools
#   sh ubuntu_setup.sh source  + Qt's X11 libraries and a venv to run ALMP from source (pip's PyQt6
#                              does not include them; the built program bundles all but libxkbcommon-x11)
# Audio: the VMware HD Audio card stalls, so ALSA is turned off in WirePlumber and a silent PipeWire
# output is added (files in ~/.config/wireplumber and ~/.config/pipewire; log out/in or reboot after).
set -e
APT="sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q"
sudo DEBIAN_FRONTEND=noninteractive apt-get update -q >/dev/null
$APT libmpv2 libxkbcommon-x11-0 xdg-utils \
  playerctl wmctrl xdotool imagemagick python3-evdev python3-pil desktop-file-utils >/dev/null
cp ~/ALMP-Linux/tools/linux-vm/xw.sh ~/xw.sh && chmod +x ~/xw.sh
~/xw.sh gsettings set org.gnome.desktop.session idle-delay 0
~/xw.sh gsettings set org.gnome.desktop.screensaver lock-enabled false
mkdir -p ~/.config/wireplumber/wireplumber.conf.d ~/.config/pipewire/pipewire.conf.d
printf 'wireplumber.profiles = {\n  main = {\n    monitor.alsa = disabled\n  }\n}\n' \
  > ~/.config/wireplumber/wireplumber.conf.d/51-almp-no-alsa.conf
printf 'context.objects = [\n  { factory = adapter\n    args = {\n      factory.name = support.null-audio-sink\n      node.name = almp-test-null\n      node.description = "ALMP test null output"\n      media.class = Audio/Sink\n      audio.position = [ FL FR ]\n    }\n  }\n]\n' \
  > ~/.config/pipewire/pipewire.conf.d/51-almp-null.conf
if [ "$1" = "source" ]; then
  $APT python3-venv libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 >/dev/null
  python3 -m venv ~/venv
  ~/venv/bin/pip install -q PyQt6==6.12.1 PyQt6-Qt6==6.12.0 python-mpv==1.0.8 mutagen==1.48.1 pytest ruff
fi
echo "setup done: $(lsb_release -ds), glibc $(ldd --version | head -1 | awk '{print $NF}'), libmpv $(dpkg-query -W -f='${Version}' libmpv2)"
