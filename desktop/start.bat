@echo off
rem DSH desktop shell launcher (double-click; this window closes, electron runs detached)
cd /d "%~dp0"
start "" node_modules\electron\dist\electron.exe . --no-sandbox
