@echo off
setlocal EnableExtensions
title ALMP - Remove ALMP from Windows (uninstall)
echo.
echo  This undoes everything ALMP has set up in Windows for your account:
echo    - ALMP in the "Open with" and "Default apps" lists
echo    - "Run at Startup" (if you had turned it on)
echo.
echo  Your music and video files are NOT touched.
echo  Please close ALMP before you continue.
echo.
choice /c YN /m "Continue"
if errorlevel 2 goto :eof

set "CLS=HKCU\Software\Classes"
set "EXTS="
set "EXTS=%EXTS% .mp3 .flac .wav .aac .m4a .ogg .oga .opus .wma .aiff"
set "EXTS=%EXTS% .aif .aifc .ape .alac .amr .awb .mp2 .mp1 .mpa .ac3"
set "EXTS=%EXTS% .eac3 .dts .wv .mka .mpc .tta .spx .caf .au .snd"
set "EXTS=%EXTS% .m4r .m4b .weba .ra .dsf .dff"
set "EXTS=%EXTS% .mp4 .mkv .avi .mov .wmv .webm .mpeg .mpg .mpe .m4v"
set "EXTS=%EXTS% .3gp .3g2 .ts .m2ts .mts .m2t .tp .trp .vob .ogv"
set "EXTS=%EXTS% .ogm .flv .f4v .rm .rmvb .asf .divx .xvid .dv .mxf"
set "EXTS=%EXTS% .qt .wtv .dvr-ms .amv .nsv .ivf"
set "EXTS=%EXTS% .m3u .m3u8 .pls"

REM ---- File associations ----
for %%E in (%EXTS%) do reg delete "%CLS%\%%E\OpenWithProgids" /v ALMP.Media /f >nul 2>&1
reg delete "%CLS%\ALMP.Media" /f >nul 2>&1
reg delete "%CLS%\Applications\ALMP.exe" /f >nul 2>&1
reg delete "HKCU\Software\ALMP" /f >nul 2>&1
reg delete "HKCU\Software\RegisteredApplications" /v ALMP /f >nul 2>&1

REM ---- Run at Startup (current shortcut, and the registry entry used by old versions) ----
if defined APPDATA if exist "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ALMP.lnk" del /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ALMP.lnk" >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v AlexbedLightMediaPlayer /f >nul 2>&1

echo.
echo  ALMP also keeps a few small files for your account:
echo    - settings (volume, shuffle, interface size...) in %%APPDATA%%\ALMP
echo    - an error log (almp.log), if there ever was an error, in %%LOCALAPPDATA%%\ALMP
echo  Keep them if you plan to use ALMP again.
echo.
choice /c YN /m "Also delete these ALMP settings and log files"
if errorlevel 2 goto :done

REM Only ALMP's own files are deleted, by name; the folders are removed only if they are then empty.
if defined APPDATA if exist "%APPDATA%\ALMP\" (
    for %%F in (settings.json startup_target.txt resume.json last_playlist.json last_playlist.tmp) do (
        if exist "%APPDATA%\ALMP\%%F" del /q "%APPDATA%\ALMP\%%F" >nul 2>&1
    )
    rmdir "%APPDATA%\ALMP" >nul 2>&1
)
if defined LOCALAPPDATA if exist "%LOCALAPPDATA%\ALMP\" (
    for %%F in (almp.log almp.log.1) do (
        if exist "%LOCALAPPDATA%\ALMP\%%F" del /q "%LOCALAPPDATA%\ALMP\%%F" >nul 2>&1
    )
    rmdir "%LOCALAPPDATA%\ALMP" >nul 2>&1
)
echo  Settings and log files deleted.

:done
echo.
echo  Done. If Windows still lists ALMP as the default for some files,
echo  open Settings ^> Apps ^> Default apps and pick another player.
echo.
echo  To remove ALMP completely, now delete the ALMP folder itself.
echo.
pause
