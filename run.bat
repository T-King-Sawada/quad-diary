@echo off
rem Start as tray app and open the diary. --show opens the diary on launch.
start "" "%USERPROFILE%\ddvenv\Scripts\pythonw.exe" "%~dp0main.py" --show
