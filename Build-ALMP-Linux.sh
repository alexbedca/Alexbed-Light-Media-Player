#!/bin/sh
# Linux portable build (ALMP-Linux): Nuitka standalone folder -> release/ALMP-vX.Y.Z-Linux-x86_64.tar.gz
# Needs: python3 venv with requirements.txt + nuitka, gcc (build-essential), patchelf, ccache (optional).
# Portable: libmpv and its libraries are bundled (mpv-libs/, from the build base's libmpv2 package), so
# nothing has to be installed. Build on the oldest base it must run on (Ubuntu 24.04: tools/linux-vm/noble_build_env.sh).
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
VER=$($PY tools/get_version.py)
echo "Building ALMP $VER for Linux" | tee build-linux.log
$PY -m nuitka --version >> build-linux.log 2>&1
$PY -m nuitka --standalone --enable-plugin=pyqt6 --lto=${LTO:-no} \
  --include-data-file=icon.png=icon.png \
  --include-data-file=shaders-builtin/FSRCNNX_x2_16-0-4-1.glsl=shaders-builtin/FSRCNNX_x2_16-0-4-1.glsl \
  --include-package=almp --output-filename=ALMP --linux-icon=icon.png \
  --assume-yes-for-downloads main.py >> build-linux.log 2>&1
rm -rf release/ALMP-linux && mkdir -p release
cp -r main.dist release/ALMP-linux
cp LICENSE README.md THIRD-PARTY-NOTICES.txt release/ALMP-linux/
cp -r LICENSES release/ALMP-linux/
# Qt's X11 backend (ALMP uses it so mpv can draw inside the window, also on Wayland through XWayland)
# needs these small X libraries. Wayland-only desktops (Ubuntu 26.04) do not install them, and
# without them Qt stops at once with no message. Nuitka leaves them out as "system" libraries, so
# copy them next to libQt6XcbQpa.so.6 (its RPATH is $ORIGIN). MIT/X licence, copyright files added.
LIBDIR=/usr/lib/x86_64-linux-gnu
mkdir -p release/ALMP-linux/LICENSES/x11-libs
# libxkbcommon-x11 must match libxkbcommon exactly (a lone Debian copy crashed against Ubuntu 26.04's
# newer libxkbcommon), so both are bundled as a pair from the same build base.
for lib in libxcb-cursor.so.0 libxcb-icccm.so.4 libxcb-image.so.0 libxcb-keysyms.so.1 \
           libxcb-render-util.so.0 libxcb-xkb.so.1 libxcb-util.so.1 libxcb-shape.so.0 \
           libxkbcommon.so.0 libxkbcommon-x11.so.0; do
  cp -L "$LIBDIR/$lib" release/ALMP-linux/
  patchelf --set-rpath '$ORIGIN' "release/ALMP-linux/$lib"
  pkg=$(dpkg -S "$LIBDIR/$lib" 2>/dev/null | head -1 | cut -d: -f1)
  [ -n "$pkg" ] && cp "/usr/share/doc/$pkg/copyright" "release/ALMP-linux/LICENSES/x11-libs/$pkg.copyright" 2>/dev/null || true
done
echo "Bundled X11 libraries: $(ls release/ALMP-linux/LICENSES/x11-libs | tr '\n' ' ')" | tee -a build-linux.log
# The playback engine: libmpv + everything it needs except what must come from the user's system
# (glibc, graphics drivers, sound servers, D-Bus, fonts: see tools/bundle_libs.py).
# QtNetwork (single-instance hand-over) needs Kerberos' libgssapi_krb5, which a bare system may lack.
$PY tools/bundle_libs.py $LIBDIR/libgssapi_krb5.so.2 release/ALMP-linux --skip-dir release/ALMP-linux \
  --licenses release/ALMP-linux/LICENSES/krb5 > release/bundle-krb5.log
tee -a build-linux.log < release/bundle-krb5.log
if [ "${BUNDLE_MPV:-yes}" = "yes" ]; then
  # $ORIGIN/.. as well: libmpv also uses libraries in ALMP's top folder (libxkbcommon) and is loaded before Qt.
  $PY tools/bundle_libs.py $LIBDIR/libmpv.so.2 release/ALMP-linux/mpv-libs --skip-dir release/ALMP-linux \
    --rpath '$ORIGIN:$ORIGIN/..' --licenses release/ALMP-linux/LICENSES/mpv-libs > release/bundle-mpv.log
  tee -a build-linux.log < release/bundle-mpv.log
fi
NAME=ALMP-v$VER-Linux-x86_64
tar -C release -czf release/$NAME.tar.gz --transform "s,^ALMP-linux,$NAME," ALMP-linux
(cd release && sha256sum $NAME.tar.gz > $NAME.tar.gz.sha256.txt)
echo "Done: release/$NAME.tar.gz" | tee -a build-linux.log
