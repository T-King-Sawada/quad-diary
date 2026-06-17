@echo off
rem Build single-file DailyDiary.exe (requires: pip install pyinstaller)
"%USERPROFILE%\ddvenv\Scripts\pyinstaller.exe" --noconsole --onefile --name DailyDiary --hidden-import keyring.backends.Windows "%~dp0main.py"
pause
