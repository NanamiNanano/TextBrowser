@echo off
chcp 65001 >nul
setlocal
set "HERE=%~dp0"
set "TARGET=%HERE%文本浏览器.exe"

if not exist "%TARGET%" (
    echo 找不到 文本浏览器.exe，请确认本文件和 exe 在同一个文件夹。
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $lnk = $ws.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) '文本浏览器.lnk')); $lnk.TargetPath = '%TARGET%'; $lnk.WorkingDirectory = '%HERE%'; $lnk.IconLocation = '%TARGET%,0'; $lnk.Description = '文本浏览器 —— TXT / EPUB 阅读'; $lnk.Save()"

if errorlevel 1 (
    echo 创建失败，请手动把 文本浏览器.exe 发送到桌面快捷方式。
) else (
    echo 已在桌面创建「文本浏览器」快捷方式。
)
pause
