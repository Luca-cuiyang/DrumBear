@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "LOG=C:\DBscore\package_win.log"
set "SOURCE_BASE="
set "SUCCESS=0"
> "%LOG%" echo === DB Score Windows package ===
>> "%LOG%" echo START=%DATE% %TIME%

taskkill /f /im DBScore5.exe >nul 2>&1

for /d %%D in ("C:\Mac\Home\Desktop\DB score*-v*") do set "SOURCE_BASE=%%~fD"
if not defined SOURCE_BASE (
  >> "%LOG%" echo SOURCE_NOT_FOUND
  goto :fail
)

set "SOURCE=!SOURCE_BASE!\DB score"
>> "%LOG%" echo SOURCE=!SOURCE!
robocopy "!SOURCE!" C:\DBscore /E /XD "!SOURCE!\applebuild" "!SOURCE!\builds" "!SOURCE!\.git" "!SOURCE!\.github" /NFL /NDL /NJH /NJS /NC /NS /NP >> "%LOG%" 2>&1
set "ROBOCOPY_EXIT=!ERRORLEVEL!"
if !ROBOCOPY_EXIT! GEQ 8 (
  >> "%LOG%" echo RobocopyExit=!ROBOCOPY_EXIT!
  goto :fail
)
if exist C:\DBscore\applebuild rmdir /s /q C:\DBscore\applebuild
if exist C:\DBscore\builds rmdir /s /q C:\DBscore\builds

call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if errorlevel 1 (
  >> "%LOG%" echo VcVarsExit=1
  goto :fail
)
set "PATH=C:\Qt\6.10.2\msvc2022_64\bin;C:\Mac\Home\.dbstudio-build-tools\WiX314;%PATH%"

cd /d C:\DBscore\build
if errorlevel 1 goto :fail
cmake . -U CPACK_WIX_PRODUCT_GUID -U CPACK_WIX_UPGRADE_GUID -DLIB_ARCH=x86_64 -DMUE_RUN_WINDEPLOYQT=ON -DMUE_WINDEPLOY_QML_DIR=C:/DBscore/buildscripts/packaging/Windows/deploy-qml >> "%LOG%" 2>&1
if errorlevel 1 (
  >> "%LOG%" echo ConfigureExit=1
  goto :fail
)

ninja DBScore >> "%LOG%" 2>&1
set "BUILD_EXIT=%ERRORLEVEL%"
echo BuildExit=%BUILD_EXIT% >> "%LOG%"
if not "%BUILD_EXIT%"=="0" goto :fail

cmake --build . --target install >> "%LOG%" 2>&1
set "INSTALL_EXIT=%ERRORLEVEL%"
echo InstallExit=%INSTALL_EXIT% >> "%LOG%"
if not "%INSTALL_EXIT%"=="0" goto :fail

if not exist "C:\DBscore\install\bin\Qt6Core5Compat.dll" (
  >> "%LOG%" echo MissingQt6Core5Compat
  goto :fail
)
if not exist "C:\DBscore\install\bin\Qt6Core.dll" (
  >> "%LOG%" echo MissingQt6Core
  goto :fail
)
if not exist "C:\DBscore\install\bin\platforms\qwindows.dll" (
  >> "%LOG%" echo MissingQWindowsPlugin
  goto :fail
)
if not exist "C:\DBscore\install\bin\d3dcompiler_47.dll" (
  >> "%LOG%" echo MissingD3DCompiler47
  goto :fail
)
if not exist "C:\DBscore\install\bin\avformat-62.dll" (
  >> "%LOG%" echo MissingFFmpegAvformat
  goto :fail
)
if not exist "C:\DBscore\install\bin\avcodec-62.dll" (
  >> "%LOG%" echo MissingFFmpegAvcodec
  goto :fail
)
if not exist "C:\DBscore\install\bin\avutil-60.dll" (
  >> "%LOG%" echo MissingFFmpegAvutil
  goto :fail
)
if not exist "C:\DBscore\install\qml\QtQuick\qmldir" (
  >> "%LOG%" echo MissingQtQuickQml
  goto :fail
)
if not exist "C:\DBscore\install\qml\Qt5Compat\GraphicalEffects\qmldir" (
  >> "%LOG%" echo MissingQt5CompatGraphicalEffectsQml
  goto :fail
)
if not exist "C:\DBscore\install\locale\qt_zh_CN.qm" (
  >> "%LOG%" echo MissingChineseTranslations
  goto :fail
)

del /q C:\DBscore\build\DBScore-*.msi 2>nul
cpack -G WIX -C Release >> "%LOG%" 2>&1
set "PACKAGE_EXIT=%ERRORLEVEL%"
echo PackageExit=%PACKAGE_EXIT% >> "%LOG%"
if not "%PACKAGE_EXIT%"=="0" goto :fail

set "MSIFILE="
for %%F in (C:\DBscore\build\DBScore-*.msi) do set "MSIFILE=%%F"
if not defined MSIFILE (
  echo MSI_NOT_FOUND >> "%LOG%"
  goto :fail
)

set "VERSION="
set /p VERSION=<C:\DBscore\release-version.txt
if not defined VERSION goto :fail

cscript //nologo C:\DBscore\buildscripts\packaging\Windows\validate_windows_msi.vbs "!MSIFILE!" "DB Score" "{22222222-2222-2222-2222-222222222222}" "!VERSION!" >> "%LOG%" 2>&1
if errorlevel 1 goto :fail

powershell -NoProfile -ExecutionPolicy Bypass -Command "Copy-Item -LiteralPath '!MSIFILE!' -Destination ('C:\Mac\Home\Desktop\DB-Score-Windows-' + '!VERSION!' + '.msi') -Force" >> "%LOG%" 2>&1
set "COPY_MSI_EXIT=!ERRORLEVEL!"
echo CopyMsiExit=!COPY_MSI_EXIT! >> "%LOG%"
if not "!COPY_MSI_EXIT!"=="0" goto :fail

powershell -NoProfile -ExecutionPolicy Bypass -Command "Copy-Item -LiteralPath '!MSIFILE!' -Destination ('C:\Mac\Home\Desktop\' + [char]68 + [char]66 + ' score' + [char]0x5236 + [char]0x8C31 + [char]0x5927 + [char]0x5E08 + '.msi') -Force" >> "%LOG%" 2>&1
set "COPY_PUBLIC_MSI_EXIT=!ERRORLEVEL!"
echo CopyPublicMsiExit=!COPY_PUBLIC_MSI_EXIT! >> "%LOG%"
if not "!COPY_PUBLIC_MSI_EXIT!"=="0" goto :fail

set "SUCCESS=1"
goto :finish

:fail
>> "%LOG%" echo RESULT=FAILED
goto :cleanup

:finish
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\DBscore\buildscripts\packaging\Windows\cleanup_old_windows_versions.ps1" -Version "!VERSION!" >> "%LOG%" 2>&1
set "CLEANUP_EXIT=!ERRORLEVEL!"
echo LatestOnlyCleanupExit=!CLEANUP_EXIT! >> "%LOG%"
if not "!CLEANUP_EXIT!"=="0" (
  >> "%LOG%" echo RESULT=FAILED_CLEANUP
  set "SUCCESS=0"
)
if "!SUCCESS!"=="1" >> "%LOG%" echo RESULT=SUCCESS

:cleanup
echo END=%DATE% %TIME% >> "%LOG%"
copy /y "%LOG%" "C:\Mac\Home\dbscore_windows_package.log" >nul 2>&1
if "!SUCCESS!"=="1" exit /b 0
exit /b 1
