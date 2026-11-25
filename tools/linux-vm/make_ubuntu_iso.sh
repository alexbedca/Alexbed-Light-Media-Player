#!/bin/sh
# Make the unattended Ubuntu install disc (run in the Debian VM, needs xorriso):
#   sh make_ubuntu_iso.sh ubuntu-26.04.1-desktop-amd64.iso almp_ed25519.pub out.iso
# Adds /autoinstall.yaml and "autoinstall" on the GRUB kernel lines; keeps the original boot setup.
set -e
SRC=$1; KEY=$2; OUT=$3
HERE=$(cd "$(dirname "$0")" && pwd)
W=$(mktemp -d)
sed "s|@SSH_PUBLIC_KEY@|$(cat "$KEY")|" "$HERE/ubuntu-autoinstall.yaml" > "$W/autoinstall.yaml"
xorriso -osirrox on -indev "$SRC" -extract /boot/grub/grub.cfg "$W/grub.cfg" 2>/dev/null
chmod u+w "$W/grub.cfg"
# no menu wait, and "autoinstall" before the "---" that ends the kernel options
sed -i -e 's/^set timeout=.*/set timeout=1/' -e 's| ---| autoinstall ---|' "$W/grub.cfg"
grep -n "autoinstall" "$W/grub.cfg" | head -3
rm -f "$OUT"
xorriso -indev "$SRC" -outdev "$OUT" \
  -map "$W/autoinstall.yaml" /autoinstall.yaml \
  -map "$W/grub.cfg" /boot/grub/grub.cfg \
  -boot_image any replay 2>&1 | tail -3
rm -rf "$W"
ls -la "$OUT"
