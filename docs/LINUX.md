# ALMP on Linux

ALMP's Linux version is the same code as the Windows version (`almp/`), with a few Linux-only parts. One
repository, one version number: each release carries `ALMP-vX.Y.Z-Portable.zip` (Windows) and
`ALMP-vX.Y.Z-Linux-x86_64.tar.gz` (Linux).

## Windows feature → Linux answer

| Windows | Linux | Code |
|---|---|---|
| Recycle Bin | freedesktop.org Trash (home: `~/.local/share/Trash`, other drives: `.Trash-<uid>`); RAM disks, network and read-only drives have no Trash, so ALMP asks before deleting for good (same rule as Windows) | `almp/platform_linux.py` |
| Explorer "Open with" / Default apps | `~/.local/share/applications/alexbed-almp.desktop` (60 types) + `xdg-mime default` | `platform_linux.py`, Settings > Linux |
| Windows media controls (SMTC) | MPRIS over D-Bus (`org.mpris.MediaPlayer2.almp`): media keys in the background, the desktop's media panel (title, artist, album, art) | `almp/mpris.py` |
| WASAPI exclusive audio | "Through PipeWire (exclusive)" or "Direct: <device>" (ALSA hdmi:/front:/hw:/iec958:, bit-perfect); a busy device falls back to PipeWire | `player.exclusive_audio_options`, Settings > Playback |
| Dark title bar (DWM) | `_GTK_THEME_VARIANT=dark` on every X11 window (Cinnamon honours it; GNOME draws its own frame) | `almp/x11_theme.py` |
| mpv-2.dll next to ALMP.exe | libmpv + its libraries in `mpv-libs/` (portable), RUNPATH `$ORIGIN:$ORIGIN/..` | `tools/bundle_libs.py`, `player.bundled_libmpv` |
| Video in the window | Qt on X11 (`xcb`; XWayland on Wayland) so mpv can draw into ALMP's window; mpv `gpu-context=x11egl` on Wayland, `input-cursor=no` (ALMP keeps the mouse) | `app.py`, `player.mpv_options` |
| Single instance, Data folder, settings | the same code (portable `Data` folder next to the program when writable) | |

## Building the Linux tarball

Build on the **oldest** system the tarball must run on: the result needs the build system's glibc or newer.
The releases are built in an Ubuntu 24.04 (glibc 2.39) chroot:

```sh
sudo apt install debootstrap ubuntu-keyring
sudo debootstrap --keyring=/usr/share/keyrings/ubuntu-archive-keyring.gpg --components=main,universe \
     --variant=minbase noble /srv/noble http://archive.ubuntu.com/ubuntu
sudo sh tools/linux-vm/noble_build_env.sh /srv/noble          # once: tools, libmpv2, venv with Nuitka
sudo sh tools/linux-vm/noble_build_env.sh /srv/noble build    # copies the source in, builds, copies the result out
```

`Build-ALMP-Linux.sh` runs Nuitka (`--standalone`), copies the small X11 libraries Qt's X11 backend needs
(and the matching `libxkbcommon` pair), Kerberos for QtNetwork, and libmpv with everything it needs
(`tools/bundle_libs.py`), then writes `release/ALMP-vX.Y.Z-Linux-x86_64.tar.gz` and its `.sha256.txt`.
Libraries that must match the user's system are **not** bundled: glibc, the graphics driver stack and the
X11/Wayland/compression libraries it uses, ALSA/PulseAudio/PipeWire, D-Bus, fontconfig/freetype, GLib.
The build prints that list ("Taken from the system"); check each entry exists on the target systems when the
build base changes (`tools/linux-vm/ldd_check.sh` on a bare system shows what is still needed).

Size: about 145 MB packed, 350 MB unpacked (most of it Ubuntu's FFmpeg with its codec libraries).

## Testing

- `pytest` runs on Windows and Ubuntu in CI. The Linux-only tests (real D-Bus, gdbus) skip when there is no
  session bus.
- On a Linux desktop (test machine or VM):
  - `tools/linux_smoke.py`: 28 checks of the real window with real mpv (from source).
  - `tools/linux-vm/built_check.sh <unpacked folder> <media> <shots>`: 19 checks of the built program
    (start, music, MPRIS, media keys, video inside the window, menu entry/default player).
  - `tools/linux-vm/mouse_check.py`: 12 checks with REAL input (xdotool on Xorg, a uinput tablet/keyboard on
    Wayland): pointer in fullscreen, Play/Pause and Next buttons, wheel, right-click menu, double-click,
    seek-bar drag. Do not run it on a PC someone is using.
  - `tools/linux-vm/exclusive_check.sh`: exclusive audio through PipeWire, direct, busy device, off.
  - `tools/linux-vm/look_shots.py`: screenshots of every window for a side-by-side look with Windows.

## Release steps (both systems)

1. Version in `almp/__init__.py`, README.md, README.txt, `docs/release-notes/vX.Y.Z.md`.
2. Windows: `Build-ALMP.bat`, `Package-ALMP.bat` (or the GitHub Actions build) → `ALMP-vX.Y.Z-Portable.zip`.
3. Linux: build in the Ubuntu 24.04 chroot (above) → `ALMP-vX.Y.Z-Linux-x86_64.tar.gz` + `.sha256.txt`.
4. Test both: the Windows release checks, and on Linux at least `built_check.sh` and `mouse_check.py` on one
   Xorg and one Wayland desktop, plus a desktop without any mpv installed.
5. One GitHub release with both files and both SHA-256 sums; the release notes list what was tested and what
   was NOT tested on each system.

## Not tested (as of the first Linux release)

KDE, Xfce and other desktops; Fedora, Arch, openSUSE; HiDPI screens; NVIDIA/AMD graphics and hardware decoding
(tested on Intel and virtual GPUs); real USB sticks (Trash); drag and drop of files.
