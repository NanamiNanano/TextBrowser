@echo off
rem 卸载：删除程序目录 + 桌面快捷方式（询问是否连同阅读数据一起删）
rem ASCII only —— cmd 按 OEM 代码页读批处理，中文注释容易把解析搞崩
setlocal
set "DEST=%LOCALAPPDATA%\TextBrowser"
set "LNK=%USERPROFILE%\Desktop\文本浏览器.lnk"
for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders" /v Desktop 2^>nul ^| find "Desktop"') do set "LNK=%%B\文本浏览器.lnk"

echo.
echo   Uninstalling TextBrowser / 正在卸载文本浏览器
echo.
if exist "%LNK%" (
    del /f /q "%LNK%" >nul 2>&1
    echo   [OK] Desktop shortcut removed / 已删除桌面快捷方式
)

echo.
set /p ANSWER=Delete reading data too? / 是否同时删除书架、进度、书签 [y/N]: 
if /i "%ANSWER%"=="y" (
    rd /s /q "%APPDATA%\TextBrowser" >nul 2>&1
    echo   [OK] Reading data removed / 已删除阅读数据
) else (
    echo   [--] Reading data kept at %%APPDATA%%\TextBrowser / 阅读数据保留
)

echo.
echo   Removing program folder ... / 正在删除程序目录
rem 自己所在目录不能直接删：起一个延迟的 cmd 在退出后删
start "" /min cmd /c "timeout /t 2 >nul & rd /s /q ""%DEST%"""
exit /b 0
