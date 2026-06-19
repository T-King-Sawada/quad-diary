@echo off
rem Build single-file QuadDiary.exe (requires: pip install pyinstaller)
"%USERPROFILE%\ddvenv\Scripts\pyinstaller.exe" --noconsole --onefile --name QuadDiary --hidden-import keyring.backends.Windows "%~dp0main.py"
pause
