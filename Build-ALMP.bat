@echo off
cd /d "%~dp0"
echo Build started %date% %time% > build.log
python --version >> build.log 2>&1
python -m nuitka --version >> build.log 2>&1
if not exist runtime\mpv-2.dll (echo ERROR: runtime\mpv-2.dll missing >> build.log & exit /b 1)
python -m nuitka --standalone --enable-plugin=pyqt6 --windows-console-mode=disable --lto=yes --windows-icon-from-ico=icon.ico --include-data-file=icon.ico=icon.ico --include-data-file=icon.png=icon.png --include-data-file=runtime/mpv-2.dll=runtime/mpv-2.dll --output-filename=ALMP.exe --assume-yes-for-downloads --company-name=Alexbed --product-name="Alexbed Light Media Player" --file-description="Alexbed Light Media Player" --file-version=8.0.0.0 --product-version=8.0.0.0 main.py >> build.log 2>&1
echo Build finished errorlevel %errorlevel% %date% %time% >> build.log
