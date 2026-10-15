@echo off
rem Build QuadDiary for release:
rem   1) PyInstaller onedir -> dist\QuadDiary\QuadDiary.exe + _internal
rem      (onedir: no extraction to %TEMP% at startup, avoids "Could not create temporary directory")
rem   2) Inno Setup 6 -> dist\QuadDiary-Setup.exe (the file to upload to GitHub Releases)
rem Requires: pip install -r requirements-dev.txt, and Inno Setup 6 (https://jrsoftware.org/isinfo.php)
setlocal
cd /d "%~dp0"
set "VENV=%USERPROFILE%\ddvenv\Scripts"

"%VENV%\pyinstaller.exe" --noconsole --onedir --noconfirm --name QuadDiary --hidden-import keyring.backends.Windows "%~dp0main.py"
if errorlevel 1 goto fail

set "VER="
for /f "usebackq delims=" %%v in (`call "%VENV%\python.exe" -c "from app import __version__; print(__version__)"`) do set "VER=%%v"
if not defined VER (
  echo Could not read __version__ from app\__init__.py
  goto fail
)

set "ISCC="
for %%p in ("%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do (
  if not defined ISCC if exist %%p set "ISCC=%%~p"
)
if not defined ISCC (
  echo Inno Setup 6 not found. Install it, or ship dist\QuadDiary\ as a zip instead.
  goto fail
)

"%ISCC%" /DMyAppVersion=%VER% "%~dp0installer.iss"
if errorlevel 1 goto fail

echo.
echo Done: dist\QuadDiary-Setup.exe (v%VER%)
pause
exit /b 0

:fail
echo.
echo Build failed.
pause
exit /b 1
