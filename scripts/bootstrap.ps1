# 安装依赖到 vendor\py312（不污染系统 site-packages）
#
# 优先用 pip；若 pip 因「临时文件删除被拒」失败（受限环境常见），
# 退回到「node 下载 wheel + Python zipfile 解压」的方式，后者只需要写权限。
#
# 用法: .\scripts\bootstrap.ps1 [-Force]

param([switch]$Force)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$vendor = Join-Path $root 'vendor\py312'
$wheels = Join-Path $root 'vendor\wheels'
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { throw '找不到 python，请先安装 Python 3.10+ 并加入 PATH' }

$ver = & python -c "import sys;print('%d.%d'%sys.version_info[:2])"
Write-Host "Python $ver -> $($py.Source)"

if ((Test-Path (Join-Path $vendor 'PySide6\QtCore.pyd')) -and -not $Force) {
    Write-Host "依赖已存在：$vendor（要重装加 -Force）"
    exit 0
}

Write-Host "`n[1/2] 尝试 pip ..."
& python -m pip install --no-cache-dir --disable-pip-version-check --target $vendor PySide6-Essentials
if ($LASTEXITCODE -eq 0) {
    Write-Host "pip 安装成功"
    exit 0
}

Write-Host "`npip 失败，改用离线解压方式 ..."
$node = (Get-Command node -ErrorAction SilentlyContinue)
if (-not $node) {
    throw 'pip 失败且没有 node。请手动下载 PySide6-Essentials 与 shiboken6 的 win_amd64 wheel，解压到 vendor\py312'
}

New-Item -ItemType Directory -Force -Path $wheels | Out-Null
& node (Join-Path $root 'spike\py\fetch_wheels.cjs') $wheels PySide6-Essentials shiboken6
if ($LASTEXITCODE -ne 0) { throw 'wheel 下载失败' }

$whl = Get-ChildItem $wheels -Filter *.whl | ForEach-Object { $_.FullName }
& python (Join-Path $root 'spike\py\install_wheel.py') $vendor @whl
Write-Host "`n完成。验证："
& python -c "import sys;sys.path.insert(0,r'$vendor');from PySide6 import QtCore;print('Qt',QtCore.qVersion())"
