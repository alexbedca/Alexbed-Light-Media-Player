#!/usr/bin/env python3
"""
Make a big fake music library to stress-test ALMP with huge playlists.

Examples
  python tools/make_test_library.py D:\\ALMP-test 10000
  python tools/make_test_library.py D:\\ALMP-test 100000 --source "D:\\short-song.mp3"

Without --source the files are empty (good for testing list loading, search and
scrolling; they will not play). With --source every file is a hard link to one
real media file, so all of them PLAY and take almost no disk space
(the target folder must be on the same NTFS/ext4 drive as the source).

Then drag the folder into ALMP and note:
  * how long until the first track starts
  * whether the window stays responsive while it loads
  * how smooth scrolling and searching feel
"""
import argparse
import os
import random
import string
import sys
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="where to create the test library")
    ap.add_argument("count", type=int, help="number of files to create")
    ap.add_argument("--source", help="a real media file to hard-link (so the files play)")
    ap.add_argument("--per-folder", type=int, default=250, help="files per sub-folder (default 250)")
    ap.add_argument("--ext", default=None, help="extension to use (default: taken from --source, else .mp3)")
    args = ap.parse_args()

    ext = args.ext or (os.path.splitext(args.source)[1] if args.source else ".mp3")
    if not ext.startswith("."):
        ext = "." + ext
    if args.source and not os.path.isfile(args.source):
        sys.exit(f"Source file not found: {args.source}")

    rng = random.Random(1234)
    words = ["Love", "Night", "Road", "Fire", "Rain", "Dream", "Gold", "Blue", "River", "Home",
             "Light", "Heart", "Dance", "Sky", "Moon", "Soul", "Wave", "Stone", "Wind", "Star"]
    start = time.perf_counter()
    made = 0
    for i in range(args.count):
        sub = os.path.join(args.folder, f"Album {i // args.per_folder + 1:04d}")
        if i % args.per_folder == 0:
            os.makedirs(sub, exist_ok=True)
        name = f"{rng.choice(words)} {rng.choice(words)} {i + 1:06d} - " \
               f"{''.join(rng.choices(string.ascii_lowercase, k=6))}{ext}"
        path = os.path.join(sub, name)
        if args.source:
            try:
                os.link(args.source, path)
            except OSError as e:
                sys.exit(f"Could not create a hard link ({e}). Put the test folder on the same drive as --source.")
        else:
            open(path, "wb").close()
        made += 1
    print(f"Created {made:,} files in {time.perf_counter() - start:.1f}s under {args.folder}")


if __name__ == "__main__":
    main()
