@echo off
setlocal EnableExtensions
title ALMP - Set as default media player

REM =====================================================================
REM  Put this file in the SAME folder as ALMP.exe, then double-click it.
REM  No editing needed - it finds ALMP.exe by itself.
REM  No administrator rights needed (registers for the current user only).
REM =====================================================================

set "ALMP=%~dp0ALMP.exe"
if not exist "%ALMP%" goto :notfound

echo.
echo  ALMP will be set up from this location:
echo.
echo     "%ALMP%"
echo.
echo  IMPORTANT: this folder must be on THIS computer (for example in
echo  Documents), not on the USB stick. If you move the folder later,
echo  run this file again.
echo.
choice /c YN /m "Continue"
if errorlevel 2 goto :eof

REM ---------------- File types ----------------
set "EXTS="
REM Audio
set "EXTS=%EXTS% .mp3 .flac .wav .aac .m4a .ogg .oga .opus .wma .aiff"
set "EXTS=%EXTS% .aif .aifc .ape .alac .amr .awb .mp2 .mp1 .mpa .ac3"
set "EXTS=%EXTS% .eac3 .dts .wv .mka .mpc .tta .spx .caf .au .snd"
set "EXTS=%EXTS% .m4r .m4b .weba .ra .dsf .dff"
REM Video
set "EXTS=%EXTS% .mp4 .mkv .avi .mov .wmv .webm .mpeg .mpg .mpe .m4v"
set "EXTS=%EXTS% .3gp .3g2 .ts .m2ts .mts .m2t .tp .trp .vob .ogv"
set "EXTS=%EXTS% .ogm .flv .f4v .rm .rmvb .asf .divx .xvid .dv .mxf"
set "EXTS=%EXTS% .qt .wtv .dvr-ms .amv .nsv .ivf"
REM Playlists
set "EXTS=%EXTS% .m3u .m3u8 .pls"

echo.
echo  Registering ALMP, please wait...

set "FAIL=0"
set "CLS=HKCU\Software\Classes"

REM ---- ProgID (how Windows opens a file with ALMP) ----
reg add "%CLS%\ALMP.Media" /ve /d "ALMP Media File" /f >nul 2>&1 || set "FAIL=1"
reg add "%CLS%\ALMP.Media\DefaultIcon" /ve /d "\"%ALMP%\",0" /f >nul 2>&1 || set "FAIL=1"
reg add "%CLS%\ALMP.Media\shell\open\command" /ve /d "\"%ALMP%\" \"%%1\"" /f >nul 2>&1 || set "FAIL=1"
REM "Player" lets you open many selected files at once (not only 15); ALMP collects them in one window.
reg add "%CLS%\ALMP.Media\shell\open" /v MultiSelectModel /d Player /f >nul 2>&1 || set "FAIL=1"

REM ---- Application entry ("Open with" list) ----
reg add "%CLS%\Applications\ALMP.exe" /v FriendlyAppName /d "ALMP Media Player" /f >nul 2>&1 || set "FAIL=1"
reg add "%CLS%\Applications\ALMP.exe\shell\open\command" /ve /d "\"%ALMP%\" \"%%1\"" /f >nul 2>&1 || set "FAIL=1"
reg add "%CLS%\Applications\ALMP.exe\shell\open" /v MultiSelectModel /d Player /f >nul 2>&1 || set "FAIL=1"

REM ---- Capabilities (makes ALMP appear in Settings > Default apps) ----
reg add "HKCU\Software\ALMP\Capabilities" /v ApplicationName /d "ALMP" /f >nul 2>&1 || set "FAIL=1"
reg add "HKCU\Software\ALMP\Capabilities" /v ApplicationDescription /d "Alexbed Light Media Player" /f >nul 2>&1 || set "FAIL=1"
reg add "HKCU\Software\RegisteredApplications" /v ALMP /d "Software\ALMP\Capabilities" /f >nul 2>&1 || set "FAIL=1"

REM ---- Every file type ----
for %%E in (%EXTS%) do call :addext %%E

if "%FAIL%"=="1" goto :failed

echo.
echo  ===============================================================
echo   ALMP is registered.  ONE LAST STEP (Windows requires you to
echo   confirm it yourself - no program is allowed to do it for you):
echo.
echo   The Windows "Default apps" page will open on ALMP.
echo     - Windows 11: click the "Set default" button at the top.
echo       (If you only see a list, click each file type and choose
echo        ALMP.  Start with .mp3 and .mp4.)
echo     - Windows 10: click "Set this program as default".
echo  ===============================================================
echo.
pause
start "" "ms-settings:defaultapps?registeredAppUser=ALMP"
goto :eof

:addext
reg add "%CLS%\%~1\OpenWithProgids" /v ALMP.Media /t REG_NONE /f >nul 2>&1 || set "FAIL=1"
reg add "%CLS%\Applications\ALMP.exe\SupportedTypes" /v %~1 /d "" /f >nul 2>&1 || set "FAIL=1"
reg add "HKCU\Software\ALMP\Capabilities\FileAssociations" /v %~1 /d ALMP.Media /f >nul 2>&1 || set "FAIL=1"
goto :eof

:notfound
echo.
echo  ERROR: ALMP.exe was not found next to this file.
echo.
echo  Please copy this file INTO the same folder as ALMP.exe
echo  and run it again.
echo.
pause
exit /b 1

:failed
echo.
echo  Something went wrong while registering ALMP.
echo  Please close this window and try again.
echo.
pause
exit /b 1
