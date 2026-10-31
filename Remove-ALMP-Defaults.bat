@echo off
setlocal EnableExtensions
title ALMP - Remove default media player registration
echo.
echo  This removes ALMP from Windows' "Open with" and "Default apps" lists.
echo  (Your files and the ALMP folder are not touched.)
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

for %%E in (%EXTS%) do reg delete "%CLS%\%%E\OpenWithProgids" /v ALMP.Media /f >nul 2>&1
reg delete "%CLS%\ALMP.Media" /f >nul 2>&1
reg delete "%CLS%\Applications\ALMP.exe" /f >nul 2>&1
reg delete "HKCU\Software\ALMP" /f >nul 2>&1
reg delete "HKCU\Software\RegisteredApplications" /v ALMP /f >nul 2>&1

echo.
echo  Done. If Windows still lists ALMP as the default for some files,
echo  open Settings ^> Apps ^> Default apps and pick another player.
echo.
pause
