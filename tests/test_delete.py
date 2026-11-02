"""Delete safety: the Recycle Bin is only promised where Windows really has one, and a failed
Recycle Bin call never turns into a silent permanent delete. Windows calls are mocked."""
import ctypes
import os
import types

import pytest

import main


@pytest.mark.parametrize("path,root", [
    ("C:\\Music\\song.mp3", "C:\\"),
    ("e:/Videos/x.mp4", "e:\\"),
    ("\\\\server\\share\\a\\b.mp3", "\\\\server\\share\\"),
    ("relative\\file.mp3", None),
])
def test_drive_root(path, root):
    assert main.drive_root(path) == root


@pytest.mark.parametrize("drive_type,expected", [
    (main.DRIVE_FIXED, True),
    (main.DRIVE_REMOVABLE, False),     # USB stick, SD card
    (main.DRIVE_REMOTE, False),        # network drive
    (main.DRIVE_CDROM, False),
    (main.DRIVE_RAMDISK, False),
    (main.DRIVE_UNKNOWN, False),
    (main.DRIVE_NO_ROOT_DIR, False),
])
def test_recycle_bin_decision(drive_type, expected):
    assert main.recycle_bin_available("X:\\f.mp3", platform="win32",
                                      drive_type_func=lambda p: drive_type) is expected


def test_never_promise_recycle_bin_off_windows():
    assert main.recycle_bin_available("/home/a.mp3", platform="linux",
                                      drive_type_func=lambda p: main.DRIVE_FIXED) is False


def test_flags():
    soft = main.recycle_flags(permanent=False)
    assert soft & main.FOF_ALLOWUNDO and soft & main.FOF_WANTNUKEWARNING
    hard = main.recycle_flags(permanent=True)
    assert not hard & main.FOF_ALLOWUNDO


@pytest.fixture
def fake_windows(monkeypatch):
    """Pretend to be Windows, with GetDriveTypeW and SHFileOperationW replaced."""
    calls = {"drive": [], "shfileop": []}
    behaviour = {"drive_type": main.DRIVE_FIXED, "shfileop": None}

    def GetDriveTypeW(root):
        calls["drive"].append(root.value)
        return behaviour["drive_type"]

    def SHFileOperationW(byref_op):
        op = byref_op._obj
        calls["shfileop"].append(op.fFlags)
        return behaviour["shfileop"](op)

    fake_ctypes = types.SimpleNamespace(
        Structure=ctypes.Structure, c_uint16=ctypes.c_uint16, c_void_p=ctypes.c_void_p,
        c_wchar_p=ctypes.c_wchar_p, byref=ctypes.byref,
        windll=types.SimpleNamespace(kernel32=types.SimpleNamespace(GetDriveTypeW=GetDriveTypeW),
                                     shell32=types.SimpleNamespace(SHFileOperationW=SHFileOperationW)))
    import ctypes.wintypes as wintypes
    monkeypatch.setattr(main, "ctypes", fake_ctypes, raising=False)
    monkeypatch.setattr(main, "wintypes", wintypes, raising=False)
    monkeypatch.setattr(main.sys, "platform", "win32")
    monkeypatch.setattr(main.os.path, "abspath", lambda p: p)
    return calls, behaviour


def test_get_drive_type_uses_the_drive_root(fake_windows):
    calls, behaviour = fake_windows
    behaviour["drive_type"] = main.DRIVE_REMOVABLE
    assert main.get_drive_type("F:\\Holiday\\video.mp4") == main.DRIVE_REMOVABLE
    assert calls["drive"] == ["F:\\"]
    assert main.recycle_bin_available("F:\\Holiday\\video.mp4") is False


def test_unc_paths_count_as_network_without_asking_windows(fake_windows):
    calls, _ = fake_windows
    assert main.get_drive_type("\\\\nas\\music\\a.mp3") == main.DRIVE_REMOTE
    assert calls["drive"] == []


def test_failed_recycle_call_leaves_the_file_alone(fake_windows, tmp_path):
    calls, behaviour = fake_windows
    f = tmp_path / "keep.mp3"
    f.write_bytes(b"x")

    def boom(op):
        raise OSError("shell32 not available")

    behaviour["shfileop"] = boom
    assert main.send_to_recycle_bin(str(f)) == main.DELETE_FAILED
    assert f.exists()                         # the old code would have used os.remove() here


def test_recycle_reports_failure_when_windows_returns_an_error(fake_windows, tmp_path):
    _, behaviour = fake_windows
    f = tmp_path / "keep.mp3"
    f.write_bytes(b"x")
    behaviour["shfileop"] = lambda op: 0x78
    assert main.send_to_recycle_bin(str(f)) == main.DELETE_FAILED
    assert f.exists()


def test_recycle_cancelled_by_user(fake_windows, tmp_path):
    _, behaviour = fake_windows
    f = tmp_path / "keep.mp3"
    f.write_bytes(b"x")

    def user_said_no(op):
        op.fAnyOperationsAborted = True
        return 0

    behaviour["shfileop"] = user_said_no
    assert main.send_to_recycle_bin(str(f)) == main.DELETE_CANCELLED
    assert f.exists()


def test_recycle_ok_uses_safe_flags(fake_windows, tmp_path):
    calls, behaviour = fake_windows
    f = tmp_path / "gone.mp3"
    f.write_bytes(b"x")

    def recycle(op):
        os.remove(op.pFrom.rstrip("\0"))
        return 0

    behaviour["shfileop"] = recycle
    assert main.send_to_recycle_bin(str(f), hwnd=1234) == main.DELETE_OK
    assert calls["shfileop"] == [main.recycle_flags(False)]


def test_non_windows_never_deletes_without_permanent_consent(monkeypatch, tmp_path):
    monkeypatch.setattr(main.sys, "platform", "linux")
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    assert main.send_to_recycle_bin(str(f)) == main.DELETE_FAILED
    assert f.exists()
    assert main.send_to_recycle_bin(str(f), permanent=True) == main.DELETE_OK
    assert not f.exists()
