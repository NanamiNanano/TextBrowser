# 启动文本浏览器（开发模式，带控制台，能看到报错）
#
# 用法: .\scripts\run.ps1 [要打开的文件]
#
# Python 解释器查找顺序：
#   1. 环境变量 TB_PYTHON 指定的路径
#   2. PATH 里的 python
#   3. 常见的 %LOCALAPPDATA%\Programs\Python\Python3xx\python.exe

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot

$py = $null
if ($env:TB_PYTHON -and (Test-Path $env:TB_PYTHON)) {
    $py = $env:TB_PYTHON
}
if (-not $py) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source }
}
if (-not $py) {
    foreach ($ver in 'Python313', 'Python312', 'Python311', 'Python310') {
        $cand = Join-Path $env:LOCALAPPDATA "Programs\Python\$ver\python.exe"
        if (Test-Path $cand) { $py = $cand; break }
    }
}
if (-not $py) {
    throw '找不到 python。请安装 Python 3.10+ 并加入 PATH，或用 TB_PYTHON 指定路径。'
}

# 项目自带的 PySide6 优先，不受系统已装版本影响
$env:PYTHONPATH = "$root;$root\vendor\py312"
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $root
& $py -m app @args
