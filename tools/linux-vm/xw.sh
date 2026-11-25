#!/bin/sh
# Like ~/x.sh, but for a GNOME *Wayland* session: takes DISPLAY/WAYLAND_DISPLAY/XAUTHORITY from the
# user's systemd environment (XWayland's auth file name changes at every login). Copy to ~/xw.sh in the VM.
export XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
eval "$(systemctl --user show-environment | grep -E '^(DISPLAY|WAYLAND_DISPLAY|XAUTHORITY|XDG_SESSION_TYPE)=' | sed 's/^/export /')"
exec "$@"
