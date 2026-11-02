@echo off
setlocal
cd /d "%~dp0"
echo Build started %date% %time% > build.log
python --version >> build.log 2>&1
python -m nuitka --version >> build.log 2>&1
if not exist runtime\mpv-2.dll (echo ERROR: runtime\mpv-2.dll missing >> build.log & exit /b 1)

REM The version is read from __version__ in almp\__init__.py (plain X.Y.Z only), so it is set in one place.
set "VER="
for /f "usebackq delims=" %%v in (`python tools\get_version.py`) do set "VER=%%v"
if not defined VER (echo ERROR: could not read the version from almp\__init__.py >> build.log & exit /b 1)
echo Version %VER% >> build.log

python -m nuitka --standalone --enable-plugin=pyqt6 --windows-console-mode=disable --lto=yes --windows-icon-from-ico=icon.ico --include-data-file=icon.ico=icon.ico --include-data-file=icon.png=icon.png --include-data-file=runtime/mpv-2.dll=runtime/mpv-2.dll --include-package=almp --output-filename=ALMP.exe --assume-yes-for-downloads --company-name=Alexbed --product-name="Alexbed Light Media Player" --file-description="Alexbed Light Media Player" --file-version=%VER%.0 --product-version=%VER%.0 main.py >> build.log 2>&1
set "RC=%errorlevel%"
echo Build finished errorlevel %RC% %date% %time% >> build.log
exit /b %RC%
