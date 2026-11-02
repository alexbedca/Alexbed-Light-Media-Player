"""Playlist data (store), natural sort, the search filter and the streaming folder scan.
No Qt needed: these are the parts that make 100,000+ files fast."""
import os
import random

import pytest

from almp import scanner
from almp.naturalsort import natural_key, natural_name_key, natural_path_key, natural_sorted
from almp.store import PlaylistStore, is_refinement, make_entry, split_query

# --- natural sort -------------------------------------------------------------


def test_numbers_sort_as_numbers():
    names = ["Track 10.mp3", "track 2.mp3", "Track 1.mp3", "Track B.mp3", "Track 02b.mp3", "track 11.mp3"]
    assert natural_sorted(names) == ["Track 1.mp3", "track 2.mp3", "Track 02b.mp3", "Track 10.mp3",
                                     "track 11.mp3", "Track B.mp3"]


def test_case_does_not_matter_but_order_is_stable():
    assert natural_key("ABC") < natural_key("abd")
    assert natural_key("abc") != natural_key("ABC")          # still a fixed order between the two
    assert sorted(["b", "A", "a", "B"], key=natural_key)[:2] in (["A", "a"], ["a", "A"])


def test_leading_zeros_and_long_numbers():
    assert natural_sorted(["1", "01", "001"]) == ["001", "01", "1"]
    big = ["x 123456789012345678901", "x 2"]
    assert natural_sorted(big)[0] == "x 2"


def test_shorter_name_first():
    assert natural_sorted(["abc def", "abc"]) == ["abc", "abc def"]


def test_path_sort_goes_folder_by_folder():
    paths = [r"C:\M\Album 10\01.mp3", r"C:\M\Album 2\10.mp3", r"C:\M\Album 2\9.mp3", r"C:\M\Album 2 (live)\1.mp3"]
    assert sorted(paths, key=natural_path_key) == [r"C:\M\Album 2\9.mp3", r"C:\M\Album 2\10.mp3",
                                                    r"C:\M\Album 2 (live)\1.mp3", r"C:\M\Album 10\01.mp3"]


def test_both_slash_kinds_are_folder_separators():
    assert natural_path_key("C:/a/b.mp3") == natural_path_key("C:\\a\\b.mp3")


def test_name_sort_ignores_folder_first():
    paths = [r"C:\Z\a 2.mp3", r"C:\A\a 10.mp3", r"C:\B\a 1.mp3"]
    assert sorted(paths, key=natural_name_key) == [r"C:\B\a 1.mp3", r"C:\Z\a 2.mp3", r"C:\A\a 10.mp3"]


# --- store --------------------------------------------------------------------


def _paths(n):
    return [f"D:\\Music\\Artist {i // 100}\\Album\\{i % 100 + 1:02d} - Song {i}.mp3" for i in range(n)]


def test_duplicates_are_skipped_but_same_name_elsewhere_is_kept():
    s = PlaylistStore(normcase=lambda p: p.lower())
    assert s.extend([r"C:\a\x.mp3", r"C:\A\X.MP3", r"C:\b\x.mp3"]) == 2
    assert s.paths == [r"C:\a\x.mp3", r"C:\b\x.mp3"]
    assert s.contains(r"c:\A\x.mp3")
    assert s.extend([r"C:\a\x.mp3"]) == 0


def test_duplicates_inside_one_batch():
    s = PlaylistStore()
    entries = [make_entry("/m/a.mp3"), make_entry("/m/a.mp3"), make_entry("/m/b.mp3")]
    fresh = s.new_entries(entries)
    assert [e[0] for e in fresh] == ["/m/a.mp3", "/m/b.mp3"]


def test_remove_and_move_keep_search_in_step():
    s = PlaylistStore()
    s.extend(["/m/one.mp3", "/m/two.mp3", "/m/three.mp3"])
    v = s.version
    assert s.remove_at(1) == "/m/two.mp3"
    assert not s.contains("/m/two.mp3")
    assert s.version != v
    assert s.move(0, 1)
    assert s.paths == ["/m/three.mp3", "/m/one.mp3"]
    assert s.filter_rows(["one"]) == [1]
    assert s.extend(["/m/two.mp3"]) == 1         # can be added again after removal


def test_move_rejects_bad_rows():
    s = PlaylistStore()
    s.extend(["/a.mp3", "/b.mp3"])
    assert not s.move(0, 0)
    assert not s.move(-1, 1)
    assert not s.move(0, 5)


def test_reorder_needs_a_permutation():
    s = PlaylistStore()
    s.extend(["/a.mp3", "/b.mp3", "/c.mp3"])
    s.reorder([2, 0, 1])
    assert s.paths == ["/c.mp3", "/a.mp3", "/b.mp3"]
    assert s.filter_rows(["a"]) == [1]
    with pytest.raises(ValueError):
        s.reorder([0, 0, 1])


def test_filter_matches_name_and_folder_every_word():
    s = PlaylistStore()
    s.extend([r"C:\Jazz\Blue Moon.mp3", r"C:\Rock\Blue Sky.mp3", r"C:\Jazz\Night.mp3"])
    assert s.filter_rows(split_query("blue")) == [0, 1]
    assert s.filter_rows(split_query("JAZZ")) == [0, 2]
    assert s.filter_rows(split_query("blue jazz")) == [0]
    assert s.filter_rows(split_query("   ")) == [0, 1, 2]
    assert s.filter_rows(split_query("zzz")) == []


def test_filter_never_matches_across_name_and_folder():
    s = PlaylistStore()
    s.extend([r"C:\ab\cd.mp3"])
    assert s.filter_rows(["mp3ab"]) == []


def test_refinement_search_gives_the_same_result():
    rng = random.Random(3)
    words = ["love", "night", "blue", "moon", "river"]
    s = PlaylistStore()
    s.extend([f"/m/{rng.choice(words)} {rng.choice(words)} {i}.mp3" for i in range(3000)])
    first = s.filter_rows(split_query("lo"))
    assert is_refinement(["lo"], ["lov"])
    assert is_refinement(["lo"], ["lo", "moon"])
    assert not is_refinement(["love"], ["lo"])
    assert not is_refinement([], ["x"])
    narrowed = s.filter_rows(split_query("lov moon"), within=first)
    assert narrowed == s.filter_rows(split_query("lov moon"))


def test_index_of_with_hint_and_key():
    s = PlaylistStore()
    s.extend(_paths(50))
    p = s.paths[30]
    assert s.index_of(p, hint=30) == 30
    assert s.index_of(p, hint=3) == 30
    assert s.index_of("/nope") == -1
    assert s.index_of_key(make_entry(p)[1]) == 30


def test_store_handles_100k_quickly():
    """A smoke check, not a benchmark (see tools/bench_playlist.py for numbers)."""
    import time
    s = PlaylistStore()
    entries = [make_entry(p) for p in _paths(100_000)]
    s.commit(s.new_entries(entries))
    assert len(s) == 100_000
    t = time.perf_counter()
    rows = s.filter_rows(split_query("song 9999"))
    assert time.perf_counter() - t < 2.0          # generous: slow CI machines
    assert s.paths[rows[0]].endswith("Song 9999.mp3")


# --- streaming scan -------------------------------------------------------------


def _make_tree(root):
    files = ["b/10.mp3", "b/9.mp3", "a/2.flac", "a/sub/1.mp3", "a/10.ogg", "z.mp4", "notes.txt",
             "$RECYCLE.BIN/x.mp3", "System Volume Information/y.mp3", "a/cover.jpg"]
    for f in files:
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")
    return root


def test_iter_folder_natural_order_and_skips(tmp_path):
    _make_tree(tmp_path)
    got = [os.path.relpath(p, tmp_path).replace(os.sep, "/") for p in scanner.iter_folder(str(tmp_path))]
    assert got == ["a/2.flac", "a/10.ogg", "a/sub/1.mp3", "b/9.mp3", "b/10.mp3", "z.mp4"]


def test_iter_folder_order_equals_sorting_all_paths(tmp_path):
    rng = random.Random(7)
    for i in range(300):
        d = tmp_path / f"Album {rng.randint(1, 12)}" / ("CD 2" if i % 7 == 0 else "")
        d.mkdir(parents=True, exist_ok=True)
        (d / f"Track {rng.randint(1, 40)} v{i}.mp3").write_bytes(b"")
    walked = list(scanner.iter_folder(str(tmp_path)))
    assert walked == sorted(walked, key=natural_path_key)
    assert len(walked) == 300


def test_iter_targets_singles_first_then_folders_and_playlists(tmp_path):
    _make_tree(tmp_path)
    single = tmp_path / "single 2.mp3"
    single.write_bytes(b"")
    single1 = tmp_path / "single 10.mp3"
    single1.write_bytes(b"")
    pl = tmp_path / "list.m3u8"
    pl.write_text(f"#EXTM3U\n{tmp_path / 'z.mp4'}\nmissing.mp3\n", encoding="utf-8")
    got = list(scanner.iter_targets([str(single1), str(tmp_path / "b"), str(pl), str(single), ""]))
    names = [os.path.basename(p) for p in got]
    assert names == ["single 2.mp3", "single 10.mp3", "9.mp3", "10.mp3", "z.mp4"]


def test_scan_stops_when_asked(tmp_path):
    for i in range(50):
        (tmp_path / f"{i}.mp3").write_bytes(b"")
    seen = []

    def stop():
        return len(seen) >= 5

    for p in scanner.iter_folder(str(tmp_path), stop):
        seen.append(p)
    assert len(seen) == 5


def test_unreadable_folder_is_skipped(tmp_path, monkeypatch):
    real = os.scandir

    def fake_scandir(path):
        if str(path).endswith("locked"):
            raise PermissionError("no")
        return real(path)

    (tmp_path / "locked").mkdir()
    (tmp_path / "ok.mp3").write_bytes(b"")
    monkeypatch.setattr(scanner.os, "scandir", fake_scandir)
    assert [os.path.basename(p) for p in scanner.iter_folder(str(tmp_path))] == ["ok.mp3"]


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_first_file_is_handed_over_at_once_then_batches(tmp_path):
    for i in range(25):
        (tmp_path / f"{i:03d}.mp3").write_bytes(b"")
    clock = FakeClock()
    batches = []
    total = scanner.scan_in_batches([str(tmp_path)], batches.append, max_items=10, interval_s=999, clock=clock)
    assert total == 25
    assert [len(b) for b in batches] == [1, 10, 10, 4]
    assert batches[0][0][0].endswith("000.mp3")
    path, key, search = batches[0][0]
    assert key == make_entry(path)[1] and "000.mp3" in search


def test_batches_also_go_out_on_time():
    clock = FakeClock()
    timer = scanner.BatchTimer(max_items=1000, interval_s=0.1, clock=clock)
    assert timer.due(1)              # first one at once
    assert not timer.due(5)
    clock.t = 0.2
    assert timer.due(5)
    assert not timer.due(0)
