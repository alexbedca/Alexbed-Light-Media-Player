# Alexbed Light Media Player (ALMP)
# Copyright (C) 2026 Alexander Bediako
# SPDX-License-Identifier: GPL-3.0-or-later
"""A virtual list model over PlaylistStore.

The list view asks this model only for the rows it is drawing (about 20 at a time), so a playlist
of 250,000 files costs no more on screen than one of 20. There is no item object per file.

"Source row" = position in the whole playlist (store.paths). "View row" = position in what is
shown (the same when no search is active; otherwise only the matches, in playlist order).
"""
import bisect
import ntpath

from PyQt6.QtCore import QAbstractListModel, QByteArray, QMimeData, QModelIndex, Qt
from PyQt6.QtGui import QColor, QFont

from .store import PlaylistStore, is_refinement, split_query

ROW_MIME = "application/x-almp-playlist-rows"
PathRole = Qt.ItemDataRole.UserRole
SourceRowRole = Qt.ItemDataRole.UserRole + 1


class PlaylistModel(QAbstractListModel):
    def __init__(self, store=None, parent=None):
        super().__init__(parent)
        self.store = store if store is not None else PlaylistStore()
        self._rows = None            # None = everything shown; else sorted list of source rows
        self._words = []
        self._current = -1           # source row of the track that is playing
        self._bold = QFont()
        self._bold.setBold(True)
        self._accent = QColor("#19c8e6")
        self.queued = None           # callable(path) -> queue position or 0 (set by the window)

    # --- what is shown ---
    @property
    def filtered(self):
        return self._rows is not None

    @property
    def query_words(self):
        return list(self._words)

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.store.paths) if self._rows is None else len(self._rows)

    def source_row(self, view_row):
        if self._rows is None:
            return view_row if 0 <= view_row < len(self.store.paths) else -1
        return self._rows[view_row] if 0 <= view_row < len(self._rows) else -1

    def view_row(self, source_row):
        if self._rows is None:
            return source_row if 0 <= source_row < len(self.store.paths) else -1
        i = bisect.bisect_left(self._rows, source_row)
        return i if i < len(self._rows) and self._rows[i] == source_row else -1

    def path_at_view(self, view_row):
        s = self.source_row(view_row)
        return self.store.paths[s] if s >= 0 else None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        s = self.source_row(index.row())
        if s < 0:
            return None
        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.AccessibleTextRole:
            name = ntpath.basename(self.store.paths[s])
            if self.queued is not None:
                pos = self.queued(self.store.paths[s])
                if pos:
                    name = f"[next {pos}]  {name}" if pos > 1 else f"[next]  {name}"
            if role == Qt.ItemDataRole.AccessibleTextRole and s == self._current:
                return "Playing: " + name
            return name
        if role == Qt.ItemDataRole.ToolTipRole:
            return self.store.paths[s]
        if role == PathRole:
            return self.store.paths[s]
        if role == SourceRowRole:
            return s
        if s == self._current:
            if role == Qt.ItemDataRole.FontRole:
                return self._bold
            if role == Qt.ItemDataRole.ForegroundRole:
                return self._accent
        return None

    def flags(self, index):
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled if self._rows is None else Qt.ItemFlag.NoItemFlags
        if self._rows is None:
            base |= Qt.ItemFlag.ItemIsDragEnabled
        return base

    def set_accent(self, color):
        self._accent = QColor(color)
        self._emit_row(self._current)

    # --- the playing track ---
    @property
    def current(self):
        return self._current

    def set_current(self, source_row):
        old, self._current = self._current, source_row
        if old != source_row:
            self._emit_row(old)
            self._emit_row(source_row)

    def refresh_all(self):
        """Repaint every row on screen (cheap: the view only redraws what it shows)."""
        n = self.rowCount()
        if n:
            self.dataChanged.emit(self.index(0, 0), self.index(n - 1, 0))

    def refresh_path(self, path):
        """Repaint one row (for example after it was queued)."""
        s = self.store.index_of(path)
        if s >= 0:
            self._emit_row(s)

    def _emit_row(self, source_row):
        v = self.view_row(source_row) if source_row >= 0 else -1
        if v >= 0:
            ix = self.index(v, 0)
            self.dataChanged.emit(ix, ix)

    # --- changes ---
    def append_entries(self, entries):
        """Add entries (from store.make_entry) at the end. Returns how many were new."""
        store = self.store
        fresh = store.new_entries(entries)
        if not fresh:
            return 0
        start = len(store.paths)
        if self._rows is None:
            self.beginInsertRows(QModelIndex(), start, start + len(fresh) - 1)
            store.commit(fresh)
            self.endInsertRows()
        else:
            store.commit(fresh)
            new_rows = store.filter_rows(self._words, within=range(start, start + len(fresh)))
            if new_rows:
                v0 = len(self._rows)
                self.beginInsertRows(QModelIndex(), v0, v0 + len(new_rows) - 1)
                self._rows.extend(new_rows)
                self.endInsertRows()
        return len(fresh)

    def remove_source(self, source_row):
        """Remove one row of the playlist. Returns its path (or None)."""
        store = self.store
        if not (0 <= source_row < len(store.paths)):
            return None
        if self._rows is None:
            self.beginRemoveRows(QModelIndex(), source_row, source_row)
            path = store.remove_at(source_row)
            self._shift_current_after_remove(source_row)
            self.endRemoveRows()
            return path
        rows = self._rows
        v = bisect.bisect_left(rows, source_row)
        visible = v < len(rows) and rows[v] == source_row
        if visible:
            self.beginRemoveRows(QModelIndex(), v, v)
            del rows[v]
        path = store.remove_at(source_row)
        for i in range(v, len(rows)):           # later rows move up by one
            rows[i] -= 1
        self._shift_current_after_remove(source_row)
        if visible:
            self.endRemoveRows()
        return path

    def _shift_current_after_remove(self, source_row):
        if self._current == source_row:
            self._current = -1
        elif self._current > source_row:
            self._current -= 1

    def move_source(self, src, dst):
        """Move one playlist row (Move up / Move down / drag). Only when no search is active."""
        n = len(self.store.paths)
        if self._rows is not None or not (0 <= src < n) or not (0 <= dst < n) or src == dst:
            return False
        # Qt wants the destination as "insert before this row" in the old numbering.
        qt_dst = dst + 1 if dst > src else dst
        if not self.beginMoveRows(QModelIndex(), src, src, QModelIndex(), qt_dst):
            return False
        self.store.move(src, dst)
        cur = self._current
        if cur == src:
            self._current = dst
        elif src < cur <= dst:
            self._current = cur - 1
        elif dst <= cur < src:
            self._current = cur + 1
        self.endMoveRows()
        return True

    def moveRows(self, source_parent, source_row, count, destination_parent, destination_child):
        """Qt's own drag-and-drop move (one row at a time is all ALMP needs)."""
        if count != 1 or source_parent.isValid() or destination_parent.isValid():
            return False
        dst = destination_child - 1 if destination_child > source_row else destination_child
        return self.move_source(source_row, max(0, min(dst, len(self.store.paths) - 1)))

    def clear(self):
        self.beginResetModel()
        self.store.clear()
        self._rows = None if not self._words else []
        self._current = -1
        self.endResetModel()

    def reorder(self, order, expected_version=None):
        """Apply a new order (sorting). Refused if the playlist changed meanwhile."""
        if expected_version is not None and expected_version != self.store.version:
            return False
        cur_path = self.store.paths[self._current] if 0 <= self._current < len(self.store.paths) else None
        self.beginResetModel()
        self.store.reorder(order)
        if cur_path is not None:
            self._current = self.store.index_of(cur_path)
        if self._rows is not None:
            self._rows = self.store.filter_rows(self._words)
        self.endResetModel()
        return True

    # --- search ---
    def set_filter(self, text):
        """Show only rows whose name or folder contains every word. Returns the number shown."""
        words = split_query(text)
        if words == self._words:
            return self.rowCount()
        within = self._rows if (self._rows is not None and is_refinement(self._words, words)) else None
        self.beginResetModel()
        self._words = words
        self._rows = None if not words else self.store.filter_rows(words, within=within)
        self.endResetModel()
        return self.rowCount()

    # --- drag and drop inside the list ---
    def supportedDropActions(self):
        return Qt.DropAction.MoveAction | Qt.DropAction.CopyAction

    def supportedDragActions(self):
        return Qt.DropAction.MoveAction

    def mimeTypes(self):
        return [ROW_MIME]

    def mimeData(self, indexes):
        rows = sorted({self.source_row(i.row()) for i in indexes if i.isValid()})
        md = QMimeData()
        md.setData(ROW_MIME, QByteArray(",".join(str(r) for r in rows if r >= 0).encode("ascii")))
        return md

    def canDropMimeData(self, data, action, row, column, parent):
        return self._rows is None and data is not None and data.hasFormat(ROW_MIME)

    def dropMimeData(self, data, action, row, column, parent):
        if not self.canDropMimeData(data, action, row, column, parent):
            return False
        try:
            rows = [int(x) for x in bytes(data.data(ROW_MIME)).decode("ascii").split(",") if x]
        except ValueError:
            return False
        if len(rows) != 1:
            return False
        src = rows[0]
        if row < 0:
            row = parent.row() if parent.isValid() else len(self.store.paths)
        dst = row - 1 if row > src else row
        dst = max(0, min(dst, len(self.store.paths) - 1))
        self.move_source(src, dst)
        # Returning False tells the view not to delete anything afterwards (the move is done).
        return False
