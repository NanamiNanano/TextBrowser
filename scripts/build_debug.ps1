# 生成「诊断版」：控制台 + 不裁剪
#
# 目的只有一个：让 Qt 把「托盘图标注册失败」这类告警直接打到窗口里，
# 同时排除「裁剪掉某个组件」这个可能。
#
# 产物: dist\TextBrowserDbg\TextBrowserDbg.exe
# 用法: 双击 dist\TextBrowserDbg\run_debug.cmd

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = "$root;$root\vendor\py312"
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $root

$dist = Join-Path $root 'dist\TextBrowserDbg'
$args = @(
    '-m', 'PyInstaller',
    '--noconfirm', '--clean',
    '--console',                       # 关键：保留控制台，Qt 告警能看到
    '--name', 'TextBrowserDbg',
    '--icon', (Join-Path $root 'assets\app.ico'),
    '--distpath', (Join-Path $root 'dist'),
    '--workpath', (Join-Path $root 'build\pyidbg'),
    '--specpath', (Join-Path $root 'build'),
    '--add-data', ((Join-Path $root 'assets') + ';assets'),
    (Join-Path $root 'launcher.py')
)

Write-Host "== 打包诊断版（控制台 + 不裁剪）==" -ForegroundColor Cyan
& python @args
if ($LASTEXITCODE -ne 0) { throw "打包失败" }

# 放一个双击就能跑的入口，输出同时写文件，方便把结果发回来
$cmd = @'
@echo off
chcp 65001 >nul
cd /d "%~dp0"
set TB_DEBUG_ICON=1
set TB_DEBUG_TRAYSHOT=1
set PYTHONIOENCODING=utf-8
echo ==== 诊断开始（把下面的内容整段复制发回即可）====
"%~dp0TextBrowserDbg.exe" 2>&1 | more
echo.
echo ==== 程序已结束，以下是托盘诊断 ====
if exist "%~dp0tray_diag.txt" type "%~dp0tray_diag.txt"
echo.
echo ==== 结束。请把上面全部内容复制发回 ====
pause
'@
[IO.File]::WriteAllText((Join-Path $dist 'run_debug.cmd'), ($cmd -replace "`r?`n", "`r`n"),
                        [Text.Encoding]::GetEncoding(936))

$size = (Get-ChildItem $dist -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host "`n== 完成 ==" -ForegroundColor Green
Write-Host ("诊断版目录 : {0}" -f $dist)
Write-Host ("体积       : {0:N1} MB" -f $size)
Write-Host "`n请双击运行：dist\TextBrowserDbg\run_debug.cmd"
