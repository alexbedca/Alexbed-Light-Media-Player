# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""The playlist data: one Python list of paths plus a small search index. No Qt here.

Why this is fast with 100,000+ files:
  * one plain string per file in `paths`, one case-folded search string per file in `search`;
    no widget or item object per file (the list on screen asks only for the rows it shows);
  * duplicates are found with a set of hashes, so adding a file is O(1);
  * the search text is made once, when the file is added (on the scanner thread when possible),
    so filtering is a single tight loop over strings;
  * a search that only adds letters to the previous one is run over the previous matches only.
"""
import ntpath
import os

# Separates the file name from its folder name inside the search text, so a search never matches
# across the two (it is a character nobody types).
_SEP = "\x1f"


def make_entry(path, normcase=os.path.normcase):
    """(path, duplicate key, search text) for one file. Cheap; runs on the scanner thread."""
    head, name = ntpath.split(path)
    parent = ntpath.basename(head)
    return (path, hash(normcase(path)), (name + _SEP + parent).casefold())


def split_query(text):
    """Search words, case-folded. Every word must be found (in the file name or its folder name)."""
    return [w for w in (text or "").casefold().split() if w]


class PlaylistStore:
    """Ordered list of files with O(1) "already in the list?" checks and a fast filter.

    `paths[i]` and `search[i]` always describe the same row. `version` changes on every change of
    order or content, so background work (sorting) can tell whether its snapshot is still valid.
    Duplicate check: the same file twice is skipped; the same NAME in another folder is kept.
    (Keys are 64-bit hashes of the normalised path, which saves memory with huge lists.)"""

    def __init__(self, normcase=os.path.normcase):
        self.normcase = normcase
        self.paths = []
        self.search = []
        self._keys = set()
        self.version = 0

    # --- reading ---
    def __len__(self):
        return len(self.paths)

    def __bool__(self):
        return bool(self.paths)

    def key_of(self, path):
        return hash(self.normcase(path))

    def contains(self, path):
        return self.key_of(path) in self._keys

    def contains_key(self, key):
        return key in self._keys

    def index_of(self, path, hint=-1):
        """Row of `path`, or -1. `hint` (a row where it probably is) makes the usual case O(1)."""
        if 0 <= hint < len(self.paths) and self.paths[hint] == path:
            return hint
        try:
            return self.paths.index(path)
        except ValueError:
            return -1

    def index_of_key(self, key):
        """Row whose normalised path has this key (slow path, used once per opened file)."""
        nc = self.normcase
        for i, p in enumerate(self.paths):
            if hash(nc(p)) == key:
                return i
        return -1

    @staticmethod
    def name_of(path):
        return ntpath.basename(path)

    # --- adding ---
    def new_entries(self, entries):
        """The entries that are not in the list yet (also drops duplicates inside `entries`).
        Does not change the store: call commit() with the result."""
        keys = self._keys
        seen = set()
        out = []
        for e in entries:
            k = e[1]
            if k in keys or k in seen:
                continue
            seen.add(k)
            out.append(e)
        return out

    def commit(self, entries):
        """Append entries returned by new_entries(). Returns the first new row."""
        start = len(self.paths)
        if entries:
            self.paths.extend(e[0] for e in entries)
            self.search.extend(e[2] for e in entries)
            self._keys.update(e[1] for e in entries)
            self.version += 1
        return start

    def extend(self, paths):
        """Convenience for tests and small additions: add plain paths, return how many were new."""
        fresh = self.new_entries([make_entry(p, self.normcase) for p in paths])
        self.commit(fresh)
        return len(fresh)

    # --- removing / moving ---
    def remove_at(self, row):
        path = self.paths.pop(row)
        self.search.pop(row)
        self._keys.discard(self.key_of(path))
        self.version += 1
        return path

    def move(self, src, dst):
        """Move row `src` so that it ends up at row `dst` (in the final list)."""
        n = len(self.paths)
        if not (0 <= src < n) or not (0 <= dst < n) or src == dst:
            return False
        p = self.paths.pop(src)
        s = self.search.pop(src)
        self.paths.insert(dst, p)
        self.search.insert(dst, s)
        self.version += 1
        return True

    def clear(self):
        self.paths = []
        self.search = []
        self._keys = set()
        self.version += 1

    def reorder(self, order):
        """Apply a new order (a permutation of row numbers), e.g. after sorting."""
        n = len(self.paths)
        if len(order) != n or (n and (min(order) != 0 or max(order) != n - 1 or len(set(order)) != n)):
            raise ValueError("not a permutation of the rows")
        self.paths = [self.paths[i] for i in order]
        self.search = [self.search[i] for i in order]
        self.version += 1

    # --- filtering ---
    def filter_rows(self, words, within=None):
        """Rows whose search text contains every word. `within` (a list of rows) limits the search,
        e.g. to the previous matches when the user only typed more letters."""
        search = self.search
        if not words:
            return list(range(len(search))) if within is None else list(within)
        first, rest = words[0], words[1:]
        if within is None:
            rows = [i for i, s in enumerate(search) if first in s]
        else:
            rows = [i for i in within if first in search[i]]
        for w in rest:
            rows = [i for i in rows if w in search[i]]
        return rows


def is_refinement(old_words, new_words):
    """True when every new word extends an old word at the same place (or is a new extra word),
    so the new matches are a subset of the old ones and only those need checking."""
    if not old_words:
        return False
    if len(new_words) < len(old_words):
        return False
    return all(o in n for o, n in zip(old_words, new_words, strict=False))
