ALMP - LICENCE TEXTS OF THE SOFTWARE INSIDE THIS FOLDER
=======================================================

ALMP itself is under the GNU General Public License v3 or later: see the
file LICENSE next to ALMP.exe. This folder holds the licence texts of the
other free software that is shipped inside the ALMP zip. The overview of
which component uses which licence is in THIRD-PARTY-NOTICES.txt.

File                     Used by
-----------------------  ---------------------------------------------------
GPL-2.0.txt              mpv / libmpv, mutagen, python-mpv (all "v2 or later";
                         FFmpeg parts in a GPL build)
LGPL-2.1.txt             parts of FFmpeg and mpv, python-mpv (dual licence)
LGPL-3.0.txt             Qt 6 (read together with the GPL v3 in LICENSE)
Apache-2.0.txt           OpenSSL 3 (used by Python), Nuitka runtime parts
MIT-libffi.txt           libffi (used by Python's ctypes)
Python-PSF-2.0.txt       Python (the full licence file shipped with Python)

The GNU GPL version 3 text is the file LICENSE.

Libraries built into Qt and into the libmpv/FFmpeg build
--------------------------------------------------------
Qt and the libmpv build contain smaller libraries with their own (all
free and permissive or copyleft) licences, for example zlib, libpng,
FreeType, HarfBuzz, PCRE2 and double-conversion inside Qt, and dav1d,
libass, FriBidi, libplacebo and others inside the libmpv build. Their
notices are listed by the upstream projects:

- Qt:      https://doc.qt.io/qt-6/licenses-used-in-qt.html
- libmpv:  https://github.com/zhongfly/mpv-winbuild (build scripts and the
           list of libraries for the pinned build named in BUILD-INFO.txt)

This list is a good-faith summary, not legal advice. If you find a
missing notice, please open an issue on
https://github.com/alexbedca/Alexbed-Light-Media-Player/issues
