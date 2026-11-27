@echo off
rem ASCII only: cmd reads batch files in the OEM code page, so non-ASCII
rem bytes here can break parsing. All real logic lives in install.ps1.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
