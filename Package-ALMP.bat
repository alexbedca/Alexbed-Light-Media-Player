@echo off
setlocal
cd /d "%~dp0"
set "VER="
for /f "usebackq delims=" %%v in (`python tools\get_version.py`) do set "VER=%%v"
if not defined VER (echo ERROR: could not read the version from main.py & exit /b 1)
set "NAME=ALMP-v%VER%-Portable"
taskkill /im ALMP.exe /f >nul 2>&1
if not exist main.dist\ALMP.exe (echo ERROR: build first with Build-ALMP.bat & exit /b 1)
if exist release\%NAME% rmdir /s /q release\%NAME%
if exist release\%NAME%.zip del release\%NAME%.zip
mkdir release\%NAME%
xcopy main.dist release\%NAME% /e /i /q /y >nul
copy /y LICENSE release\%NAME% >nul
copy /y README.txt release\%NAME% >nul
copy /y THIRD-PARTY-NOTICES.txt release\%NAME% >nul
copy /y Set-ALMP-Defaults.bat release\%NAME% >nul
copy /y Remove-ALMP-Defaults.bat release\%NAME% >nul
xcopy LICENSES release\%NAME%\LICENSES /e /i /q /y >nul
if exist BUILD-INFO.txt copy /y BUILD-INFO.txt release\%NAME% >nul
powershell -NoProfile -Command "Compress-Archive -Path 'release\%NAME%' -DestinationPath 'release\%NAME%.zip' -CompressionLevel Optimal"
powershell -NoProfile -Command "(Get-FileHash 'release\%NAME%.zip' -Algorithm SHA256).Hash + '  %NAME%.zip'" > release\%NAME%.sha256.txt
echo Packaged %date% %time% > package.log
dir release >> package.log
type release\%NAME%.sha256.txt >> package.log
