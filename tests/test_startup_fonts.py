"""Start-up speed on PCs with many fonts (see docs/release-notes and tools/bench_startup.py).

Qt searches every installed font when asked for a weight or a character the UI font does not
have. With 9,223 fonts that cost 6 to 70 s before the window appeared. These tests keep the
settings that avoid that search."""
from almp import app, theme


def test_windows_uses_the_quick_gdi_font_list():
    assert app.qt_platform_override({}, platform="win32") == "windows:fontengine=gdi"


def test_users_own_qt_platform_setting_wins():
    assert app.qt_platform_override({"QT_QPA_PLATFORM": "windows:darkmode=1"}, platform="win32") is None


def test_other_systems_are_left_alone():
    assert app.qt_platform_override({}, platform="linux") is None
    assert app.qt_platform_override({}, platform="darwin") is None


def test_style_sheets_have_no_placeholders_left():
    for hc in (False, True):
        sheet = theme.stylesheet(hc)
        assert "{" + "SEMIBOLD}" not in sheet
        assert "{" + "UI_FONT_FAMILY}" not in sheet


def test_semibold_names_its_own_face_on_windows(monkeypatch):
    # "Segoe UI" only has regular and bold; weight 600 must come from "Segoe UI Semibold".
    monkeypatch.setattr(theme, "SEMIBOLD", 'font-family: "Segoe UI Semibold"; font-weight: 600')
    for hc in (False, True):
        sheet = theme.stylesheet(hc)
        assert sheet.count("font-weight: 600") == sheet.count('font-family: "Segoe UI Semibold"; font-weight: 600')
        assert sheet.count("font-weight: 600") >= 4 + (1 if hc else 0)


def test_ui_text_has_no_check_mark_character():
    # The check mark U+2713 is not in Segoe UI; drawing it made Qt search all fonts (6 s) the
    # first time the audio/subtitle menu opened.
    from pathlib import Path
    src = Path(app.__file__).with_name("ui.py").read_text(encoding="utf-8")
    assert "\u2713" not in src
