"""M3U / PLS reading and writing, including old "ANSI" playlists from Windows tools."""
import codecs

import main


def _touch(folder, name):
    p = folder / name
    p.write_bytes(b"")
    return p


def test_reads_utf8_with_and_without_bom(tmp_path):
    song = _touch(tmp_path, "Café del Mar.mp3")
    for data in (f"#EXTM3U\n{song}\n".encode("utf-8"),
                 codecs.BOM_UTF8 + f"#EXTM3U\n{song}\n".encode("utf-8")):
        pl = tmp_path / "list.m3u"
        pl.write_bytes(data)
        assert main.read_playlist_file(str(pl)) == [str(song)]


def test_ansi_playlist_falls_back_instead_of_dropping_names(tmp_path):
    song = _touch(tmp_path, "Señorita Müller.mp3")
    pl = tmp_path / "old.m3u"
    pl.write_bytes(("#EXTM3U\n#EXTINF:123,Test\n" + song.name + "\r\n").encode("cp1252"))
    # The bytes are not valid UTF-8, so the fallback code page must be used.
    assert main.read_playlist_file(str(pl), fallback_encoding="cp1252") == [str(song)]


def test_decode_prefers_utf8_and_handles_utf16():
    text = "Ünïcödé.mp3\n"
    assert main.decode_playlist_bytes(text.encode("utf-8"), "cp1252") == text
    assert main.decode_playlist_bytes(text.encode("utf-16"), "cp1252") == text
    assert main.decode_playlist_bytes(text.encode("cp1252"), "cp1252") == text


def test_unknown_fallback_encoding_still_decodes():
    raw = "Señor.mp3".encode("cp1252")
    assert main.decode_playlist_bytes(raw, "no-such-codec") == "Señor.mp3"


def test_relative_paths_file_uris_and_missing_files(tmp_path):
    sub = tmp_path / "music"
    sub.mkdir()
    a = _touch(sub, "a b.mp3")
    b = _touch(sub, "b.flac")
    pl = tmp_path / "mix.m3u8"
    uri = a.as_uri()                      # file:///.../a%20b.mp3 (file:///C:/... on Windows)
    pl.write_text(f"#EXTM3U\n{uri}\nmusic/b.flac\nmissing.mp3\nnotes.txt\n", encoding="utf-8")
    assert main.read_playlist_file(str(pl)) == [str(a), str(b)]


def test_pls_files(tmp_path):
    a = _touch(tmp_path, "one.mp3")
    pl = tmp_path / "radio.pls"
    pl.write_text(f"[playlist]\nFile1={a}\nTitle1=One\nNumberOfEntries=1\n", encoding="utf-8")
    assert main.read_playlist_file(str(pl)) == [str(a)]


def test_unreadable_playlist_returns_empty(tmp_path):
    assert main.read_playlist_file(str(tmp_path / "does-not-exist.m3u")) == []


def test_write_m3u_has_bom_and_m3u8_has_none(tmp_path):
    files = [str(tmp_path / "Café.mp3"), str(tmp_path / "Ñandú.flac")]
    m3u = tmp_path / "x.m3u"
    m3u8 = tmp_path / "x.m3u8"
    main.write_playlist_file(str(m3u), files)
    main.write_playlist_file(str(m3u8), files)
    assert m3u.read_bytes().startswith(codecs.BOM_UTF8 + b"#EXTM3U\n")
    assert m3u8.read_bytes().startswith(b"#EXTM3U\n")
    assert m3u8.read_text(encoding="utf-8").splitlines()[1:] == files


def test_round_trip(tmp_path):
    files = [str(_touch(tmp_path, n)) for n in ("Été.mp3", "Øre.ogg", "plain.wav")]
    for name in ("r.m3u", "r.m3u8"):
        pl = tmp_path / name
        main.write_playlist_file(str(pl), files)
        assert main.read_playlist_file(str(pl)) == files


def test_windows_style_file_uris():
    to_path = main._playlist_entry_to_path
    assert to_path("file:///C:/Music/a%20b.mp3", "X").replace("\\", "/") == "C:/Music/a b.mp3"
    assert to_path("file://server/share/x.mp3", "X").replace("\\", "/") == "//server/share/x.mp3"
    assert to_path("FILE://localhost/C:/M/%C3%A9.mp3", "X").replace("\\", "/") == "C:/M/é.mp3"
