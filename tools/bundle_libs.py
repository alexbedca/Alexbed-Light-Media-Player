"""Linux build: copy a library (libmpv) and everything it needs into a folder, so ALMP is portable
(nothing to install). Run on the build base (Ubuntu 24.04 chroot):
    python3 tools/bundle_libs.py /usr/lib/x86_64-linux-gnu/libmpv.so.2 <dist>/mpv-libs --skip-dir <dist>
              [--licenses <dist>/LICENSES/mpv-libs]
Libraries that must match the user's own system are NOT copied (see SYSTEM_PATTERNS): glibc, the GPU /
graphics-driver stack and the libraries the drivers themselves use, sound servers (ALSA, PulseAudio,
PipeWire), D-Bus, fonts. Every copied library gets RUNPATH $ORIGIN so it finds its neighbours.
Pure helpers (is_system_lib, parse_ldd) are tested on Windows too."""
import argparse
import os
import re
import shutil
import subprocess
import sys

# Taken from the user's system. Reasons: glibc must be the system's; GPU drivers (Mesa/NVIDIA) and
# the X11/Wayland/compression libraries they link must match the driver; sound and D-Bus libraries
# talk to services of the same version; fontconfig must read the system's font configuration.
SYSTEM_PATTERNS = [
    # glibc and the compiler runtime
    r"ld-linux.*", r"libc", r"libm", r"libdl", r"libpthread", r"librt", r"libresolv", r"libutil", r"libanl",
    r"libmvec", r"libnsl", r"libBrokenLocale", r"libthread_db", r"libstdc\+\+", r"libgcc_s",
    # GPU / graphics drivers (OpenGL/EGL/GBM/DRM through glvnd and Mesa or NVIDIA)
    r"libGL", r"libGLX", r"libEGL", r"libGLdispatch", r"libOpenGL", r"libGLESv2", r"libgbm", r"libdrm.*",
    r"libglapi",
    # libraries the graphics drivers link themselves (one copy per process: must be the system's)
    r"libX11", r"libX11-xcb", r"libxcb", r"libxcb-(dri2|dri3|present|sync|xfixes|randr|glx|shm|render)",
    r"libXext", r"libXfixes", r"libXxf86vm", r"libxshmfence", r"libXau", r"libXdmcp",
    r"libwayland-.*", r"libexpat", r"libz", r"libzstd", r"libelf", r"libLLVM.*", r"libsensors", r"libudev",
    r"libsystemd", r"libcap", r"liblzma", r"liblz4", r"libgcrypt", r"libgpg-error", r"libffi", r"libbsd",
    # (not libxml2 / ICU: Ubuntu 26.04 has libxml2.so.16 and Debian 13 / Ubuntu 26.04 a newer ICU, so the
    # sonames libavformat needs are missing there; they are bundled)
    r"libmd", r"libedit", r"libtinfo", r"libbz2", r"libbrotli.*", r"libpng16",
    # sound servers and D-Bus (client libraries must match the running service)
    r"libasound", r"libpulse.*", r"libpipewire-.*", r"libdbus-1",
    # fonts (must read the system's font configuration)
    r"libfontconfig", r"libfreetype",
    # GLib (Qt already loads the system's copy; GIO loads the system's modules), and its base libraries
    r"libglib-2\.0", r"libgobject-2\.0", r"libgio-2\.0", r"libgmodule-2\.0", r"libgthread-2\.0",
    r"libselinux", r"libpcre2-8", r"libmount", r"libblkid",
]
_SYSTEM_RE = re.compile(r"^(?:" + "|".join(SYSTEM_PATTERNS) + r")\.so(?:\.[0-9.]+)?$")


def is_system_lib(soname):
    """True for libraries ALMP takes from the user's system instead of bundling."""
    return bool(_SYSTEM_RE.match(soname))


def parse_ldd(text):
    """ldd output -> {soname: path or None (not found)}."""
    libs = {}
    for line in text.splitlines():
        m = re.match(r"\s*(\S+)\s+=>\s+(not found|\S+)", line)
        if m:
            libs[m.group(1)] = None if m.group(2) == "not found" else m.group(2)
    return libs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("library")
    ap.add_argument("dest")
    ap.add_argument("--skip-dir", action="append", default=[], help="sonames already present there are skipped")
    ap.add_argument("--licenses")
    ap.add_argument("--rpath", default="$ORIGIN", help='e.g. "$ORIGIN:$ORIGIN/.." to also see the folder above')
    a = ap.parse_args(argv)
    os.makedirs(a.dest, exist_ok=True)
    libs = parse_ldd(subprocess.run(["ldd", a.library], capture_output=True, text=True, check=True).stdout)
    missing = [n for n, p in libs.items() if p is None]
    if missing:
        sys.exit("not found on the build base: " + ", ".join(missing))
    main_name = os.path.basename(a.library)
    libs[main_name] = os.path.realpath(a.library)
    copied, system, skipped = [], [], []
    for name, path in sorted(libs.items()):
        if is_system_lib(name):
            system.append(name)
            continue
        if any(os.path.exists(os.path.join(d, name)) for d in a.skip_dir):
            skipped.append(name)
            continue
        target = os.path.join(a.dest, name)
        shutil.copy2(os.path.realpath(path), target)
        os.chmod(target, 0o755)
        subprocess.run(["patchelf", "--set-rpath", a.rpath, target], check=True)
        copied.append(name)
        if a.licenses:
            pkg = subprocess.run(["dpkg", "-S", os.path.realpath(path)], capture_output=True, text=True).stdout
            pkg = pkg.split(":")[0].strip() if pkg else ""
            src = f"/usr/share/doc/{pkg}/copyright"
            if pkg and os.path.exists(src):
                os.makedirs(a.licenses, exist_ok=True)
                shutil.copy2(src, os.path.join(a.licenses, f"{pkg}.copyright"))
    size = sum(os.path.getsize(os.path.join(a.dest, n)) for n in copied)
    print(f"Bundled {len(copied)} libraries ({size / 1e6:.1f} MB) into {a.dest}")
    print("Taken from the system: " + " ".join(system))
    if skipped:
        print("Already next to ALMP: " + " ".join(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
