# 生成 文本浏览器.lnk 快捷方式（换机器 / 移动目录后重新跑一次）
#
# 为什么用 pythonw.exe：python.exe 每次双击都会闪一个黑色控制台窗口。
# pythonw 没有控制台，所以 launcher.py 把异常写成日志 + 弹窗，否则用户只会
# 看到「双击了但没反应」。
#
# 用法: .\scripts\make_shortcut.ps1 [-Desktop]

param([switch]$Desktop)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $root 'launcher.py'
$icon = Join-Path $root 'assets\app.ico'

if (-not (Test-Path $launcher)) { throw "找不到 $launcher" }
if (-not (Test-Path $icon)) {
    Write-Host "图标不存在，先生成 ..."
    & python (Join-Path $root 'scripts\make_icon.py')
}

# 优先系统 Python 的 pythonw（比各类运行时目录更稳定）
$pythonw = $null
foreach ($cand in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\pythonw.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\pythonw.exe'))) {
    if (Test-Path $cand) { $pythonw = $cand; break }
}
if (-not $pythonw) {
    $cmd = Get-Command pythonw -ErrorAction SilentlyContinue
    if ($cmd) { $pythonw = $cmd.Source }
}
if (-not $pythonw) { throw '找不到 pythonw.exe，请先安装 Python 并加入 PATH' }

$targets = @(Join-Path $root '文本浏览器.lnk')
if ($Desktop) {
    $targets += Join-Path ([Environment]::GetFolderPath('Desktop')) '文本浏览器.lnk'
}

$ws = New-Object -ComObject WScript.Shell
foreach ($lnkPath in $targets) {
    $lnk = $ws.CreateShortcut($lnkPath)
    $lnk.TargetPath = $pythonw
    $lnk.Arguments = '"' + $launcher + '"'
    $lnk.WorkingDirectory = $root
    $lnk.IconLocation = $icon + ',0'
    $lnk.Description = '文本浏览器 —— 打开 TXT / EPUB 阅读'
    $lnk.WindowStyle = 1
    $lnk.Save()
    Write-Host "已创建 $lnkPath"
}

Write-Host "目标: $pythonw"
