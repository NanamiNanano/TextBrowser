# 生成快捷方式（换机器 / 移动目录 / 重新打包后跑一次）
#
# 两种模式：
#   默认        指向 launcher.py + pythonw.exe（开发用，依赖本机 Python 与 vendor）
#   -Packaged   指向 dist\文本浏览器\文本浏览器.exe（免安装版，拷走整个 dist 目录即可用）
#
# 为什么开发模式用 pythonw.exe：python.exe 每次双击都会闪一个黑色控制台窗口。
# pythonw 没有控制台，所以 launcher.py 把异常写成日志 + 弹窗，否则用户只会
# 看到「双击了但没反应」。
#
# 用法: .\scripts\make_shortcut.ps1 [-Desktop] [-Packaged]

param([switch]$Desktop, [switch]$Packaged)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $root 'launcher.py'
$icon = Join-Path $root 'assets\app.ico'

if (-not (Test-Path $icon)) {
    Write-Host "图标不存在，先生成 ..."
    & python (Join-Path $root 'scripts\make_icon.py')
}

if ($Packaged) {
    $exe = Join-Path $root 'dist\文本浏览器\文本浏览器.exe'
    if (-not (Test-Path $exe)) { throw "找不到 $exe，先跑 scripts\build.ps1" }
    $ws = New-Object -ComObject WScript.Shell
    $targets = @(Join-Path (Split-Path $exe) '文本浏览器 快捷方式.lnk')
    if ($Desktop) {
        $targets += Join-Path ([Environment]::GetFolderPath('Desktop')) '文本浏览器.lnk'
    }
    foreach ($lnkPath in $targets) {
        $lnk = $ws.CreateShortcut($lnkPath)
        $lnk.TargetPath = $exe
        $lnk.WorkingDirectory = Split-Path $exe
        $lnk.IconLocation = $exe + ',0'
        $lnk.Description = '文本浏览器 —— 打开 TXT / EPUB 阅读'
        $lnk.Save()
        Write-Host "已创建 $lnkPath"
    }
    exit 0
}

if (-not (Test-Path $launcher)) { throw "找不到 $launcher" }

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
