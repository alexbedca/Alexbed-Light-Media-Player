#!/bin/sh
# Ubuntu 24.04 ("noble", glibc 2.39) build base inside the Debian VM, so one Linux build runs on
# Linux Mint 22 / Ubuntu 24.04 and newer (Debian 13, Ubuntu 26.04). A build on glibc 2.41 does not start there.
#   sudo debootstrap --keyring=/usr/share/keyrings/ubuntu-archive-keyring.gpg --components=main,universe \
#        --variant=minbase noble /srv/noble http://archive.ubuntu.com/ubuntu
#   sudo sh tools/linux-vm/noble_build_env.sh /srv/noble          (once: tools + venv)
#   sudo sh tools/linux-vm/noble_build_env.sh /srv/noble build    (copy ~/ALMP-Linux in, build, copy release out)
set -e
R=${1:-/srv/noble}
mounts() {
  for d in proc sys dev dev/pts; do mountpoint -q "$R/$d" || mount --bind "/$d" "$R/$d"; done
  cp /etc/resolv.conf "$R/etc/resolv.conf"
}
unmounts() { for d in dev/pts dev sys proc; do umount "$R/$d" 2>/dev/null || true; done; }
trap unmounts EXIT
mounts
if [ "$2" = "build" ]; then
  rm -rf "$R/build/ALMP-Linux" && mkdir -p "$R/build"
  cp -r /home/almp/ALMP-Linux "$R/build/ALMP-Linux"
  rm -rf "$R/build/ALMP-Linux/main.build" "$R/build/ALMP-Linux/main.dist" "$R/build/ALMP-Linux/release"
  chroot "$R" sh -c 'cd /build/ALMP-Linux && PYTHON=/opt/venv/bin/python ./Build-ALMP-Linux.sh'
  mkdir -p /home/almp/ALMP-Linux/release-noble
  cp "$R"/build/ALMP-Linux/release/*.tar.gz* /home/almp/ALMP-Linux/release-noble/
  cp "$R/build/ALMP-Linux/build-linux.log" /home/almp/ALMP-Linux/release-noble/
  chown -R almp:almp /home/almp/ALMP-Linux/release-noble
  ls -la /home/almp/ALMP-Linux/release-noble
  exit 0
fi
cat > "$R/etc/apt/sources.list" <<'EOF'
deb http://archive.ubuntu.com/ubuntu noble main universe
deb http://archive.ubuntu.com/ubuntu noble-updates main universe
deb http://security.ubuntu.com/ubuntu noble-security main universe
EOF
chroot "$R" sh -c 'export DEBIAN_FRONTEND=noninteractive; apt-get update -q >/dev/null && apt-get upgrade -y -q >/dev/null &&
  apt-get install -y -q --no-install-recommends python3 python3-venv python3-dev gcc g++ make patchelf ccache \
    ca-certificates dpkg-dev libgl1 libegl1 libfontconfig1 libfreetype6 libxkbcommon0 libdbus-1-3 libglib2.0-0t64 \
    libx11-6 libx11-xcb1 libxcb1 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 \
    libxcb-xkb1 libxcb-util1 libxkbcommon-x11-0 libxrender1 libxi6 libsm6 libice6 libmpv2 libxcb-shape0 libgssapi-krb5-2 >/dev/null'
chroot "$R" sh -c 'python3 -m venv /opt/venv && /opt/venv/bin/pip install -q PyQt6==6.12.1 PyQt6-Qt6==6.12.0 \
  python-mpv==1.0.8 mutagen==1.48.1 nuitka==4.3.5 ordered-set zstandard'
chroot "$R" sh -c 'ldd --version | head -1; /opt/venv/bin/python --version; /opt/venv/bin/python -m nuitka --version | head -1'
